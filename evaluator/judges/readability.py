"""Readability Judge（D8b）：整篇可读性 0–4。"""

from __future__ import annotations

from typing import Any

from evaluator.judges.base import BaseJudge, clamp_int, require_str


class ReadabilityJudge(BaseJudge):
    prompt_name = "readability"

    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        return {
            "score": clamp_int(parsed.get("score"), 4),
            "reason": require_str(parsed.get("reason")),
        }

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"score": 0, "reason": "Judge 调用失败，按 0 降级。"}

    def score_of(self, output: dict[str, Any]) -> float:
        return float(output.get("score", 0))
