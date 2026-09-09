"""Web 工作台的受限文件读取和上传解析。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.core.types import PaperSet
from app.io.loader import LoaderError, load_papers

ARTIFACTS = frozenset(
    {
        "task.json",
        "papers.json",
        "analyses.json",
        "knowledge.json",
        "outline.json",
        "draft.md",
        "claims.json",
        "verification.json",
        "final.md",
        "result.json",
    }
)


def read_json(path: Path, default: Any = None) -> Any:
    """运行中可能读到尚未写完的 JSON，下次轮询重试。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def run_path(base: Path, run_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", run_id):
        raise FileNotFoundError("任务不存在")
    target = base / run_id
    if target.is_symlink() or not target.is_dir() or target.resolve().parent != base.resolve():
        raise FileNotFoundError("任务不存在")
    return target


def artifact_path(base: Path, run_id: str, name: str) -> Path:
    if name not in ARTIFACTS:
        raise FileNotFoundError("产物不存在")
    folder = run_path(base, run_id)
    target = folder / name
    if target.is_symlink() or not target.is_file():
        raise FileNotFoundError("产物尚未生成")
    return target


def parse_upload(filename: str, content: str) -> PaperSet:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".json", ".jsonl", ".yaml", ".yml"}:
        raise LoaderError("请选择 JSON、JSONL 或 YAML 论文集文件。")
    with TemporaryDirectory(prefix="hy-survey-upload-") as directory:
        path = Path(directory) / f"papers{suffix}"
        path.write_text(content, encoding="utf-8")
        try:
            papers = load_papers(path)
        except Exception as exc:
            raise LoaderError("论文集格式无法解析，请检查文件结构与字段。") from exc
    if not papers.papers:
        raise LoaderError("论文集为空；每条论文至少需要 title，并建议提供 content 或 abstract。")
    ids = [paper.paper_id for paper in papers]
    if len(ids) != len(set(ids)):
        raise LoaderError("论文 paper_id 重复，请为每篇论文设置唯一 ID。")
    if len(papers.papers) > 200:
        raise LoaderError("单个任务最多支持 200 篇论文，请拆分论文集。")
    return papers


def stage_records(folder: Path) -> list[dict[str, Any]]:
    path = folder / "logs" / "stages.jsonl"
    if path.is_symlink() or path.parent.is_symlink():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(
                {
                    "stage": record.get("stage"),
                    "latency_ms": record.get("latency_ms", 0),
                    "token_usage": record.get("token_usage", {}),
                    "error": bool(record.get("error")),
                    "timestamp": record.get("timestamp", ""),
                }
            )
    return records
