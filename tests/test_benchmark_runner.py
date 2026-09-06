"""Benchmark Batch Runner 的集成测试：批量执行、失败隔离、汇总落盘。"""

from __future__ import annotations

import json
from pathlib import Path

from app.benchmark.runner import BenchmarkRunner
from app.config import AppConfig
from tests.conftest import SAMPLE_ANALYSIS_PAYLOAD, ScriptedProvider
from tests.test_pipeline import ORGANIZER_PAYLOAD, PLANNER_PAYLOAD, VERIFIER_PAYLOAD, WRITER_PAYLOAD

FULL_TASK_RESPONSES = [
    SAMPLE_ANALYSIS_PAYLOAD,
    SAMPLE_ANALYSIS_PAYLOAD,
    ORGANIZER_PAYLOAD,
    PLANNER_PAYLOAD,
    WRITER_PAYLOAD,
    WRITER_PAYLOAD,
    VERIFIER_PAYLOAD,
]


def write_manifest(tmp_path: Path, tasks: list[dict], name: str = "manifest.jsonl") -> Path:
    target = tmp_path / name
    target.write_text(
        "\n".join(json.dumps(task, ensure_ascii=False) for task in tasks) + "\n",
        encoding="utf-8",
    )
    return target


def make_papers_file(tmp_path: Path, name: str = "papers.json") -> Path:
    target = tmp_path / name
    target.write_text(
        json.dumps(
            [
                {"paper_id": "P001", "title": "Vision-Language Models for Driving", "year": 2024},
                {
                    "paper_id": "P002",
                    "title": "Language-Grounded Trajectory Prediction",
                    "year": 2025,
                },
            ]
        ),
        encoding="utf-8",
    )
    return target


def make_runner(tmp_path, prompt_dir, scripted_provider):
    config = AppConfig(root=tmp_path)
    config.paths.prompts_dir = str(prompt_dir)
    return BenchmarkRunner(scripted_provider([]), config), config


def test_run_batch_executes_all_tasks(tmp_path, prompt_dir, sample_papers, scripted_provider):
    papers = make_papers_file(tmp_path)
    manifest = write_manifest(
        tmp_path,
        [
            {"task_id": "task-a", "topic": "Topic A", "papers": papers.name},
            {"task_id": "task-b", "topic": "Topic B", "papers": papers.name},
        ],
    )
    runner, _ = make_runner(tmp_path, prompt_dir, scripted_provider)
    # ScriptedProvider 响应共享：为两个任务各准备一份完整响应序列
    runner.llm.responses.extend(FULL_TASK_RESPONSES * 2)

    summary = runner.run(manifest)

    assert summary["total"] == 2
    assert summary["passed"] == 2
    assert summary["failed"] == 0
    assert summary["total_token_usage"]["prompt"] == 140  # 每任务 70 prompt tokens
    task_a = summary["tasks"][0]
    assert task_a["status"] == "ok"
    assert task_a["task_id"] == "task-a"
    assert task_a["n_claims"] == 2
    assert task_a["n_citations"] == 1
    assert task_a["violations"] == []
    assert task_a["error"] == ""
    # 汇总落盘到 results/benchmark/<batch_id>/summary.json
    summary_path = tmp_path / "results" / "benchmark" / summary["batch_id"] / "summary.json"
    assert summary_path.is_file()
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary
    # 每个任务都有独立运行目录与 meta.json（含批次上下文）
    for record in summary["tasks"]:
        meta = json.loads(
            (tmp_path / "runs" / record["run_id"] / "meta.json").read_text(encoding="utf-8")
        )
        assert meta["benchmark"]["task_id"] == record["task_id"]


def test_run_batch_isolates_single_task_failure(
    tmp_path, prompt_dir, sample_papers, scripted_provider
):
    papers = make_papers_file(tmp_path)
    manifest = write_manifest(
        tmp_path,
        [
            {"task_id": "task-a", "topic": "Topic A", "papers": papers.name},
            {"task_id": "task-b", "topic": "Topic B", "papers": papers.name},
        ],
    )
    runner, _ = make_runner(tmp_path, prompt_dir, scripted_provider)
    # 只为第一个任务准备完整响应：第二个任务响应耗尽 → 失败，但不中断批次
    runner.llm.responses.extend(FULL_TASK_RESPONSES)

    summary = runner.run(manifest)

    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["tasks"][0]["status"] == "ok"
    assert summary["tasks"][1]["status"] == "failed"
    assert "AssertionError" in summary["tasks"][1]["error"]


def test_run_batch_respects_limit(tmp_path, prompt_dir, sample_papers, scripted_provider):
    papers = make_papers_file(tmp_path)
    manifest = write_manifest(
        tmp_path,
        [{"task_id": f"task-{i}", "topic": f"Topic {i}", "papers": papers.name} for i in range(3)],
    )
    config = AppConfig(root=tmp_path)
    config.paths.prompts_dir = str(prompt_dir)
    runner = BenchmarkRunner(scripted_provider([]), config, limit=1)
    runner.llm.responses.extend(FULL_TASK_RESPONSES)

    summary = runner.run(manifest)

    assert summary["total"] == 1
    assert summary["tasks"][0]["task_id"] == "task-0"


def test_cli_runs_batch_and_reports_exit_code(
    tmp_path, prompt_dir, sample_papers, scripted_provider, monkeypatch, capsys
):
    from app.benchmark import cli

    papers = make_papers_file(tmp_path)
    manifest = write_manifest(
        tmp_path,
        [{"task_id": "task-a", "topic": "Topic A", "papers": str(papers)}],
    )
    config = AppConfig(root=tmp_path)
    config.paths.prompts_dir = str(prompt_dir)

    class FakeAdapter(ScriptedProvider):
        @classmethod
        def from_config(cls, config, client=None):
            return cls(FULL_TASK_RESPONSES)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return None

    monkeypatch.setattr(cli, "Hy3Adapter", FakeAdapter)

    exit_code = cli.main(["--manifest", str(manifest)])

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "task-a" in captured
    assert "成功 1，失败 0" in captured


def test_cli_returns_1_when_task_fails(
    tmp_path, prompt_dir, sample_papers, scripted_provider, monkeypatch
):
    from app.benchmark import cli

    papers = make_papers_file(tmp_path)
    manifest = write_manifest(
        tmp_path,
        [{"task_id": "task-a", "topic": "Topic A", "papers": str(papers)}],
    )
    config = AppConfig(root=tmp_path)
    config.paths.prompts_dir = str(prompt_dir)

    class FakeAdapter(ScriptedProvider):
        @classmethod
        def from_config(cls, config, client=None):
            # 不准备任何响应 → 任务失败
            return cls([])

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return None

    monkeypatch.setattr(cli, "Hy3Adapter", FakeAdapter)

    exit_code = cli.main(["--manifest", str(manifest)])

    assert exit_code == 1
