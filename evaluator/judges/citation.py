"""Citation Judge（D2 Precision）：claim-citation pair 的支持度判定，0/1/2 三档。"""

from __future__ import annotations

from typing import Any

from evaluator.judges.base import BaseJudge, clamp_int, require_str


class CitationJudge(BaseJudge):
    prompt_name = "citation"

    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        support = parsed.get("support")
        score = clamp_int(support, 2)
        warning = ""
        if not isinstance(support, int) or support != score:
            warning = (
                "support 非法或越界，已按 0 处理。" if score == 0 else "support 已按边界裁剪。"
            )
        reason = require_str(parsed.get("reason"))
        if not reason:
            warning = (warning + " " if warning else "") + "reason 缺失。"
        return {
            "claim_id": str(parsed.get("claim_id") or ""),
            "citation": str(parsed.get("citation") or ""),
            "support": score,
            "reason": reason,
            **({"warning": warning} if warning else {}),
        }

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "claim_id": str(payload.get("claim_id") or ""),
            "citation": str(payload.get("citation") or ""),
            "support": 0,
            "reason": "Judge 调用失败，按 Unsupported 降级。",
        }

    def score_of(self, output: dict[str, Any]) -> float:
        return float(output.get("support", 0))
