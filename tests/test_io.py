"""输入输出模块的单元测试：论文加载归一化、任务文件、Prompt 渲染与运行产物落盘。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import AppConfig
from app.io.exporter import RunWriter
from app.io.loader import LoaderError, load_papers, load_task_input
from app.prompts.loader import PromptError, PromptLoader


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_papers_from_array(tmp_path: Path) -> None:
    path = write_json(
        tmp_path / "papers.json",
        [{"title": "Paper One", "year": "2024", "authors": "Solo Author"}],
    )
    papers = load_papers(path)
    assert len(papers) == 1
    assert papers.papers[0].paper_id == "P001"
    assert papers.papers[0].year == 2024
    assert papers.papers[0].authors == ["Solo Author"]


def test_load_papers_from_papers_key(tmp_path: Path) -> None:
    path = write_json(tmp_path / "papers.json", {"papers": [{"title": "A"}, {"title": "B"}]})
    assert len(load_papers(path)) == 2


def test_load_papers_from_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "papers.jsonl"
    path.write_text('{"title": "A"}\n\n{"title": "B"}\n', encoding="utf-8")
    assert len(load_papers(path)) == 2


def test_load_papers_deduplicates_by_title(tmp_path: Path) -> None:
    path = write_json(
        tmp_path / "papers.json",
        [{"title": "Same Title", "year": 2024}, {"title": "same title!", "year": 2025}],
    )
    papers = load_papers(path)
    assert len(papers) == 1
    assert papers.duplicates_removed == 1


def test_load_papers_drops_records_without_title(tmp_path: Path) -> None:
    path = write_json(tmp_path / "papers.json", [{"year": 2024}, {"title": "Keep"}])
    papers = load_papers(path)
    assert [paper.title for paper in papers] == ["Keep"]


def test_load_papers_assigns_missing_ids(tmp_path: Path) -> None:
    path = write_json(
        tmp_path / "papers.json",
        [{"title": "A", "paper_id": "P002"}, {"title": "B"}, {"title": "C"}],
    )
    assert [paper.paper_id for paper in load_papers(path)] == ["P002", "P001", "P003"]


def test_load_papers_applies_limit(tmp_path: Path) -> None:
    path = write_json(tmp_path / "papers.json", [{"title": "A"}, {"title": "B"}, {"title": "C"}])
    assert len(load_papers(path, limit=2)) == 2


def test_load_papers_rejects_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "papers.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(LoaderError):
        load_papers(path)


def test_load_task_input(tmp_path: Path) -> None:
    path = tmp_path / "task.yaml"
    path.write_text(
        "topic: Test Topic\n"
        "research_questions:\n  - Q1\n  - Q2\n"
        "time_range:\n  start: 2020\n  end: 2026\n",
        encoding="utf-8",
    )
    task = load_task_input(path)
    assert task.topic == "Test Topic"
    assert task.research_questions == ["Q1", "Q2"]
    assert task.time_range == {"start": 2020, "end": 2026}


def test_prompt_loader_renders_and_reports_missing(tmp_path: Path) -> None:
    target = tmp_path / "demo.md"
    target.write_text("> version: 1.2.3\nTopic: {{ topic }}\n", encoding="utf-8")
    loader = PromptLoader(tmp_path)
    assert loader.render("demo", topic="X") == "> version: 1.2.3\nTopic: X\n"
    assert loader.version("demo") == "1.2.3"
    assert len(loader.digest("demo")) == 12
    with pytest.raises(PromptError, match="未渲染"):
        loader.render("demo")
    with pytest.raises(PromptError, match="不存在"):
        loader.load("missing")


def test_run_writer_creates_layout_and_logs(tmp_path: Path) -> None:
    run = RunWriter.create(tmp_path, "runs", None, topic="Unit Topic")
    run.write_json("task.json", {"topic": "Unit Topic"})
    with run.stage("unit_stage", "task.json", "out.json") as stats:
        stats["token_usage"] = {"prompt": 1, "completion": 2}
    run.write_text("final.md", "body")

    assert (run.run_dir / "task.json").is_file()
    assert (run.run_dir / "final.md").read_text(encoding="utf-8") == "body"
    assert run.task_id.startswith("t-")
    lines = (run.run_dir / "logs" / "stages.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["stage"] == "unit_stage"
    assert record["token_usage"] == {"prompt": 1, "completion": 2}
    assert record["error"] is None


def test_run_writer_logs_error_and_reraises(tmp_path: Path) -> None:
    run = RunWriter.create(tmp_path, "runs", "t-unit-001")
    with pytest.raises(RuntimeError):
        with run.stage("boom", "in", "out"):
            raise RuntimeError("stage failed")
    record = json.loads(
        (run.run_dir / "logs" / "stages.jsonl").read_text(encoding="utf-8").strip()
    )
    assert record["error"] == "RuntimeError: stage failed"


def test_run_writer_increments_task_id(tmp_path: Path) -> None:
    first = RunWriter.create(tmp_path, "runs")
    second = RunWriter.create(tmp_path, "runs")
    assert first.task_id != second.task_id


def test_app_config_resolves_paths(tmp_path: Path) -> None:
    config = AppConfig(root=tmp_path)
    assert config.prompts_dir() == tmp_path / "app" / "prompts"
    assert config.runs_dir() == tmp_path / "runs"
