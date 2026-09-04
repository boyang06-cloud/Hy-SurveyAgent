"""Context 渲染：把论文与论文分析结果转成各 Stage 所需的注入文本。

统一放在这里，保证各 Agent 拿到的 Context 形状一致、长度可控，
落实"按阶段传递最小必要 Context"（references/architecture.md 第 4 节）。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.types import Paper, PaperAnalysis, PaperSet

MAX_READING_CHARS = 24000
MAX_ANALYSIS_CHARS = 3000
EMPTY_CONTEXT = "（无论文分析结果可用）"


def render_paper_for_reading(paper: Paper, *, max_chars: int = MAX_READING_CHARS) -> str:
    """渲染单篇论文供 Paper Reader 抽取：只注入这一篇，不携带其它论文。"""
    parts = [f"Title: {paper.title}"]
    if paper.authors:
        parts.append(f"Authors: {', '.join(paper.authors[:10])}")
    if paper.year is not None:
        parts.append(f"Year: {paper.year}")
    if paper.source:
        parts.append(f"Source: {paper.source}")
    if paper.abstract:
        parts.append(f"Abstract:\n{paper.abstract}")
    if paper.content:
        parts.append(f"Content:\n{_truncate(paper.content, max_chars)}")
    elif not paper.abstract:
        parts.append("Content: （无论文正文，仅元数据可用）")
    return "\n".join(parts)


def render_analyses_context(
    analyses: list[PaperAnalysis],
    papers: PaperSet,
    *,
    max_papers: int | None = None,
    max_chars: int = MAX_ANALYSIS_CHARS,
) -> str:
    """渲染论文分析结果供 Survey Writer 使用；unavailable 的论文不进入 Context。"""
    selected = [analysis for analysis in analyses if analysis.available]
    if max_papers is not None:
        selected = selected[: max(0, max_papers)]
    if not selected:
        return EMPTY_CONTEXT

    blocks = []
    for analysis in selected:
        paper = papers.get(analysis.paper_id)
        title = paper.label() if paper else analysis.paper_id
        lines = [f"[{analysis.paper_id}] {title}"]
        _append(lines, "Key idea", analysis.key_idea)
        _append(lines, "Problem", analysis.problem)
        _append(lines, "Motivation", analysis.motivation)
        _append(lines, "Method", analysis.method)
        _append(lines, "Architecture", analysis.architecture)
        if analysis.dataset:
            lines.append(f"Datasets: {', '.join(analysis.dataset)}")
        if analysis.advantages:
            lines.append("Advantages:\n" + _bullets(analysis.advantages))
        if analysis.limitations:
            lines.append("Limitations:\n" + _bullets(analysis.limitations))
        if analysis.results:
            lines.append("Results:\n" + _bullets(analysis.results))
        if analysis.experiments:
            lines.append("Experiments:\n" + _bullets(analysis.experiments))
        if analysis.claims:
            lines.append(
                "Key claims:\n"
                + _bullets(f"{claim.claim_id}: {claim.text}" for claim in analysis.claims)
            )
        blocks.append(_truncate("\n".join(lines), max_chars))
    return "\n\n".join(blocks)


def _append(lines: list[str], name: str, value: str) -> None:
    if value:
        lines.append(f"{name}: {value}")


def _bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ...[truncated]"
