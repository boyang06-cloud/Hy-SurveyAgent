"""Pipeline 集成测试：端到端跑通多阶段 Workflow，并校验 runs/ 产物。"""

import asyncio
import json

import pytest

from app.config import AppConfig
from app.core.pipeline import build_result, run_pipeline
from app.core.types import PaperAnalysis, SurveyState, TaskInput
from app.io.exporter import RunWriter
from app.io.loader import load_papers
from tests.conftest import SAMPLE_ANALYSIS_PAYLOAD

ORGANIZER_PAYLOAD = {
    "topics": ["Language-grounded driving"],
    "methods": [{"name": "Instruction-conditioned", "papers": ["P001", "P002"]}],
    "problems": [{"name": "Open-loop evaluation", "papers": ["P001", "P002"]}],
    "datasets": [{"name": "nuScenes", "papers": ["P001"]}],
    "papers": ["P001", "P002"],
    "relations": [{"source": "P001", "relation": "extends", "target": "P002"}],
}
PLANNER_PAYLOAD = {
    "sections": [
        {
            "title": "Introduction",
            "purpose": "Motivate language-grounded driving",
            "papers": ["P001"],
            "key_claims": ["P001-C1"],
        },
        {"title": "Taxonomy", "purpose": "Classify existing methods", "papers": ["P002"]},
    ]
}
WRITER_PAYLOAD = {
    "content": "Vision-language models support driving [[P001]].",
    "claims": [{"text": "VLMs support driving", "citations": ["P001"]}],
}
VERIFIER_PAYLOAD = {
    "results": [
        {
            "claim_id": "C001",
            "citation": "P001",
            "support": True,
            "evidence": "Applies a vision-language model to driving scenes and reports results.",
            "confidence": 0.9,
        }
    ]
}

STAGE_ORDER = [
    "literature_manager",
    "paper_reader",
    "knowledge_organizer",
    "outline_planner",
    "survey_writer",
    "citation_verifier",
    "finalize",
]


def build_config(root, prompt_dir):
    config = AppConfig(root=root)
    config.paths.prompts_dir = str(prompt_dir)
    return config


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_stage_logs(run):
    return [
        json.loads(line)
        for line in run.path("logs/stages.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def scripted_step2_responses(scripted_provider):
    """Reader 2 次 + Organizer 1 次 + Planner 1 次 + Writer 2 次 + Verifier 1 次。"""
    return scripted_provider(
        [
            SAMPLE_ANALYSIS_PAYLOAD,
            SAMPLE_ANALYSIS_PAYLOAD,
            ORGANIZER_PAYLOAD,
            PLANNER_PAYLOAD,
            WRITER_PAYLOAD,
            WRITER_PAYLOAD,
            VERIFIER_PAYLOAD,
        ]
    )


def test_run_pipeline_writes_all_artifacts(tmp_path, prompt_dir, sample_papers, scripted_provider):
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step3-001", topic="Unit Topic")
    llm = scripted_step2_responses(scripted_provider)

    payload = asyncio.run(
        run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
    )

    assert set(payload) == {"task", "papers", "survey", "claims", "citations", "evidence_map"}
    assert len(payload["papers"]) == 2
    assert payload["citations"][0]["paper_id"] == "P001"
    assert [c["claim_id"] for c in payload["claims"]] == ["C001", "C002"]

    assert len(read_json(run.path("papers.json"))) == 2
    analyses = read_json(run.path("analyses.json"))
    assert [a["paper_id"] for a in analyses] == ["P001", "P002"]
    assert read_json(run.path("knowledge.json"))["methods"][0]["name"] == "Instruction-conditioned"
    outline = read_json(run.path("outline.json"))
    assert [s["title"] for s in outline["sections"]] == ["Introduction", "Taxonomy"]
    assert read_json(run.path("result.json")) == payload
    assert run.path("draft.md").read_text(encoding="utf-8") == payload["survey"]
    assert run.path("final.md").read_text(encoding="utf-8") == payload["survey"]
    verification = read_json(run.path("verification.json"))
    assert verification["summary"]["total_claims"] == 2
    assert verification["summary"]["supported"] == 1
    assert verification["summary"]["unverifiable"] == 1  # C001 已核验，C002 由系统补齐
    assert verification["results"][0]["support"] is True
    assert verification["results"][0]["evidence"]
    # Step 4 起 evidence_map 来自真实核验结果（Evaluation 接口）
    assert payload["evidence_map"] == verification["results"]


def test_run_pipeline_logs_every_stage_with_usage(
    tmp_path, prompt_dir, sample_papers, scripted_provider
):
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step3-002")
    llm = scripted_step2_responses(scripted_provider)

    asyncio.run(run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config))

    records = read_stage_logs(run)
    assert [r["stage"] for r in records] == STAGE_ORDER
    assert all(r["error"] is None for r in records)
    usage = {r["stage"]: r["token_usage"] for r in records}
    assert usage["paper_reader"] == {"prompt": 20, "completion": 40}
    assert usage["knowledge_organizer"] == {"prompt": 10, "completion": 20}
    assert usage["outline_planner"] == {"prompt": 10, "completion": 20}
    assert usage["survey_writer"] == {"prompt": 20, "completion": 40}
    assert usage["citation_verifier"] == {"prompt": 10, "completion": 20}


def test_run_pipeline_continues_when_one_paper_fails(
    tmp_path, prompt_dir, sample_papers, scripted_provider
):
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step3-003")
    llm = scripted_provider(
        ["bad", "bad", SAMPLE_ANALYSIS_PAYLOAD, ORGANIZER_PAYLOAD, PLANNER_PAYLOAD, WRITER_PAYLOAD]
    )

    payload = asyncio.run(
        run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
    )
    analyses = read_json(run.path("analyses.json"))
    assert analyses[0]["status"] == PaperAnalysis.STATUS_UNAVAILABLE
    assert analyses[1]["status"] == PaperAnalysis.STATUS_OK
    assert payload["survey"]


def test_run_pipeline_dry_run_renders_all_prompts(tmp_path, prompt_dir, sample_papers):
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step3-004")

    payload = asyncio.run(
        run_pipeline(
            None, TaskInput(topic="Unit Topic"), sample_papers, run, config=config, dry_run=True
        )
    )
    prompts = run.path("prompts")
    assert (prompts / "paper_reader.rendered.md").is_file()
    assert (prompts / "organizer.rendered.md").is_file()
    assert (prompts / "planner.rendered.md").is_file()
    assert (prompts / "writer" / "01.rendered.md").is_file()
    assert (prompts / "citation_verifier.rendered.md").is_file()
    assert "Unit Topic" in (prompts / "writer" / "01.rendered.md").read_text(encoding="utf-8")
    assert payload["survey"] == ""


def test_run_pipeline_skips_verifier_when_disabled(
    tmp_path, prompt_dir, sample_papers, scripted_provider
):
    config = build_config(tmp_path, prompt_dir)
    config.pipeline.enable_citation_verification = False
    run = RunWriter.create(tmp_path, "runs", "t-step4-disabled")
    llm = scripted_provider(
        [
            SAMPLE_ANALYSIS_PAYLOAD,
            SAMPLE_ANALYSIS_PAYLOAD,
            ORGANIZER_PAYLOAD,
            PLANNER_PAYLOAD,
            WRITER_PAYLOAD,
            WRITER_PAYLOAD,
        ]
    )

    asyncio.run(run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config))

    assert len(llm.calls) == 6  # Verifier 未消耗模型调用
    verification = read_json(run.path("verification.json"))
    assert verification["summary"] == {
        "total_claims": 2,
        "supported": 0,
        "unsupported": 0,
        "unverifiable": 2,
    }
    assert all(r["error"] for r in verification["results"])


