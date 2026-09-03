"""Hy3 Adapter 的单元测试：请求构造、响应解析、重试与错误归一化。全部使用假客户端。"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.model.hy3_adapter import Hy3Adapter
from app.model.provider import LLMError

BASE_URL = "https://hy3.unit.test/v1"
MESSAGES = [{"role": "user", "content": "hello"}]


class FakeResponse:
    """未显式给出 payload 时，`json()` 直接解析 text，用于模拟非法 JSON 响应。"""

    def __init__(
        self, status_code: int, payload: dict[str, Any] | None = None, text: str = ""
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text if text else (json.dumps(payload) if payload is not None else "")

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            return json.loads(self.text)  # 非法 JSON 时抛出 ValueError，与 httpx 行为一致
        return self._payload


class FakeClient:
    """按脚本返回响应或抛出异常，并记录每次调用。"""

    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_adapter(client: FakeClient, **kwargs: Any) -> Hy3Adapter:
    params: dict[str, Any] = {
        "api_key": "sk-unit-test-000000000",
        "base_url": BASE_URL,
        "model": "hy3-unit",
        "timeout": 5.0,
        "max_retries": 2,
        "backoff": 0.0,  # 测试中不做真实等待
        "client": client,
    }
    params.update(kwargs)
    return Hy3Adapter(**params)


def completion(content: str) -> dict[str, Any]:
    return {
        "model": "hy3-unit",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22},
    }


def test_endpoint_appends_chat_completions() -> None:
    adapter = make_adapter(FakeClient([]))
    assert adapter.endpoint() == f"{BASE_URL}/chat/completions"


def test_endpoint_is_idempotent() -> None:
    adapter = make_adapter(FakeClient([]), base_url=f"{BASE_URL}/chat/completions")
    assert adapter.endpoint() == f"{BASE_URL}/chat/completions"


def test_generate_builds_openai_compatible_request() -> None:
    client = FakeClient([FakeResponse(200, completion("ok"))])
    adapter = make_adapter(client)
    response = adapter.generate(MESSAGES, "hy3-unit", 0.2, 512, top_p=0.9)

    assert response.text == "ok"
    assert response.model == "hy3-unit"
    assert response.token_usage == {"prompt": 11, "completion": 22}
    call = client.calls[0]
    assert call["url"] == f"{BASE_URL}/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-unit-test-000000000"
    assert call["json"]["messages"] == MESSAGES
    assert call["json"]["temperature"] == 0.2
    assert call["json"]["max_tokens"] == 512
    assert call["json"]["top_p"] == 0.9


def test_retry_on_retryable_status() -> None:
    client = FakeClient(
        [FakeResponse(503, text="busy"), FakeResponse(200, completion("recovered"))]
    )
    adapter = make_adapter(client)
    assert adapter.generate(MESSAGES, "hy3-unit", 0.2, 512).text == "recovered"
    assert len(client.calls) == 2


def test_retry_on_network_error() -> None:
    client = FakeClient([RuntimeError("connection reset"), FakeResponse(200, completion("ok"))])
    adapter = make_adapter(client)
    assert adapter.generate(MESSAGES, "hy3-unit", 0.2, 512).text == "ok"


def test_raises_immediately_on_auth_error() -> None:
    client = FakeClient([FakeResponse(401, text="unauthorized")])
    adapter = make_adapter(client)
    with pytest.raises(LLMError, match="401"):
        adapter.generate(MESSAGES, "hy3-unit", 0.2, 512)
    assert len(client.calls) == 1


def test_raises_after_retries_exhausted() -> None:
    client = FakeClient([FakeResponse(500, text="err")] * 3)
    adapter = make_adapter(client)
    with pytest.raises(LLMError, match="3 次尝试"):
        adapter.generate(MESSAGES, "hy3-unit", 0.2, 512)
    assert len(client.calls) == 3


def test_raises_on_empty_choices() -> None:
    client = FakeClient([FakeResponse(200, {"choices": []})])
    adapter = make_adapter(client)
    with pytest.raises(LLMError, match="choices 为空"):
        adapter.generate(MESSAGES, "hy3-unit", 0.2, 512)


def test_raises_on_invalid_json_body() -> None:
    client = FakeClient([FakeResponse(200, text="not-json")])
    adapter = make_adapter(client)
    with pytest.raises(LLMError, match="合法 JSON"):
        adapter.generate(MESSAGES, "hy3-unit", 0.2, 512)
