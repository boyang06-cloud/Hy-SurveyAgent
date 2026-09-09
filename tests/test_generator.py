"""统一生成器接口的集成测试：HySurveyAgentGenerator → SurveyOutput。"""

from __future__ import annotations

import json

from app.config import AppConfig
from app.core.generator import HySurveyAgentGenerator
from app.core.pipeline import run_pipeline  # noqa: F401  # 保证 pipeline 可用
from tests.conftest import SAMPLE_ANALYSIS_PAYLOAD
from tests.test_pipeline import ORGANIZER_PAYLOAD, PLANNER_PAYLOAD, VERIFIER_PAYLOAD, WRITER_PAYLOAD


def build_generator(tmp_path, prompt_dir, scripted_provider, run_id="t-step5-001"):
    config = AppConfig(root=tmp_path)
    config.paths.prompts_dir = str(prompt_dir)
    llm = scripted_provider(
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
    return HySurveyAgentGenerator(llm, config, run_id=run_id), llm


def test_generate_returns_contract_payload(tmp_path, prompt_dir, sample_papers, scripted_provider):
    generator, _ = build_generator(tmp_path, prompt_dir, scripted_provider)

    output = generator.generate("Unit Topic", sample_papers)

    assert output.task_id == "t-step5-001"
    assert output.violations == []
    assert set(output.to_dict()) == {
        "task",
        "papers",
        "survey",
        "claims",
        "citations",
        "evidence_map",
    }
    assert output.survey
    assert output.claims[0]["claim_id"] == "C001"
    assert output.evidence_map[0]["paper_id"] == "P001"
    # 产物已落盘且与输出同源
    result = json.loads(
        (tmp_path / "runs" / "t-step5-001" / "result.json").read_text(encoding="utf-8")
    )
    assert result == output.to_dict()


def test_generate_rejects_empty_topic_and_papers(
    tmp_path, prompt_dir, sample_papers, scripted_provider
):
    generator, _ = build_generator(tmp_path, prompt_dir, scripted_provider)

    import pytest

    with pytest.raises(ValueError, match="研究主题"):
        generator.generate("   ", sample_papers)
    with pytest.raises(ValueError, match="论文集合"):
        generator.generate("Unit Topic", type(sample_papers)())
