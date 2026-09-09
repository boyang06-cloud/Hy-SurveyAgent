"""Synthesis Judge（D4）：四个子维度各 0–4，document-level 单次判定。"""

from __future__ import annotations

from typing import Any

from evaluator.judges.base import BaseJudge, clamp_int, require_str

SUB_DIMENSIONS = ("taxonomy", "comparison", "evolution", "insight")


class SynthesisJudge(BaseJudge):
    prompt_name = "synthesis"

    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key in SUB_DIMENSIONS:
            output[key] = clamp_int(parsed.get(key), 4)
        output["reason"] = require_str(parsed.get("reason"))
        return output

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: 0 for key in SUB_DIMENSIONS} | {"reason": "Judge 调用失败，按 0 降级。"}

    def score_of(self, output: dict[str, Any]) -> float:
        return float(sum(int(output.get(key, 0)) for key in SUB_DIMENSIONS))
