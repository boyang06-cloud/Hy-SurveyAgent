"""LLM 调用抽象层。

所有 Agent 只依赖 ``LLMProvider``，不感知具体模型与厂商；
唯一的实现是 ``app.model.hy3_adapter.Hy3Adapter``，替换模型时 Pipeline 无需改动。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

Message = dict[str, Any]

REPAIR_INSTRUCTION = (
    "上一次输出不是合法 JSON。请只输出一个 JSON 对象，"
    "不要包含任何解释性文字、Markdown 代码块标记或额外说明。"
)


class LLMError(RuntimeError):
    """模型调用失败（网络、鉴权、返回格式异常等）。"""


class LLMOutputError(LLMError):
    """结构化输出解析失败。"""


@dataclass
class LLMResponse:
    """统一的模型返回，供 Stage 日志统计 token_usage 与 latency。"""

    text: str
    model: str = ""
    token_usage: dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0})
    latency_ms: int = 0
    raw: dict[str, Any] | None = None


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型输出中提取 JSON 对象。

    容忍 Markdown 代码块围栏与前后多余文字；使用括号配平扫描，避免贪婪匹配截断。
    """
    if not text:
        raise LLMOutputError("模型输出为空。")

    cleaned = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except ValueError:
        parsed = None

    if not isinstance(parsed, dict):
        candidate = _balanced_object(cleaned)
        if candidate is None:
            raise LLMOutputError("模型输出中找不到合法的 JSON 对象。")
        try:
            parsed = json.loads(candidate)
        except ValueError as exc:
            raise LLMOutputError(f"JSON 解析失败：{exc}") from exc

    if not isinstance(parsed, dict):
        raise LLMOutputError("模型输出不是 JSON 对象。")
    return parsed


def _balanced_object(text: str) -> str | None:
    """返回第一个花括号配平的子串。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


class LLMProvider(ABC):
    """模型调用抽象。子类只负责"把 messages 变成文本"。"""

    #: 最近一次原始响应，供调用方统计 token_usage / latency（generate_json 会同步更新）
    last_response: LLMResponse | None = None
    #: 累计 token 消耗（按实例惰性初始化，避免类属性被多实例共享）
    usage: dict[str, int] | None = None

    def _record(self, response: LLMResponse) -> None:
        self.last_response = response
        if self.usage is None:
            self.usage = {"prompt": 0, "completion": 0}
        self.usage["prompt"] += int(response.token_usage.get("prompt", 0))
        self.usage["completion"] += int(response.token_usage.get("completion", 0))

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        model: str,
        temperature: float,
        max_tokens: int,
        *,
        top_p: float = 1.0,
    ) -> LLMResponse:
        """调用模型并返回统一响应。"""
        raise NotImplementedError

    def generate_json(
        self,
        messages: list[Message],
        model: str,
        temperature: float,
        max_tokens: int,
        *,
        top_p: float = 1.0,
        retry_on_invalid: bool = True,
    ) -> dict[str, Any]:
        """调用模型并解析为 JSON 对象。

        解析失败时携带原始输出重试一次（要求只输出 JSON）；仍失败则抛出 LLMOutputError，
        由调用方按 Failure Handling 约定回退。
        """
        response = self.generate(messages, model, temperature, max_tokens, top_p=top_p)
        self._record(response)
        try:
            return extract_json_object(response.text)
        except LLMOutputError:
            if not retry_on_invalid:
                raise
        repaired = [
            *messages,
            {"role": "assistant", "content": response.text[:4000]},
            {"role": "user", "content": REPAIR_INSTRUCTION},
        ]
        response = self.generate(repaired, model, temperature, max_tokens, top_p=top_p)
        self._record(response)
        return extract_json_object(response.text)
