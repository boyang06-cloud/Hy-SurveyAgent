"""Literature Manager 的单元测试：固定集检索、过滤与动态检索边界。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.types import Paper, PaperSet, TaskInput
from app.retrieval.benchmark_loader import build_benchmark_retriever, load_benchmark_source
from app.retrieval.retriever import DynamicRetriever, FixedSetRetriever, RetrieverError


def write_papers(path: Path, records: list[dict]) -> Path:
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return path


def make_papers() -> PaperSet:
    return PaperSet(
        papers=[
            Paper(paper_id="P001", title="A", year=2019),
            Paper(paper_id="P002", title="B", year=2024),
            Paper(paper_id="P003", title="C", year=None),
        ]
    )


def test_fixed_set_retriever_returns_all_without_filters() -> None:
    papers = make_papers()
    result = FixedSetRetriever(papers).retrieve(TaskInput(topic="T"))
    assert [paper.paper_id for paper in result] == ["P001", "P002", "P003"]
    assert result.filtered_out == 0


def test_fixed_set_retriever_filters_by_paper_ids() -> None:
    result = FixedSetRetriever(make_papers()).retrieve(
        TaskInput(topic="T", paper_ids=["P002", "P999"])
    )
    assert [paper.paper_id for paper in result] == ["P002"]
    assert result.filtered_out == 2


def test_fixed_set_retriever_filters_by_time_range() -> None:
    result = FixedSetRetriever(make_papers()).retrieve(
        TaskInput(topic="T", time_range={"start": 2020, "end": 2026})
    )
    # 年份未知的论文保留，避免误删
    assert [paper.paper_id for paper in result] == ["P002", "P003"]
    assert result.filtered_out == 1


def test_fixed_set_retriever_preserves_duplicate_stats() -> None:
    papers = make_papers()
    papers.duplicates_removed = 3
    result = FixedSetRetriever(papers).retrieve(TaskInput(topic="T"))
    assert result.duplicates_removed == 3


def test_dynamic_retriever_is_not_available_yet() -> None:
    with pytest.raises(RetrieverError, match="V1"):
        DynamicRetriever().retrieve(TaskInput(topic="T"))


def test_benchmark_loader_reads_fixed_source(tmp_path: Path) -> None:
    path = write_papers(
        tmp_path / "papers.json",
        [{"title": "A"}, {"title": "B"}, {"title": "A"}],
    )
    papers = load_benchmark_source(path)
    assert len(papers) == 2
    assert papers.duplicates_removed == 1


def test_benchmark_retriever_applies_task_filters(tmp_path: Path) -> None:
    path = write_papers(
        tmp_path / "papers.json",
        [
            {"paper_id": "P001", "title": "Old", "year": 2015},
            {"paper_id": "P002", "title": "New", "year": 2025},
        ],
    )
    retriever = build_benchmark_retriever(path)
    result = retriever.retrieve(TaskInput(topic="T", time_range={"start": 2020, "end": 2026}))
    assert [paper.paper_id for paper in result] == ["P002"]
