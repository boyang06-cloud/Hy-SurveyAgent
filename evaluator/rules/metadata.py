"""文献元数据规则检查（D8a，纯规则）。

- 相关性：2 = gold paper；1 = benchmark pool / human reference；0 = 数据集中未知（疑似捏造）；
- 重复引用：同一论文对应多个引用编号；
- 来源集中度：单篇论文在引用中的占比（>0.5 记为极端集中）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MARKER_RE = re.compile(r"\[(\d+)\]")


@dataclass
class LiteratureStats:
    relevance: dict[str, int]
    duplicates: list[str]
    concentration: float
    notes: list[str]


def check_literature(
    citations: list[dict[str, object]],
    survey_markdown: str,
    *,
    gold_papers: set[str],
    pool_papers: set[str],
) -> LiteratureStats:
    """citations 为 result.json 的 citations（citation_id / paper_id）。"""
    by_paper: dict[str, list[str]] = {}
    citation_ids: list[str] = []
    for citation in citations:
        citation_id = str(citation.get("citation_id") or "")
        paper_id = str(citation.get("paper_id") or "")
        if not citation_id or not paper_id:
            continue
        by_paper.setdefault(paper_id, []).append(citation_id)
        citation_ids.append(citation_id)

    relevance: dict[str, int] = {}
    for paper_id in by_paper:
        if paper_id in gold_papers:
            relevance[paper_id] = 2
        elif paper_id in pool_papers:
            relevance[paper_id] = 1
        else:
            relevance[paper_id] = 0

    duplicates = sorted(paper_id for paper_id, ids in by_paper.items() if len(set(ids)) > 1)

    marker_counts = [len(by_paper.get(pid, [])) for pid in by_paper]
    total_occurrences = sum(marker_counts)
    concentration = max(marker_counts) / total_occurrences if total_occurrences else 0.0

    notes: list[str] = []
    if duplicates:
        notes.append(f"重复引用：{duplicates[:5]}")
    if concentration > 0.5 and total_occurrences > 1:
        notes.append(f"来源集中度 {concentration:.1%} > 50%")

    # 正文标记计数与 references 数不一致（引用了未登记编号）
    used_markers = {match.group(1) for match in _MARKER_RE.finditer(survey_markdown)}
    known_markers = {cid for cid in citation_ids}
    unknown_markers = sorted(used_markers - known_markers)
    if unknown_markers:
        notes.append(f"正文引用标记无对应 references 条目：{unknown_markers[:5]}")

    return LiteratureStats(
        relevance=relevance,
        duplicates=duplicates,
        concentration=concentration,
        notes=notes,
    )
