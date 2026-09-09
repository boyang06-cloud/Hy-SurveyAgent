"""输入加载：任务输入与 Source Papers。

Benchmark 模式下论文来自固定文件，不经任何实时检索，保证实验输入完全一致。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.types import Paper, PaperSet, TaskInput


class LoaderError(ValueError):
    """输入文件格式或内容不合法。"""


def read_records(path: str | Path) -> list[dict[str, Any]]:
    """读取论文记录列表，支持 JSON / JSONL / YAML。

    JSON 支持两种形态：数组，或 ``{"papers": [...]}``。
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise LoaderError(f"输入文件不存在：{file_path}")

    suffix = file_path.suffix.lower()
    text = file_path.read_text(encoding="utf-8")

    if suffix == ".jsonl":
        records: list[Any] = []
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except ValueError as exc:
                raise LoaderError(f"{file_path} 第 {number} 行不是合法 JSON：{exc}") from exc
        return _as_records(records, file_path)

    if suffix in {".yaml", ".yml"}:
        return _as_records(yaml.safe_load(text), file_path)

    try:
        loaded = json.loads(text)
    except ValueError as exc:
        raise LoaderError(f"{file_path} 不是合法 JSON：{exc}") from exc
    if isinstance(loaded, dict):
        loaded = loaded.get("papers", [])
    return _as_records(loaded, file_path)


def _as_records(loaded: Any, file_path: Path) -> list[dict[str, Any]]:
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        raise LoaderError(f"{file_path} 的内容应为数组，实际为 {type(loaded).__name__}")
    for index, item in enumerate(loaded, start=1):
        if not isinstance(item, dict):
            raise LoaderError(f"{file_path} 第 {index} 条记录不是对象。")
    return list(loaded)


def normalize_title(title: str) -> str:
    """标题归一化键（小写、去标点与空白），用于去重。"""
    return re.sub(r"[^a-z0-9一-鿿]+", "", title.lower())


def load_papers(
    path: str | Path,
    *,
    limit: int | None = None,
    deduplicate: bool = True,
) -> PaperSet:
    """加载并归一化论文集合：去重、丢弃无标题条目、补齐缺失的 paper_id。"""
    records = read_records(path)
    if limit is not None:
        records = records[: max(0, limit)]

    papers: list[Paper] = []
    seen: set[str] = set()
    duplicates = 0

    for record in records:
        if not str(record.get("title") or "").strip():
            continue  # 无标题记录无法被引用，直接丢弃
        paper = Paper.from_dict(record)
        if deduplicate:
            key = normalize_title(paper.title) or paper.paper_id
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
        papers.append(paper)

    return PaperSet(papers=_assign_missing_ids(papers), duplicates_removed=duplicates)


def _assign_missing_ids(papers: list[Paper]) -> list[Paper]:
    used = {paper.paper_id for paper in papers if paper.paper_id}
    counter = 1
    for paper in papers:
        if paper.paper_id:
            continue
        while f"P{counter:03d}" in used:
            counter += 1
        paper.paper_id = f"P{counter:03d}"
        used.add(paper.paper_id)
    return papers


def load_task_input(path: str | Path) -> TaskInput:
    """加载 YAML / JSON 任务文件。"""
    file_path = Path(path)
    if not file_path.is_file():
        raise LoaderError(f"任务文件不存在：{file_path}")
    text = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() in {".yaml", ".yml"}:
        loaded = yaml.safe_load(text)
    else:
        try:
            loaded = json.loads(text)
        except ValueError as exc:
            raise LoaderError(f"{file_path} 不是合法 JSON：{exc}") from exc
    if not isinstance(loaded, dict):
        raise LoaderError(f"{file_path} 的内容应为映射。")

    time_range = loaded.get("time_range")
    if time_range is not None and not isinstance(time_range, dict):
        raise LoaderError("time_range 应为 {start, end} 映射。")

    return TaskInput(
        topic=str(loaded.get("topic") or "").strip(),
        research_questions=[str(q) for q in _as_list(loaded.get("research_questions"))],
        paper_ids=[str(p) for p in _as_list(loaded.get("paper_ids"))],
        time_range=time_range,
        output_style=str(loaded.get("output_style") or "academic_survey"),
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]
