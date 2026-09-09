"""Coverage Judge（D3）：chapter 级 KIU 覆盖判定与无关段落扫描。

单次调用同时输出：每个 KIU 的 0/1/2 覆盖分 + 该章节的无关段落数，
供 D3 的 word 加权聚合与 Irrelevant 惩罚使用。
"""

from __future__ import annotations

from typing import Any

from evaluator.judges.base import BaseJudge, clamp_int


class CoverageJudge(BaseJudge):
    prompt_name = "coverage"

    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        units_raw = parsed.get("units")
        units: list[dict[str, Any]] = []
        if isinstance(units_raw, list):
            for item in units_raw:
                if not isinstance(item, dict):
                    continue
                units.append(
                    {
                        "id": str(item.get("id") or ""),
                        "score": clamp_int(item.get("score"), 2),
                        "evidence_span": str(item.get("evidence_span") or ""),
                    }
                )
        total = clamp_int(parsed.get("total_paragraphs"), 10**6)
        irrelevant = clamp_int(parsed.get("irrelevant_paragraphs"), 10**6)
        return {
            "units": units,
            "total_paragraphs": total,
            "irrelevant_paragraphs": irrelevant,
            **({"warning": "units 缺失。"} if not units else {}),
        }

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        units = [
            {"id": str(unit.get("id") or ""), "score": 0, "evidence_span": ""}
            for unit in payload.get("units", [])
            if isinstance(unit, dict)
        ]
        return {
            "units": units,
            "total_paragraphs": 0,
            "irrelevant_paragraphs": 0,
            "warning": "Judge 调用失败，全部 KIU 按 missing 处理。",
        }

    def score_of(self, output: dict[str, Any]) -> float:
        units = output.get("units") or []
        if not units:
            return 0.0
        return 2.0 * sum(int(unit.get("score", 0)) for unit in units) / len(units)
