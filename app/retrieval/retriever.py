"""文献获取抽象。

Benchmark 模式下走 `FixedSetRetriever`（固定 Source Paper Set），
动态检索属于 V1 特性，当前显式报错，避免悄悄引入不可复现的在线检索结果。
"""

from __future__ import annotations

from typing import Protocol

from app.core.types import PaperSet, TaskInput


class RetrieverError(RuntimeError):
    """文献获取失败，或使用了当前版本未实现的检索方式。"""


class PaperRetriever(Protocol):
    """文献获取接口。实现只需返回归一化后的 PaperSet。"""

    def retrieve(self, task: TaskInput) -> PaperSet: ...


class FixedSetRetriever:
    """固定论文集检索器（Benchmark 模式）。

    按 `task.paper_ids` / `task.time_range` 过滤，但绝不联网，输入完全可复现。
    """

    def __init__(self, papers: PaperSet) -> None:
        self.papers = papers

    def retrieve(self, task: TaskInput) -> PaperSet:
        selected = list(self.papers.papers)
        total = len(selected)

        if task.paper_ids:
            wanted = set(task.paper_ids)
            selected = [paper for paper in selected if paper.paper_id in wanted]

        if task.time_range:
            start = task.time_range.get("start")
            end = task.time_range.get("end")
            selected = [paper for paper in selected if _in_range(paper.year, start, end)]

        return PaperSet(
            papers=selected,
            duplicates_removed=self.papers.duplicates_removed,
            filtered_out=total - len(selected),
        )


class DynamicRetriever:
    """动态检索器（V1 特性，尚未实现）。"""

    def retrieve(self, task: TaskInput) -> PaperSet:
        raise RetrieverError(
            "动态检索属于 V1 特性，当前版本仅支持固定 Source Paper Set（Benchmark 模式）。"
        )


def _in_range(year: int | None, start: int | None, end: int | None) -> bool:
    """年份未知时保留该论文（无法判定，交由后续阶段处理）。"""
    if year is None:
        return True
    if start is not None and year < start:
        return False
    if end is not None and year > end:
        return False
    return True
