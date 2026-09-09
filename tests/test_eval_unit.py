"""维度公式（metrics.py）、文本工具、规则检查与证据检索单元测试。"""

from __future__ import annotations

import pytest

from evaluator.dataset import PaperFulltext, PaperSection
from evaluator.evidence.retriever import LexicalRetriever, tokenize
from evaluator.metrics import (
    apply_irrelevant_penalty,
    citation_metrics,
    coverage_score,
    d8_composite,
    factual_score,
    format_score,
    literature_relevance_score,
    quiz_dimension_score,
    sub_dimension_score,
    terminology_score,
)
from evaluator.rules.format import check_format
from evaluator.rules.metadata import check_literature
from evaluator.textutil import count_words, headings, split_chapters, split_passages

# --- textutil ----------------------------------------------------------------- #


def test_split_chapters_with_preamble() -> None:
    markdown = "Intro paragraph.\n\n# A\n\nText A.\n\n## B\n\nText B.\n"
    chapters = split_chapters(markdown)
    assert [c.title for c in chapters] == ["(preamble)", "A", "B"]
    assert chapters[1].text == "Text A."
    assert chapters[1].words == 2


def test_split_chapters_no_heading() -> None:
    chapters = split_chapters("Just text.")
    assert len(chapters) == 1
    assert chapters[0].title == "Document"


def test_headings_levels() -> None:
    items = headings("# A\n\ntext\n\n### C\n")
    assert items == [(1, "A"), (3, "C")]


def test_split_passages_respects_limit() -> None:
    paragraphs = ["a" * 60, "b" * 60, "c" * 150]
    passages = split_passages("\n\n".join(paragraphs), max_chars=100)
    assert all(len(p) <= 100 for p in passages)
    assert "".join(passages).count("a") == 60
    assert "".join(passages).count("c") == 150


# --- retriever ---------------------------------------------------------------- #


def _fulltext(paper_id: str, text: str) -> PaperFulltext:
    return PaperFulltext(
        paper_id=paper_id, sections=[PaperSection(section_id="sec_1", title="S", text=text)]
    )


def test_retriever_ranks_and_filters() -> None:
    retriever = LexicalRetriever.from_fulltexts(
        [
            _fulltext("p1", "gaussian splatting renders scenes"),
            _fulltext("p2", "transformer attention blocks"),
        ],
        max_passage_chars=100,
    )
    hits = retriever.retrieve("gaussian splatting", top_k=2)
    assert hits and hits[0].paper_id == "p1"
    assert hits[0].section_id == "sec_1"
    # paper_ids 过滤
    filtered = retriever.retrieve("attention", paper_ids=["p1"], top_k=2)
    assert filtered == []


def test_retriever_empty_query_or_corpus() -> None:
    retriever = LexicalRetriever.from_fulltexts([_fulltext("p1", "text")])
    assert retriever.retrieve("") == []
    assert LexicalRetriever([]).retrieve("anything") == []


def test_retriever_deterministic_order() -> None:
    fulltexts = [_fulltext(f"p{i}", f"alpha beta common{i}") for i in range(5)]
    retriever = LexicalRetriever.from_fulltexts(fulltexts)
    first = retriever.retrieve("alpha beta common", top_k=5)
    second = retriever.retrieve("alpha beta common", top_k=5)
    assert [(p.paper_id, p.section_id) for p in first] == [
        (p.paper_id, p.section_id) for p in second
    ]


def test_tokenize() -> None:
    assert tokenize("3D-GS, is Fun!") == ["3d", "gs", "is", "fun"]


# --- metrics ------------------------------------------------------------------ #


def test_factual_score() -> None:
    assert factual_score([2, 2, 1]) == pytest.approx(83.333, abs=0.01)
    assert factual_score([]) is None
    assert factual_score([0]) == 0.0


def test_citation_metrics_f1() -> None:
    metrics = citation_metrics(
        supports=[2, 2, 0], citation_worthy=4, cited_worthy=3, fabricated=1, total_citations=4
    )
    assert metrics["precision"] == pytest.approx(4 / 6)
    assert metrics["recall"] == pytest.approx(0.75)
    assert metrics["f1"] == pytest.approx(2 * (4 / 6) * 0.75 / (4 / 6 + 0.75))
    assert metrics["fabricated_citation_rate"] == pytest.approx(0.25)


def test_citation_metrics_empty() -> None:
    metrics = citation_metrics(
        supports=[], citation_worthy=0, cited_worthy=0, fabricated=0, total_citations=0
    )
    assert metrics["f1"] is None
    assert metrics["fabricated_citation_rate"] == 0.0


