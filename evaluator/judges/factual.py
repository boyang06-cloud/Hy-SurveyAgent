"""Factual Judge（D1）：Claim 级证据判定，0/1/2 三档。

只依据提供的 Paper Evidence 判断；证据为空时不进入本 Judge（上层 gating）。
"""

from __future__ import annotations

from typing import Any

from evaluator.judges.base import BaseJudge, clamp_int

#: label → score（judge-design.md 第 2 节）
LABEL_SCORES: dict[str, int] = {
    "SUPPORTED": 2,
    "PARTIALLY_SUPPORTED": 1,
    "UNSUPPORTED": 0,
    "FABRICATED": 0,
    "NO_SUFFICIENT_INFORMATION": 0,
}


class FactualJudge(BaseJudge):
    prompt_name = "factual"

    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        label = str(parsed.get("label") or "").strip().upper()
        if label not in LABEL_SCORES:
            label = "UNSUPPORTED"
        score = clamp_int(parsed.get("score"), 2)
        canonical = LABEL_SCORES[label]
        warning = ""
        if not isinstance(parsed.get("score"), int) or score != canonical:
            warning = f"score 与 label 不一致，按 {label}={canonical} 归一化。"
            score = canonical
        reason = parsed.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = ""
            warning = (warning + " " if warning else "") + "reason 缺失。"
        return {
            "claim_id": str(parsed.get("claim_id") or ""),
            "label": label,
            "score": score,
            "reason": reason,
            **({"warning": warning} if warning else {}),
        }

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "claim_id": str(payload.get("claim_id") or ""),
            "label": "UNSUPPORTED",
            "score": 0,
            "reason": "Judge 调用失败，按 UNSUPPORTED 降级。",
        }

    def score_of(self, output: dict[str, Any]) -> float:
        return float(output.get("score", 0))
