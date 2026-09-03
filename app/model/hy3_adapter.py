"""Hy3 Adapter —— 全项目唯一允许调用 Hy3 的位置。

Hy3 提供 OpenAI 兼容的 Chat Completions 接口：
``POST {base_url}/chat/completions``，请求体 ``{"model","messages","temperature","max_tokens"}``。
若后续改用官方 SDK，只需替换本文件，Agent 与 Pipeline 不变。
"""

from __future__ import annotations

import time
from typing import Any, Protocol

import httpx

from app.config import AppConfig
from app.model.provider import LLMError, LLMProvider, LLMResponse, Message

CHAT_COMPLETIONS_PATH = "/chat/completions"
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
MAX_BACKOFF_SECONDS = 30.0


class HttpClient(Protocol):
    """最小 HTTP 客户端协议，便于测试注入假客户端。"""

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> Any: ...


class Hy3Adapter(LLMProvider):
    """把 LLMProvider 调用翻译成 Hy3 Chat Completions 请求。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff: float = 2.0,
        client: HttpClient | None = None,
    ) -> None:
        if not base_url:
            raise LLMError("缺少 Hy3 服务地址（base_url）。")
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self._client = client
        self._owns_client = client is None

    @classmethod
    def from_config(cls, config: AppConfig, client: HttpClient | None = None) -> Hy3Adapter:
        """从 AppConfig 构造；密钥只经 config 暴露，不在此处读取文件或环境变量。"""
        return cls(
            api_key=config.api_key(),
            base_url=config.base_url(),
            model=config.model.name,
            timeout=config.runtime.timeout_seconds,
            max_retries=config.runtime.max_retries,
            backoff=config.runtime.retry_backoff,
            client=client,
        )

    # --- LLMProvider ----------------------------------------------------- #

    def generate(
        self,
        messages: list[Message],
        model: str,
        temperature: float,
        max_tokens: int,
        *,
        top_p: float = 1.0,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if top_p is not None:
            payload["top_p"] = top_p

        started = time.perf_counter()
        data = self._post(payload)
        return LLMResponse(
            text=self._content(data),
            model=str(data.get("model") or payload["model"]),
            token_usage=self._usage(data),
            latency_ms=int((time.perf_counter() - started) * 1000),
            raw=data,
        )

    # --- 内部实现 --------------------------------------------------------- #

    @property
    def client(self) -> HttpClient:
        if self._client is None:
            self._client = httpx.Client()  # type: ignore[assignment]
        return self._client

    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith(CHAT_COMPLETIONS_PATH):
            return base
        return base + CHAT_COMPLETIONS_PATH

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error = "未知错误"
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.post(
                    self.endpoint(),
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )
            except Exception as exc:  # noqa: BLE001 - 网络层异常同样进入重试
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                status = int(getattr(response, "status_code", 200) or 200)
                body = _safe_text(response)
                if status in RETRYABLE_STATUS:
                    last_error = f"HTTP {status}: {body[:200]}"
                elif status >= 400:
                    raise LLMError(f"Hy3 请求失败：HTTP {status}: {body[:200]}")
                else:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise LLMError(f"Hy3 返回的不是合法 JSON：{exc}") from exc
                    if not isinstance(data, dict):
                        raise LLMError("Hy3 返回结构异常（期望 JSON 对象）。")
                    return data

            if attempt < self.max_retries:
                time.sleep(min(self.backoff * (2**attempt), MAX_BACKOFF_SECONDS))

        raise LLMError(f"Hy3 请求在 {self.max_retries + 1} 次尝试后仍失败：{last_error}")

    @staticmethod
    def _content(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("Hy3 返回内容为空（choices 为空）。")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):  # 部分兼容实现返回分片列表
            return "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            ).strip()
        if content is None:
            raise LLMError("Hy3 返回内容为空（message.content 缺失）。")
        return str(content).strip()

    @staticmethod
    def _usage(data: dict[str, Any]) -> dict[str, int]:
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            return {"prompt": 0, "completion": 0}
        return {
            "prompt": int(usage.get("prompt_tokens") or 0),
            "completion": int(usage.get("completion_tokens") or 0),
        }

    def close(self) -> None:
        """关闭自有的 HTTP 客户端（注入的客户端由调用方负责）。"""
        if self._owns_client and self._client is not None:
            closer = getattr(self._client, "close", None)
            if callable(closer):
                closer()
            self._client = None

    def __enter__(self) -> Hy3Adapter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _safe_text(response: Any) -> str:
    text = getattr(response, "text", "")
    return text if isinstance(text, str) else ""