def test_coverage_score_weighted() -> None:
    score = coverage_score({"u1": (2, 2), "u2": (1, 0)})
    assert score == pytest.approx(2 * 2 / (2 * 3) * 100)


def test_irrelevant_penalty() -> None:
    assert apply_irrelevant_penalty(90.0, 0.1) == (90.0, None)
    score, note = apply_irrelevant_penalty(90.0, 0.3)
    assert score == pytest.approx(81.0) and note
    score, note = apply_irrelevant_penalty(90.0, 0.5)
    assert score == pytest.approx(63.0) and note


def test_sub_dimension_score() -> None:
    assert sub_dimension_score([4, 4, 4, 4]) == 100.0
    assert sub_dimension_score([0, 0, 0, 0]) == 0.0
    assert sub_dimension_score([2, 2]) == 50.0
    assert sub_dimension_score([]) is None


def test_quiz_dimension_score_weighting() -> None:
    # general 全对（10/10 → 100），topic 全错（0）→ 0.4×100
    assert quiz_dimension_score([10.0], [0.0]) == pytest.approx(40.0)
    # 只有一套时退化为该套
    assert quiz_dimension_score([], [5.0]) == pytest.approx(50.0)
    assert quiz_dimension_score([5.0], []) == pytest.approx(50.0)
    assert quiz_dimension_score([], []) is None


def test_terminology_score() -> None:
    # 1000 词 1 severe 1 moderate 1 minor → 100 - 30
    assert terminology_score(1, 1, 1, 1000) == pytest.approx(70.0)
    assert terminology_score(10, 0, 0, 500) == 0.0
    assert terminology_score(0, 0, 0, 100) == 100.0
    assert terminology_score(0, 0, 0, 0) is None


def test_literature_and_format_and_d8() -> None:
    assert literature_relevance_score([2, 1, 0]) == pytest.approx(50.0)
    assert literature_relevance_score([]) is None
    assert format_score(5, 6) == pytest.approx(500 / 6)
    assert format_score(0, 0) is None
    assert d8_composite(100.0, 100.0, 100.0) == 100.0
    # (3×60 + 2×90) / 5
    assert d8_composite(60.0, 90.0, None) == pytest.approx(72.0)
    assert d8_composite(None, None, None) is None


# --- rules -------------------------------------------------------------------- #


def test_check_format_clean_survey() -> None:
    result = check_format("# A\n\nText [1].\n", ["1"])
    assert result["issues"] == []
    assert result["passed"] == result["total"]


def test_check_format_violations() -> None:
    survey = "# A\n\nTODO fix this [1].\n\n```python\nx\n\n## A\n\nsame title [2]"
    result = check_format(survey, ["1"])
    issues = result["issues"]
    assert any("占位符" in issue for issue in issues)
    assert any("围栏" in issue for issue in issues)
    assert any("重复章节标题" in issue for issue in issues)
    assert any("未解析" in issue for issue in issues)


def test_check_format_heading_jump_and_missing() -> None:
    result = check_format("# A\n\ntext\n\n### C\n\nmore", ["1"])
    assert any("层级跳跃" in issue for issue in result["issues"])
    empty = check_format("no headings at all", [])
    assert any("标题" in issue for issue in empty["issues"])


def test_check_literature_relevance_and_duplicates() -> None:
    citations = [
        {"citation_id": "1", "paper_id": "2201.00001"},
        {"citation_id": "2", "paper_id": "2201.00001"},
        {"citation_id": "3", "paper_id": "2201.00003"},
        {"citation_id": "4", "paper_id": "9999.99999"},
    ]
    stats = check_literature(
        citations,
        "[1] and [3] and [4]",
        gold_papers={"2201.00001"},
        pool_papers={"2201.00003"},
    )
    assert stats.relevance == {"2201.00001": 2, "2201.00003": 1, "9999.99999": 0}
    assert stats.duplicates == ["2201.00001"]
    assert stats.relevance and max(stats.relevance.values()) == 2


def test_check_literature_concentration_and_notes() -> None:
    citations = [
        {"citation_id": "1", "paper_id": "p1"},
        {"citation_id": "2", "paper_id": "p2"},
        {"citation_id": "3", "paper_id": "p2"},
    ]
    stats = check_literature(citations, "", gold_papers={"p1", "p2"}, pool_papers=set())
    assert stats.concentration == pytest.approx(2 / 3)
    assert stats.notes  # 集中度 > 50%


def test_count_words() -> None:
    assert count_words("a b  c\n\nd") == 4
