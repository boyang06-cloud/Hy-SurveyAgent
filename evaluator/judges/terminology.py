"""Terminology Judge（D7）：chapter 级术语与学术严谨性错误计数。"""

from __future__ import annotations

from typing import Any

from evaluator.judges.base import BaseJudge, clamp_int


class TerminologyJudge(BaseJudge):
    prompt_name = "terminology"

    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        issues_raw = parsed.get("issues")
        issues: list[dict[str, str]] = []
        if isinstance(issues_raw, list):
            for item in issues_raw:
                if isinstance(item, dict):
                    issues.append(
                        {
                            "level": str(item.get("level") or "").upper(),
                            "description": str(item.get("description") or ""),
                        }
                    )
        return {
            "severe": clamp_int(parsed.get("severe"), 10**6),
            "moderate": clamp_int(parsed.get("moderate"), 10**6),
            "minor": clamp_int(parsed.get("minor"), 10**6),
            "issues": issues,
        }

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "severe": 0,
            "moderate": 0,
            "minor": 0,
            "issues": [],
            "warning": "Judge 调用失败，按无错误降级（分数 100），该章节结果低置信。",
        }

    def score_of(self, output: dict[str, Any]) -> float:
        return float(
            20 * int(output.get("severe", 0))
            + 8 * int(output.get("moderate", 0))
            + 2 * int(output.get("minor", 0))
        )
