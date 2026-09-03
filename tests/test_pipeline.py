"""Step 1 Pipeline 的集成测试：端到端跑通 Topic + Papers → Survey，并校验 runs/ 产物。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.config import AppConfig
from app.core.pipeline import build_result, run_step1
from app.core.types import PaperSet, SurveyState, TaskInput
from app.io.exporter import RunWriter
from app.io.loader import load_papers

SURVEY_PAYLOAD = {
    "survey_markdown": "## Introduction\nVLMs are applied to driving [1].",
    "claims": [{"text": "VLMs are applied to driving", "citations": ["P001"]}],
    "citations": [{"citation_id": "[1]", "paper_id": "P001"}],
}


def build_config(root: Path, prompt_dir: Path) -> AppConfig:
    config = AppConfig(root=root)
    config.paths.prompts_dir = str(prompt_dir)
    return config


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_run_step1_writes_all_artifacts(
    tmp_path: Path, prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step1-001", topic="Unit Topic")
    llm = scripted_provider([SURVEY_PAYLOAD])

    payload = asyncio.run(
        run_step1(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
    )

    assert set(payload) == {"task", "papers", "survey", "claims", "citations", "evidence_map"}
    assert payload["task"]["topic"] == "Unit Topic"
    assert len(payload["papers"]) == 2
    assert payload["citations"][0]["paper_id"] == "P001"
    assert payload["claims"][0]["claim_id"] == "C001"

    assert len(read_json(run.path("papers.json"))) == 2
    assert read_json(run.path("result.json")) == payload
    assert run.path("draft.md").read_text(encoding="utf-8") == payload["survey"]
    assert run.path("final.md").read_text(encoding="utf-8") == payload["survey"]
    assert len(read_json(run.path("claims.json"))["claims"]) == 1
    assert read_json(run.path("verification.json"))["summary"]["total_claims"] == 1


def test_run_step1_logs_every_stage(
    tmp_path: Path, prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step1-002")
    llm = scripted_provider([SURVEY_PAYLOAD])

    asyncio.run(
        run_step1(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
    )

    records = [
        json.loads(line)
        for line in run.path("logs/stages.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [record["stage"] for record in records] == [
        "literature_manager",
        "survey_writer",
        "finalize",
    ]
    assert all(record["error"] is None for record in records)
    assert records[1]["token_usage"] == {"prompt": 10, "completion": 20}


def test_run_step1_dry_run_skips_model(
    tmp_path: Path, prompt_dir: Path, sample_papers: PaperSet
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step1-003")

    payload = asyncio.run(
        run_step1(
            None, TaskInput(topic="Unit Topic"), sample_papers, run, config=config, dry_run=True
        )
    )

    rendered = run.path("prompts/writer.rendered.md").read_text(encoding="utf-8")
    assert "Unit Topic" in rendered
    assert "[P001]" in rendered
    assert payload["survey"] == ""
    assert payload["citations"] == []


def test_run_step1_requires_provider_without_dry_run(
    tmp_path: Path, prompt_dir: Path, sample_papers: PaperSet
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step1-004")
    with pytest.raises(ValueError, match="LLMProvider"):
        asyncio.run(
            run_step1(None, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
        )


def test_run_step1_records_stage_error(
    tmp_path: Path, prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step1-005")
    llm = scripted_provider(["not a json object", "still not json"])

    with pytest.raises(Exception, match="JSON"):
        asyncio.run(
            run_step1(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
        )

    records = [
        json.loads(line)
        for line in run.path("logs/stages.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records[-1]["error"]


def test_build_result_matches_evaluation_contract(
    prompt_dir: Path, papers_file: Path
) -> None:
    papers = load_papers(papers_file)
    state = SurveyState(task=TaskInput(topic="Unit Topic"), papers=list(papers.papers))
    result = build_result(TaskInput(topic="Unit Topic"), state)
    assert result["evidence_map"] == []
    assert [paper["paper_id"] for paper in result["papers"]] == ["P001", "P002"]
