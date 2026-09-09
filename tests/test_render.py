"""Context 渲染的单元测试：注入内容正确、长度可控、unavailable 不进入 Context。"""

from __future__ import annotations

from app.core.types import Paper, PaperAnalysis, PaperSet
from app.io.render import (
    EMPTY_CONTEXT,
    render_analyses_context,
    render_paper_for_reading,
)


def test_render_paper_for_reading_includes_metadata_and_body() -> None:
    paper = Paper(
        paper_id="P001",
        title="A Title",
        authors=["A", "B"],
        year=2025,
        source="Conf 2025",
        abstract="short abstract",
        content="full body " * 50,
    )
    text = render_paper_for_reading(paper, max_chars=100)
    assert "Title: A Title" in text
    assert "Authors: A, B" in text
    assert "Year: 2025" in text
    assert "Abstract:\nshort abstract" in text
    assert "truncated" in text


def test_render_paper_for_reading_handles_metadata_only() -> None:
    text = render_paper_for_reading(Paper(paper_id="P001", title="A Title"))
    assert "仅元数据可用" in text


def test_render_analyses_context_includes_structured_fields(
    sample_papers: PaperSet, sample_analyses: list[PaperAnalysis]
) -> None:
    text = render_analyses_context(sample_analyses, sample_papers)
    assert "[P001] Vision-Language Models for Driving (2024)" in text
    assert "Key idea: Idea of P001" in text
    assert "Problem:" in text
    assert "Datasets: nuScenes" in text
    assert "P001-C1:" in text


def test_render_analyses_context_skips_unavailable(
    sample_papers: PaperSet, sample_analyses: list[PaperAnalysis]
) -> None:
    sample_analyses[1] = PaperAnalysis.unavailable("P002", "读取失败")
    text = render_analyses_context(sample_analyses, sample_papers)
    assert "Idea of P001" in text
    assert "Idea of P002" not in text


def test_render_analyses_context_limits_and_truncates(
    sample_papers: PaperSet, sample_analyses: list[PaperAnalysis]
) -> None:
    text = render_analyses_context(sample_analyses, sample_papers, max_papers=1, max_chars=200)
    assert "Idea of P001" in text
    assert "P002" not in text
    assert "truncated" in text


def test_render_analyses_context_empty() -> None:
    assert render_analyses_context([], PaperSet()) == EMPTY_CONTEXT