def test_run_pipeline_degrades_when_verifier_fails(
    tmp_path, prompt_dir, sample_papers, scripted_provider
):
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step4-fail")
    # Verifier 单批两次解析均失败（含 repair 重试）→ 降级为 unverifiable，不中断
    llm = scripted_provider(
        [
            SAMPLE_ANALYSIS_PAYLOAD,
            SAMPLE_ANALYSIS_PAYLOAD,
            ORGANIZER_PAYLOAD,
            PLANNER_PAYLOAD,
            WRITER_PAYLOAD,
            WRITER_PAYLOAD,
            "bad",
            "bad",
        ]
    )

    payload = asyncio.run(
        run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
    )

    verification = read_json(run.path("verification.json"))
    assert verification["summary"]["unverifiable"] == 2
    assert "LLMOutputError" in verification["error"]
    assert payload["survey"]  # Pipeline 正常完成
    records = read_stage_logs(run)
    assert [r["stage"] for r in records] == STAGE_ORDER


def test_run_pipeline_requires_provider_without_dry_run(tmp_path, prompt_dir, sample_papers):
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step3-005")
    with pytest.raises(ValueError, match="LLMProvider"):
        asyncio.run(
            run_pipeline(None, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
        )


def test_run_pipeline_records_stage_error(tmp_path, prompt_dir, sample_papers, scripted_provider):
    config = build_config(tmp_path, prompt_dir)
    run = RunWriter.create(tmp_path, "runs", "t-step3-006")
    llm = scripted_provider(["bad", "bad", "bad", "bad"])  # Reader 全部失败

    with pytest.raises(Exception, match="全部 2 篇论文读取失败"):
        asyncio.run(
            run_pipeline(llm, TaskInput(topic="Unit Topic"), sample_papers, run, config=config)
        )
    records = read_stage_logs(run)
    assert records[-1]["stage"] == "paper_reader"
    assert records[-1]["error"]


def test_build_result_matches_evaluation_contract(papers_file):
    papers = load_papers(papers_file)
    state = SurveyState(task=TaskInput(topic="Unit Topic"), papers=list(papers.papers))
    result = build_result(TaskInput(topic="Unit Topic"), state)
    assert result["evidence_map"] == []
    assert [p["paper_id"] for p in result["papers"]] == ["P001", "P002"]
