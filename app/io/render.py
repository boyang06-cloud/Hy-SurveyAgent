"""Context 渲染：把论文与论文分析结果转成各 Stage 所需的注入文本。

统一放在这里，保证各 Agent 拿到的 Context 形状一致、长度可控，
落实"按阶段传递最小必要 Context"（references/architecture.md 第 4 节）。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.types import (
    Citation,
    Claim,
    KnowledgeBase,
    OutlineSection,
    Paper,
    PaperAnalysis,
    PaperSet,
)

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


def render_knowledge_context(knowledge: KnowledgeBase) -> str:
    """渲染知识结构供 Outline Planner 使用（不含论文全文）。"""
    if knowledge.is_empty:
        return "（知识结构为空）"
    lines: list[str] = []
    if knowledge.topics:
        lines.append(f"Topics: {'; '.join(knowledge.topics)}")
    for name, groups in (
        ("Methods", knowledge.methods),
        ("Problems", knowledge.problems),
        ("Datasets", knowledge.datasets),
    ):
        if groups:
            lines.append(f"{name}:")
            lines.extend(f"- {group.name}: {', '.join(group.papers)}" for group in groups)
    if knowledge.relations:
        lines.append("Relations:")
        lines.extend(
            f"- {relation.source} {relation.relation} {relation.target}"
            for relation in knowledge.relations
        )
    if knowledge.papers:
        lines.append(f"Papers: {', '.join(knowledge.papers)}")
    return "\n".join(lines)


def render_claims_context(
    analyses: list[PaperAnalysis],
    papers: PaperSet,
    *,
    max_claims_per_paper: int = 5,
    max_chars_per_evidence: int = 160,
) -> str:
    """渲染可引用的论文级 Claim（Planner 据此填充 key_claims）。"""
    lines: list[str] = []
    for analysis in analyses:
        if not analysis.available or not analysis.claims:
            continue
        paper = papers.get(analysis.paper_id)
        title = paper.label() if paper else analysis.paper_id
        lines.append(f"[{analysis.paper_id}] {title}")
        for claim in analysis.claims[:max_claims_per_paper]:
            evidence = _truncate(claim.evidence, max_chars_per_evidence) if claim.evidence else ""
            suffix = f" (evidence: {evidence})" if evidence else ""
            lines.append(f"- {claim.claim_id}: {claim.text}{suffix}")
    return "\n".join(lines) if lines else "（无论文级 Claim 可用）"


def render_paper_evidence(
    analysis: PaperAnalysis,
    papers: PaperSet,
    *,
    max_claims: int = 5,
    max_chars_per_evidence: int = 200,
) -> str:
    """渲染单篇论文的定位证据，供 Citation Verifier 判断 Claim 是否被支持。"""
    paper = papers.get(analysis.paper_id)
    title = paper.label() if paper else analysis.paper_id
    lines = [f"[{analysis.paper_id}] {title}"]
    _append(lines, "Key idea", analysis.key_idea)
    _append(lines, "Method", analysis.method)
    if analysis.results:
        lines.append("Results:\n" + _bullets(analysis.results[:5]))
    if analysis.claims:
        bullets = []
        for claim in analysis.claims[:max_claims]:
            evidence = _truncate(claim.evidence, max_chars_per_evidence) if claim.evidence else ""
            suffix = f" (evidence: {evidence})" if evidence else ""
            bullets.append(f"- {claim.claim_id}: {claim.text}{suffix}")
        lines.append("Key claims:\n" + "\n".join(bullets))
    return "\n".join(lines)


def render_verification_context(
    claims: list[Claim],
    citation_map: list[Citation],
    analyses: list[PaperAnalysis],
    papers: PaperSet,
    *,
    max_claims_per_paper: int = 5,
    max_chars_per_evidence: int = 200,
) -> str:
    """渲染待核验 Claim 及其被引论文的定位证据（不含无关论文，最小必要 Context）。"""
    if not claims:
        return "（无 Claim 可核验）"
    analyses_by_id = {analysis.paper_id: analysis for analysis in analyses if analysis.available}
    citation_to_paper = {citation.citation_id: citation.paper_id for citation in citation_map}

    def _resolve(ref: str) -> str:
        return ref if ref in analyses_by_id else citation_to_paper.get(ref, ref)

    blocks: list[str] = []
    for claim in claims:
        lines = [f"Claim {claim.claim_id}: {claim.text}"]
        paper_ids = [_resolve(ref) for ref in claim.citations]
        if not paper_ids:
            lines.append("Citations: （无）")
            lines.append("Evidence: （该 Claim 没有可核验的引用）")
        else:
            lines.append("Citations: " + ", ".join(paper_ids))
            for paper_id in paper_ids:
                analysis = analyses_by_id.get(paper_id)
                if analysis is None:
                    lines.append(f"Evidence for {paper_id}: （该论文不可用或无分析结果）")
                else:
                    lines.append(f"Evidence for {paper_id}:")
                    lines.append(
                        render_paper_evidence(
                            analysis,
                            papers,
                            max_claims=max_claims_per_paper,
                            max_chars_per_evidence=max_chars_per_evidence,
                        )
                    )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_section_evidence(
    section: OutlineSection,
    analyses: list[PaperAnalysis],
    papers: PaperSet,
    *,
    max_papers: int | None = None,
    max_chars: int = MAX_ANALYSIS_CHARS,
) -> str:
    """渲染某个 Section 的最小必要证据：只包含该 Section 规划覆盖的论文。"""
    wanted = set(section.papers)
    relevant = [item for item in analyses if item.paper_id in wanted and item.available]
    if not relevant:
        relevant = [item for item in analyses if item.available]
    return render_analyses_context(relevant, papers, max_papers=max_papers, max_chars=max_chars)


def _append(lines: list[str], name: str, value: str) -> None:
    if value:
        lines.append(f"{name}: {value}")


def _bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ...[truncated]"
