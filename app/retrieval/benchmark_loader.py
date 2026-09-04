"""Benchmark 数据加载：把固定 Source Paper Set 包装成检索器。"""

from __future__ import annotations

from pathlib import Path

from app.core.types import PaperSet
from app.io.loader import load_papers
from app.retrieval.retriever import FixedSetRetriever


def load_benchmark_source(
    path: str | Path,
    *,
    limit: int | None = None,
) -> PaperSet:
    """加载固定 Source Paper Set（Benchmark 模式的唯一数据来源）。"""
    return load_papers(path, limit=limit)


def build_benchmark_retriever(
    path: str | Path,
    *,
    limit: int | None = None,
) -> FixedSetRetriever:
    """构造 Benchmark 模式使用的检索器：数据固定，运行期不再访问网络。"""
    return FixedSetRetriever(load_benchmark_source(path, limit=limit))
