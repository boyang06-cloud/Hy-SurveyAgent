"""Judge 抽象：prompt 加载 → 调用 → 解析 → schema 校验 → 缓存 → 成本统计。

所有 Judge / Answerer / Claim Extractor 共用本基类：
- temperature 恒为 0（可复现）；
- 强制 JSON 输出（复用 ``LLMProvider.generate_json`` 的 repair 重试）；
- 解析失败 / 输出非法时降级（degrade）并记录 error，单条失败不中断维度；
- 缓存键 = (prompt 名, prompt 版本, 模型, 温度, 输入 hash, Judge 标签)。
"""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.model.provider import LLMError, LLMProvider, Message

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

_VERSION_RE = re.compile(r"version\s*[:=]\s*([0-9][0-9A-Za-z.\-]*)")


class JudgeError(RuntimeError):
    """Judge 输出非法或调用失败。"""


class PromptMeta:
    """Prompt 文件元信息（版本与 hash，用于 Provenance 与缓存键）。"""

    def __init__(self, name: str, version: str, sha256: str, template: str) -> None:
        self.name = name
        self.version = version
        self.sha256 = sha256
        self.template = template

    def provenance(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version, "sha256": self.sha256[:16]}


_PROMPT_CACHE: dict[str, PromptMeta] = {}


def load_prompt(name: str) -> PromptMeta:
    """加载 ``evaluator/prompts/<name>.md``；结果进程内缓存。"""
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise JudgeError(f"Judge Prompt 文件不存在：{path}")
    text = path.read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if not match:
        raise JudgeError(f"Judge Prompt 未记录 version：{path}")
    meta = PromptMeta(
        name=name,
        version=match.group(1),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        template=text,
    )
    _PROMPT_CACHE[name] = meta
    return meta


class BaseJudge(ABC):
    """所有 LLM 评测角色的基类。"""

    #: Prompt 文件名（不含扩展名）
    prompt_name: str = ""

    def __init__(
        self,
        llm: LLMProvider,
        model: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        cache_dir: str | Path | None = None,
    ) -> None:
        if temperature != 0.0:
            raise ValueError("Judge temperature 必须为 0（可复现要求）。")
        if not self.prompt_name:
            raise ValueError(f"{type(self).__name__} 必须定义 prompt_name。")
        self.llm = llm
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.prompt = load_prompt(self.prompt_name)
        self.stats: dict[str, int] = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": 0,
            "errors": 0,
            "cache_hits": 0,
        }

    # --- 调用链 ------------------------------------------------------------ #

    def build_messages(self, payload: dict[str, Any]) -> list[Message]:
        """Prompt 模板 + JSON 输入；解析方按 Prompt 标识分发（测试友好）。"""
        content = (
            self.prompt.template
            + "\n\n---\nInput (JSON):\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        )
        return [{"role": "user", "content": content}]

    @abstractmethod
    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """校验并归一化输出；非法值按 UNSUPPORTED / 0 降级并记录 warning。"""

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        """调用失败或解析失败时的降级输出（默认走空输出的校验降级）。"""
        return self.validate({})

    def score_of(self, output: dict[str, Any]) -> float:
        """共识机制使用的数值抽取；子类按各自 rubric 实现。"""
        return 0.0

    def run(self, payload: dict[str, Any], *, judge_label: str = "A") -> dict[str, Any]:
        """单次 Judge：缓存 → LLM → 校验 → 回写缓存。"""
        cache_path = self._cache_path(payload, judge_label)
        if cache_path is not None:
            cached = self._read_cache(cache_path)
            if cached is not None:
                self.stats["cache_hits"] += 1
                return cached
        before = dict(self.llm.usage or {})
        try:
            parsed = self.llm.generate_json(
                self.build_messages(payload),
                self.model,
                self.temperature,
                self.max_tokens,
            )
        except LLMError as exc:
            self._record_usage(before)
            self.stats["errors"] += 1
            output = dict(self.fallback(payload))
            output["error"] = str(exc)
        else:
            self._record_usage(before)
            if not isinstance(parsed, dict):
                self.stats["errors"] += 1
                output = dict(self.fallback(payload))
                output["error"] = "Judge 输出不是 JSON 对象。"
            else:
                output = self.validate(parsed)
        if cache_path is not None:
            self._write_cache(cache_path, output)
        return output

    def run_consensus(
        self,
        payload: dict[str, Any],
        *,
        dual: bool = False,
        threshold: float = 1.0,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """单 Judge 或双 Judge + 仲裁。

        ``dual`` 为真时运行 Judge B；|A−B| > threshold 时引入 Judge C，
        返回三者中位数对应的输出与 provenance。
        """
        first = self.run(payload)
        scores = [self.score_of(first)]
        if not dual:
            return first, {"mode": "single", "scores": scores}
        second = self.run(payload, judge_label="B")
        scores.append(self.score_of(second))
        if abs(scores[0] - scores[1]) <= threshold:
            return first, {"mode": "dual_agree", "scores": scores}
        third = self.run(payload, judge_label="C")
        scores.append(self.score_of(third))
        outputs = [first, second, third]
        outputs.sort(key=self.score_of)
        median = outputs[1]
        return median, {"mode": "dual_arbiter", "scores": scores}

    # --- 缓存与统计 --------------------------------------------------------- #

    def _cache_path(self, payload: dict[str, Any], judge_label: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(
            json.dumps(
                {
                    "prompt": self.prompt.name,
                    "version": self.prompt.version,
                    "sha256": self.prompt.sha256,
                    "model": self.model,
                    "temperature": self.temperature,
                    "label": judge_label,
                    "payload": payload,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return self.cache_dir / f"{self.prompt.name}-{digest}.json"

    def _read_cache(self, path: Path) -> dict[str, Any] | None:
        try:
            if path.is_file():
                cached = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and isinstance(cached.get("output"), dict):
                    return cached["output"]
        except (OSError, json.JSONDecodeError):
            return None
        return None

    def _write_cache(self, path: Path, output: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"output": output, "prompt": self.prompt.provenance(), "model": self.model},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        except OSError:
            # 缓存写失败不影响评测结果
            self.stats["errors"] += 1

    def _record_usage(self, before: dict[str, int]) -> None:
        self.stats["calls"] += 1
        after = self.llm.usage or {}
        self.stats["prompt_tokens"] += int(after.get("prompt", 0)) - int(before.get("prompt", 0))
        self.stats["completion_tokens"] += int(after.get("completion", 0)) - int(
            before.get("completion", 0)
        )
        response = self.llm.last_response
        if response is not None:
            self.stats["latency_ms"] += int(response.latency_ms)


def clamp_int(value: Any, maximum: int, default: int = 0) -> int:
    """把 Judge 输出的数值安全转为 [0, maximum] 的整数（供各 Judge 复用）。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(maximum, number))


def require_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default
