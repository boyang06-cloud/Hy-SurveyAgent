"""维度评分公式（纯函数，与 LLM 解耦，可独立单测）。

公式来源：``eval_harness/eval_protocol.md`` 第 5–12 节；
所有结果归一化到 [0,100]，输入为空时返回 None（维度缺失）。
"""

from __future__ import annotations


def factual_score(scores: list[int]) -> float | None:
    """D1 = Σclaim / (2N) × 100。"""
    if not scores:
        return None
    return sum(scores) / (2.0 * len(scores)) * 100.0


def citation_metrics(
    supports: list[int],
    citation_worthy: int,
    cited_worthy: int,
    fabricated: int,
    total_citations: int,
) -> dict[str, float | None]:
    """D2：Precision / Recall / F1 / fabricated_rate。

    - precision = Σsupport / (2·N_pairs)，无 pair 时为 None；
    - recall = cited citation-worthy / total citation-worthy，无 citation-worthy 时为 None；
    - f1 = 2PR/(P+R)；两者皆缺 → None；一缺一在 → 用已有的一项（P 缺按 P=R? 不）：
      只有一项可用时按该限保守处理（precision 缺 → 0，recall 缺 → 0）。
    """
    precision: float | None = None
    if supports:
        precision = sum(supports) / (2.0 * len(supports))
    recall: float | None = None
    if citation_worthy > 0:
        recall = min(1.0, cited_worthy / citation_worthy)
    if precision is None and recall is None:
        f1: float | None = None
    elif precision is None:
        f1 = 0.0
    elif recall is None:
        f1 = 0.0
    else:
        f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
    fabricated_rate = fabricated / total_citations if total_citations > 0 else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fabricated_citation_rate": fabricated_rate,
    }


def coverage_score(unit_scores: dict[str, tuple[int, int]]) -> float | None:
    """D3 = Σ w_i r_i / (2Σw_i) × 100。

    unit_scores: {unit_id: (importance, score0-2)}。
    """
    if not unit_scores:
        return None
    total_weight = sum(weight for weight, _ in unit_scores.values())
    if total_weight <= 0:
        return None
    achieved = sum(weight * score for weight, score in unit_scores.values())
    return achieved / (2.0 * total_weight) * 100.0


def apply_irrelevant_penalty(score: float, irrelevant_rate: float) -> tuple[float, str | None]:
    """D3 的 Irrelevant 惩罚：>20% ×0.9；>40% ×0.7。"""
    if irrelevant_rate > 0.40:
        return score * 0.7, f"irrelevant_rate {irrelevant_rate:.1%} > 40% → ×0.7"
    if irrelevant_rate > 0.20:
        return score * 0.9, f"irrelevant_rate {irrelevant_rate:.1%} > 20% → ×0.9"
    return score, None


def sub_dimension_score(scores: list[int], maximum_each: int = 4) -> float | None:
    """D4 / D5：Σ子项 / (maximum_each × N) × 100。"""
    if not scores:
        return None
    return sum(scores) / (maximum_each * len(scores)) * 100.0


def quiz_dimension_score(
    general_totals: list[float],
    topic_totals: list[float],
    *,
    general_weight: float = 0.4,
    topic_weight: float = 0.6,
) -> float | None:
    """D6 = 0.4G + 0.6T；G/T 为该集合单题均分（0–100）。

    只有一套 quiz 可用时退化为该套分数；两套皆空 → None。
    """
    general = sum(general_totals) / len(general_totals) * 10.0 if general_totals else None
    topic = sum(topic_totals) / len(topic_totals) * 10.0 if topic_totals else None
    if general is None and topic is None:
        return None
    if general is None:
        return topic
    if topic is None:
        return general
    return general_weight * general + topic_weight * topic


def terminology_score(severe: int, moderate: int, minor: int, words: int) -> float | None:
    """D7 = max(0, 100 − (20S+8M+2m)/(words/1000))。"""
    if words <= 0:
        return None
    penalty = (20 * severe + 8 * moderate + 2 * minor) / (words / 1000.0)
    return max(0.0, 100.0 - penalty)


def literature_relevance_score(relevance: list[int]) -> float | None:
    """D8a = Σrelevance / (2N) × 100。"""
    if not relevance:
        return None
    return sum(relevance) / (2.0 * len(relevance)) * 100.0


def format_score(passed: int, total: int) -> float | None:
    """D8c：规则通过率 × 100。"""
    if total <= 0:
        return None
    return passed / total * 100.0


def d8_composite(
    literature: float | None,
    readability: float | None,
    fmt: float | None,
) -> float | None:
    """D8 = (3·Da + 2·Db + 1·Dc)/6；缺失子项按剩余权重归一化。"""
    parts = [(3.0, literature), (2.0, readability), (1.0, fmt)]
    available = [(weight, score) for weight, score in parts if score is not None]
    if not available:
        return None
    total_weight = sum(weight for weight, _ in available)
    return sum(weight * score for weight, score in available) / total_weight


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
