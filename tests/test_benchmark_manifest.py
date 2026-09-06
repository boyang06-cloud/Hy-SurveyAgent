"""Benchmark 任务清单加载的单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.benchmark.manifest import load_manifest
from app.io.loader import LoaderError


def write_manifest(tmp_path: Path, entries: list[dict], name: str = "manifest.jsonl") -> Path:
    target = tmp_path / name
    if name.endswith(".jsonl"):
        target.write_text(
            "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
            encoding="utf-8",
        )
    else:
        target.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return target


def make_papers_file(tmp_path: Path, name: str = "papers.json") -> Path:
    target = tmp_path / name
    target.write_text(
        json.dumps([{"paper_id": "P001", "title": "Paper One", "year": 2024}]),
        encoding="utf-8",
    )
    return target


def test_load_manifest_resolves_relative_to_manifest_dir(tmp_path: Path) -> None:
    papers = make_papers_file(tmp_path)
    manifest = write_manifest(
        tmp_path,
        [
            {"topic": "VLMs for Driving", "papers": papers.name},
            {"task_id": "custom-id", "topic": "Trajectory Prediction", "papers": str(papers)},
        ],
    )

    tasks = load_manifest(manifest, search_paths=[tmp_path])

    assert [task.task_id for task in tasks] == ["vlms-for-driving", "custom-id"]
    assert tasks[0].papers == str(papers)
    assert tasks[1].topic == "Trajectory Prediction"


def test_load_manifest_dedupes_derived_ids(tmp_path: Path) -> None:
    papers = make_papers_file(tmp_path)
    manifest = write_manifest(
        tmp_path,
        [
            {"topic": "Same Topic!", "papers": papers.name},
            {"topic": "Same Topic?", "papers": papers.name},
        ],
    )

    tasks = load_manifest(manifest, search_paths=[tmp_path])

    assert [task.task_id for task in tasks] == ["same-topic", "same-topic-2"]


def test_load_manifest_missing_papers_file(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path, [{"topic": "Topic", "papers": "missing.json"}])
    with pytest.raises(LoaderError, match="论文文件不存在"):
        load_manifest(manifest, search_paths=[tmp_path])


def test_load_manifest_rejects_missing_topic(tmp_path: Path) -> None:
    papers = make_papers_file(tmp_path)
    manifest = write_manifest(tmp_path, [{"papers": papers.name}])
    with pytest.raises(LoaderError, match="缺少 topic"):
        load_manifest(manifest, search_paths=[tmp_path])


def test_load_manifest_rejects_empty(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path, [])
    with pytest.raises(LoaderError, match="清单为空"):
        load_manifest(manifest, search_paths=[tmp_path])


def test_load_manifest_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LoaderError, match="清单文件不存在"):
        load_manifest(tmp_path / "nope.jsonl", search_paths=[tmp_path])


def test_load_manifest_supports_yaml(tmp_path: Path) -> None:
    papers = make_papers_file(tmp_path)
    target = tmp_path / "manifest.yaml"
    target.write_text(
        "- topic: VLMs for Driving\n"
        f"  papers: {papers}\n"
        "  research_questions:\n"
        "    - How are VLMs applied?\n",
        encoding="utf-8",
    )

    tasks = load_manifest(target, search_paths=[tmp_path])

    assert len(tasks) == 1
    assert tasks[0].research_questions == ["How are VLMs applied?"]
