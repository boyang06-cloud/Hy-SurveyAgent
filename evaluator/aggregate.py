"""加权聚合 + Critical Failure Gate。

实现与 ``.codebuddy/skills/hy-surveyagent-eval-harness/scripts/aggregate_scores.py``
保持一致（同一套权重与 gate 规则）；维度缺失时按剩余权重重新归一化。
"""

from __future__ import annotations

from typing import Any

from evaluator.config import GATE, WEIGHTS


class ScoreError(ValueError):
    """分数输入不合法。"""


def _coerce_score(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        value = value.get("score")
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        raise ScoreError(f"维度分数必须是数字，收到：{value!r}")
    score = float(value)
    if score < 0 or score > 100:
        raise ScoreError(f"维度分数必须落在 [0,100]，收到：{score}")
    return score


def weighted_score(
    dimensions: dict[str, Any], weights: dict[str, float] | None = None
) -> tuple[float, list[str]]:
    """按权重聚合；缺失维度按剩余权重归一化，返回 (分数, 缺失维度)。"""
    effective_weights = dict(WEIGHTS if weights is None else weights)
    if not effective_weights or any(value < 0 for value in effective_weights.values()):
        raise ScoreError("权重必须是非空非负映射。")
    present: dict[str, float] = {}
    missing: list[str] = []
    for key in effective_weights:
        score = _coerce_score(dimensions.get(key))
        if score is None:
            missing.append(key)
        else:
            present[key] = score
    unknown = sorted(set(dimensions) - set(effective_weights))
    if unknown:
        raise ScoreError(f"存在未知维度：{unknown}")
    if not present:
        raise ScoreError("没有任何可用维度分数，无法聚合。")
    total_weight = sum(effective_weights[key] for key in present)
    return sum(present[key] * effective_weights[key] for key in present) / total_weight, missing


def apply_gate(score: float, gate: dict[str, Any]) -> tuple[float, list[str]]:
    """应用 Critical Failure Gate，多个条件命中时取最严格上限。"""
    reasons: list[str] = []
    cap = 100.0

    fabricated = gate.get("fabricated_citation_rate")
    if isinstance(fabricated, (int, float)) and not isinstance(fabricated, bool):
        if fabricated > GATE["fabricated_citation_rate_high"]:
            cap = min(cap, 40.0)
            reasons.append(f"Fabricated Citation Rate {fabricated:.1%} > 30% → ≤40")
        elif fabricated > GATE["fabricated_citation_rate_low"]:
            cap = min(cap, 60.0)
            reasons.append(f"Fabricated Citation Rate {fabricated:.1%} > 10% → ≤60")

    recall = gate.get("citation_recall")
    if isinstance(recall, (int, float)) and not isinstance(recall, bool):
        if recall < GATE["citation_recall_min"]:
            cap = min(cap, 50.0)
            reasons.append(f"Citation Recall {recall:.1%} < 40% → ≤50")

    severe = gate.get("severe_contradictions")
    if isinstance(severe, int) and not isinstance(severe, bool):
        if severe >= int(GATE["severe_contradictions_min"]):
            cap = min(cap, 60.0)
            reasons.append(f"Severe Contradictions {severe} ≥ 3 → ≤60")

    return min(score, cap), reasons


def aggregate(payload: dict[str, Any]) -> dict[str, Any]:
    """完整聚合：加权 → Gate，返回结果字典（与 skill 脚本字段一致）。"""
    dimensions = payload.get("dimensions") or {}
    if not isinstance(dimensions, dict):
        raise ScoreError("dimensions 必须是对象。")
    gate = payload.get("gate") or {}
    if not isinstance(gate, dict):
        raise ScoreError("gate 必须是对象。")

    configured_weights = payload.get("weights")
    weights = configured_weights if isinstance(configured_weights, dict) else None
    raw, missing = weighted_score(dimensions, weights)
    final, reasons = apply_gate(raw, gate)
    return {
        "run_id": payload.get("run_id", ""),
        "method": payload.get("method", ""),
        "dataset_version": payload.get("dataset_version", ""),
        "raw_score": round(raw, 2),
        "final_score": round(final, 2),
        "cap_applied": bool(reasons),
        "gate_reasons": reasons,
        "missing_dimensions": missing,
        "dimensions": {
            key: _coerce_score(dimensions.get(key)) for key in WEIGHTS if key in dimensions
        },
        "weights": dict(WEIGHTS if weights is None else weights),
    }
