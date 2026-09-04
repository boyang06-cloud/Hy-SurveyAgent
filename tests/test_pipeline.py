"""Pipeline 集成测试：端到端跑通 Topic + Papers → Analysis → Survey，并校验 runs/ 产物。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.config import AppConfig
from app.core.pipeline import build_result, run_pipeline
from app.core.types import PaperAnalysis, PaperSet, SurveyState, TaskInput
from app.io.exporter import RunWriter
from app.io.loader import load_papers
from tests.conftest import SAMPLE_ANALYSIS_PAYLOAD

SURVEY_PAYLOAD = {
    "survey_markdown": "## Introduction\nVLMs are applied to driving [1].",
    "claims": [{"text": "VLMs are applied to driving", "citations": ["P001"]}],
    "citations": [{"citation_id": "[1]", "paper_id": "P001"}],
}

STAGE_ORDER = [
    "literature_manager",
    "paper_reader",
    "survey_writer",
    "finalize",
]


def build_config(root: Path, prompt_dir: Path) -> AppConfig:
    config = AppConfig(root=root)
    config.paths.prompts_dir = str(prompt_dir)
    return config


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_stage_logs(run: RunWriter) -> list[dict]:
    return [
        json.loads(line)
        for line in run.path("logs/stages.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_run_pipeline_writes_all_artifacts(
    tmp_path: Path,
    prompt_dir: Path,
    sample_papers: PaperSet,
    scripted_provider,
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step2-001", topic="Unit Topic")
    llm = scripted_provider(
        [SAMPLE_ANALYSIS_PAYLOAD, SAMPLE_ANALYSIS_PAYLOAD, SURVEY_PAYLOAD]
    )

    payload = asyncio.run(
        run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
    )

    assert set(payload) == {"task", "papers", "survey", "claims", "citations", "evidence_map"}
    assert payload["task"]["topic"] == "Unit Topic"
    assert len(payload["papers"]) == 2
    assert payload["citations"][0]["paper_id"] == "P001"
    assert payload["claims"][0]["claim_id"] == "C001"

    analyses = read_json(run.path("analyses.json"))
    assert [item["paper_id"] for item in analyses] == ["P001", "P002"]
    assert analyses[0]["claims"][0]["claim_id"] == "P001-C1"
    assert len(read_json(run.path("papers.json"))) == 2
    assert read_json(run.path("result.json")) == payload
    assert run.path("draft.md").read_text(encoding="utf-8") == payload["survey"]
    assert run.path("final.md").read_text(encoding="utf-8") == payload["survey"]
    assert len(read_json(run.path("claims.json"))["claims"]) == 1
    assert read_json(run.path("verification.json"))["summary"]["total_claims"] == 1


def test_run_pipeline_logs_every_stage_with_usage(
    tmp_path: Path,
    prompt_dir: Path,
    sample_papers: PaperSet,
    scripted_provider,
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step2-002")
    llm = scripted_provider(
        [SAMPLE_ANALYSIS_PAYLOAD, SAMPLE_ANALYSIS_PAYLOAD, SURVEY_PAYLOAD]
    )

    asyncio.run(
        run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
    )

    records = read_stage_logs(run)
    assert [record["stage"] for record in records] == STAGE_ORDER
    assert all(record["error"] is None for record in records)
    # Reader: 2 篇论文各一次调用；Writer: 1 次调用
    assert records[1]["token_usage"] == {"prompt": 20, "completion": 40}
    assert records[2]["token_usage"] == {"prompt": 10, "completion": 20}


def test_run_pipeline_continues_when_one_paper_fails(
    tmp_path: Path,
    prompt_dir: Path,
    sample_papers: PaperSet,
    scripted_provider,
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step2-003")
    llm = scripted_provider(["bad", "bad", SAMPLE_ANALYSIS_PAYLOAD, SURVEY_PAYLOAD])

    payload = asyncio.run(
        run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
    )

    analyses = read_json(run.path("analyses.json"))
    assert analyses[0]["status"] == PaperAnalysis.STATUS_UNAVAILABLE
    assert analyses[1]["status"] == PaperAnalysis.STATUS_OK
    assert payload["survey"]


def test_run_pipeline_dry_run_skips_model(
    tmp_path: Path, prompt_dir: Path, sample_papers: PaperSet
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step2-004")

    payload = asyncio.run(
        run_pipeline(
            None, TaskInput(topic="Unit Topic"), sample_papers, run, config=config, dry_run=True
        )
    )

    reader_prompt = run.path("prompts/paper_reader.rendered.md").read_text(encoding="utf-8")
    writer_prompt = run.path("prompts/writer.rendered.md").read_text(encoding="utf-8")
    assert "Vision-Language Models for Driving" in reader_prompt
    assert "Unit Topic" in writer_prompt
    assert read_json(run.path("analyses.json")) == []
    assert payload["survey"] == ""
    assert payload["citations"] == []


def test_run_pipeline_requires_provider_without_dry_run(
    tmp_path: Path, prompt_dir: Path, sample_papers: PaperSet
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step2-005")
    with pytest.raises(ValueError, match="LLMProvider"):
        asyncio.run(
            run_pipeline(None, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
        )


def test_run_pipeline_records_stage_error(
    tmp_path: Path, prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step2-006")
    # Reader 两篇都失败 → Stage 失败并记录 error
    llm = scripted_provider(["bad", "bad", "bad", "bad"])

    with pytest.raises(Exception, match="全部 2 篇论文读取失败"):
        asyncio.run(
            run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
        )

    records = read_stage_logs(run)
    assert records[-1]["stage"] == "paper_reader"
    assert records[-1]["error"]


def test_build_result_matches_evaluation_contract(papers_file: Path) -> None:
    papers = load_papers(papers_file)
    state = SurveyState(task=TaskInput(topic="Unit Topic"), papers=list(papers.papers))
    result = build_result(TaskInput(topic="Unit Topic"), state)
    assert result["evidence_map"] == []
    assert [paper["paper_id"] for paper in result["papers"]] == ["P001", "P002"]
