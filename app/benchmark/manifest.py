"""Benchmark 任务清单（manifest）加载。

清单文件支持 JSONL（每行一个任务）/ JSON 数组 / YAML 列表，每个条目：
    {"task_id": "...", "topic": "...", "papers": "path/to/papers.json",
     "research_questions": ["..."]}

约定（docs 第 33 节 Benchmark Test）：
    - `topic + papers` 必填：Benchmark 模式使用固定 Source Paper Set，运行期不检索；
    - `task_id` 缺省时由 topic 生成 slug，重复自动加后缀；
    - `papers` 路径依次在清单所在目录与项目根目录下解析。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.io.loader import LoaderError


@dataclass
class BenchmarkTask:
    """一个批量运行任务：固定 Topic + 固定 Source Paper Set。"""

    task_id: str
    topic: str
    papers: str
    research_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "topic": self.topic,
            "papers": self.papers,
            "research_questions": list(self.research_questions),
        }


def load_manifest(
    path: str | Path,
    *,
    search_paths: list[Path] | None = None,
) -> list[BenchmarkTask]:
    """加载 Benchmark 任务清单；格式或内容非法时抛 LoaderError。"""
    file_path = Path(path)
    if not file_path.is_file():
        raise LoaderError(f"清单文件不存在：{file_path}")

    entries = _read_entries(file_path)
    if not entries:
        raise LoaderError(f"清单为空：{file_path}")

    tasks: list[BenchmarkTask] = []
    used_ids: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise LoaderError(f"{file_path} 第 {index} 条记录不是对象。")
        topic = str(entry.get("topic") or "").strip()
        papers = str(entry.get("papers") or "").strip()
        if not topic:
            raise LoaderError(f"{file_path} 第 {index} 条记录缺少 topic。")
        if not papers:
            raise LoaderError(f"{file_path} 第 {index} 条记录缺少 papers。")

        task_id = str(entry.get("task_id") or "").strip() or _slugify(topic)
        task_id = _dedupe_id(task_id, used_ids)
        questions = [
            str(q).strip() for q in entry.get("research_questions") or [] if str(q).strip()
        ]

        resolved = _resolve_papers(papers, search_paths or [])
        if resolved is None:
            raise LoaderError(f"任务 {task_id} 的论文文件不存在：{papers}")

        tasks.append(
            BenchmarkTask(
                task_id=task_id,
                topic=topic,
                papers=str(resolved),
                research_questions=questions,
            )
        )
    return tasks


def _read_entries(file_path: Path) -> list[Any]:
    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix == ".jsonl":
        entries: list[Any] = []
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except ValueError as exc:
                raise LoaderError(f"{file_path} 第 {number} 行不是合法 JSON：{exc}") from exc
        return entries
    if suffix in {".yaml", ".yml"}:
        loaded = yaml.safe_load(text)
    else:
        try:
            loaded = json.loads(text)
        except ValueError as exc:
            raise LoaderError(f"{file_path} 不是合法 JSON：{exc}") from exc
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        raise LoaderError(f"{file_path} 的内容应为数组。")
    return list(loaded)


def _slugify(topic: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", topic.lower()).strip("-")
    return (slug or "task")[:48]


def _dedupe_id(task_id: str, used_ids: set[str]) -> str:
    candidate = task_id
    counter = 2
    while candidate in used_ids:
        candidate = f"{task_id}-{counter}"
        counter += 1
    used_ids.add(candidate)
    return candidate


def _resolve_papers(papers: str, search_paths: list[Path]) -> Path | None:
    candidate = Path(papers)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    for base in search_paths:
        resolved = base / candidate
        if resolved.is_file():
            return resolved
    return None
