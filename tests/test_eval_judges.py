"""Judge 基类与七类 Judge 的解析 / 降级 / 缓存 / gating 单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.model.provider import LLMError
from evaluator.evidence.claims import build_citation_lookup, resolve_markers
from evaluator.judges.base import JudgeError, load_prompt
from evaluator.judges.citation import CitationJudge
from evaluator.judges.coverage import CoverageJudge
from evaluator.judges.factual import FactualJudge
from evaluator.judges.outline import OutlineJudge
from evaluator.judges.quiz_answer import QuizAnswerJudge
from evaluator.judges.readability import ReadabilityJudge
from evaluator.judges.synthesis import SynthesisJudge
from evaluator.judges.terminology import TerminologyJudge
from evaluator.quizzes.answerer import (
    NO_SUFFICIENT_INFORMATION,
    QuizAnswer,
    QuizAnswerer,
    SurveySection,
)
from evaluator.quizzes.scorer import score_answer
from tests.evalutils import RoutingProvider


class _ScriptedFailureProvider(RoutingProvider):
    """始终抛 LLMError 的 Provider。"""

    def generate(self, messages, model, temperature, max_tokens, *, top_p=1.0):
        raise LLMError("boom")


def _model() -> str:
    return "test-model"


def test_load_prompt_version_and_hash() -> None:
    meta = load_prompt("factual")
    assert meta.version == "0.1.0"
    assert len(meta.sha256) == 64
    assert "Factual Accuracy Judge" in meta.template


def test_load_prompt_missing() -> None:
    with pytest.raises(JudgeError):
        load_prompt("nonexistent_prompt")


def test_base_judge_rejects_nonzero_temperature() -> None:
    provider = RoutingProvider([])
    with pytest.raises(ValueError):
        FactualJudge(provider, _model(), temperature=0.7)


def test_factual_judge_validate_and_degrade() -> None:
    provider = RoutingProvider([])
    judge = FactualJudge(provider, _model())
    output = judge.validate({"claim_id": "C1", "label": "SUPPORTED", "score": 2, "reason": "ok"})
    assert output == {"claim_id": "C1", "label": "SUPPORTED", "score": 2, "reason": "ok"}

    # label 非法 → UNSUPPORTED
    degraded = judge.validate({"claim_id": "C1", "label": "MAYBE", "score": 2, "reason": ""})
    assert degraded["label"] == "UNSUPPORTED"
    assert degraded["score"] == 0
    assert "warning" in degraded

    # score 与 label 不一致 → 以 label 为准
    mismatch = judge.validate({"label": "SUPPORTED", "score": 1})
    assert mismatch["score"] == 2


def test_factual_judge_fallback_on_llm_error() -> None:
    judge = FactualJudge(_ScriptedFailureProvider([]), _model())
    output = judge.run({"claim_id": "C1", "claim": "x", "evidence": []})
    assert output["label"] == "UNSUPPORTED"
    assert output["score"] == 0
    assert output["error"]
    assert judge.stats["errors"] == 1
    assert judge.stats["calls"] == 1


def test_citation_judge_validate() -> None:
    judge = CitationJudge(RoutingProvider([]), _model())
    assert judge.validate({"support": 2, "reason": "ok"})["support"] == 2
    assert judge.validate({"support": "high"})["support"] == 0
    assert judge.validate({"support": 9})["support"] == 2  # 越界裁剪


def test_coverage_judge_validate() -> None:
    judge = CoverageJudge(RoutingProvider([]), _model())
    output = judge.validate(
        {
            "units": [{"id": "u1", "score": 2, "evidence_span": "s"}, {"id": "u2", "score": 5}],
            "total_paragraphs": -3,
            "irrelevant_paragraphs": 4,
        }
    )
    assert output["units"][0]["score"] == 2
    assert output["units"][1]["score"] == 2  # 越界裁剪到上限
    assert output["total_paragraphs"] == 0
    assert output["irrelevant_paragraphs"] == 4


def test_synthesis_and_outline_judge_validate() -> None:
    synthesis = SynthesisJudge(RoutingProvider([]), _model())
    output = synthesis.validate({"taxonomy": 3, "comparison": "x", "evolution": 5, "insight": 2})
    assert output == {"taxonomy": 3, "comparison": 0, "evolution": 4, "insight": 2, "reason": ""}
    outline = OutlineJudge(RoutingProvider([]), _model())
    output = outline.validate(
        {"hierarchy": 4, "logical_progression": 4, "section_function": 4, "outline_relevance": 4}
    )
    assert output["hierarchy"] == 4


def test_quiz_judge_validate() -> None:
    judge = QuizAnswerJudge(RoutingProvider([]), _model())
    output = judge.validate({"accuracy": 5, "completeness": 3, "relevance": 2})
    assert output["accuracy"] == 4  # 越界裁剪


def test_terminology_judge_validate() -> None:
    judge = TerminologyJudge(RoutingProvider([]), _model())
    output = judge.validate(
        {
            "severe": -1,
            "moderate": 2.5,
            "minor": "x",
            "issues": [{"level": "SEVERE", "description": "d"}, "bad"],
        }
    )
    assert output["severe"] == 0
    assert output["moderate"] == 2
    assert output["minor"] == 0
    assert output["issues"] == [{"level": "SEVERE", "description": "d"}]


def test_readability_judge_validate() -> None:
    judge = ReadabilityJudge(RoutingProvider([]), _model())
    assert judge.validate({"score": 3})["score"] == 3
    assert judge.validate({})["score"] == 0


def test_base_judge_cache_roundtrip(tmp_path: Path) -> None:
    provider = RoutingProvider(
        [("Factual Accuracy Judge", {"label": "SUPPORTED", "score": 2, "reason": "r"})]
    )
    judge = FactualJudge(provider, _model(), cache_dir=tmp_path)
    payload = {
        "claim_id": "C1",
        "claim": "x",
        "evidence": [{"paper_id": "p", "section_id": "s", "text": "t"}],
    }
    first = judge.run(payload)
    assert judge.stats["calls"] == 1
    second = judge.run(payload)  # 命中缓存，不再调用 LLM
    assert judge.stats["calls"] == 1
    assert judge.stats["cache_hits"] == 1
    assert first == second


def test_base_judge_records_token_usage() -> None:
    provider = RoutingProvider(
        [("Factual Accuracy Judge", {"label": "SUPPORTED", "score": 2, "reason": "r"})]
    )
    judge = FactualJudge(provider, _model())
    judge.run({"claim_id": "C1", "claim": "x", "evidence": []})
    assert judge.stats["prompt_tokens"] == 10
    assert judge.stats["completion_tokens"] == 5


def test_run_consensus_dual_and_arbiter() -> None:
    responses = [
        {"label": "SUPPORTED", "score": 2, "reason": "a"},
        {"label": "UNSUPPORTED", "score": 0, "reason": "b"},
        {"label": "PARTIALLY_SUPPORTED", "score": 1, "reason": "c"},
    ]
    provider = RoutingProvider([("Factual Accuracy Judge", list(responses))])
    judge = FactualJudge(provider, _model())
    output, provenance = judge.run_consensus({"claim_id": "C1"}, dual=True, threshold=1.0)
    assert provenance["mode"] == "dual_arbiter"
    assert output["score"] == 1  # 中位数


def test_run_consensus_dual_agree() -> None:
    response = {"label": "SUPPORTED", "score": 2, "reason": "a"}
    provider = RoutingProvider([("Factual Accuracy Judge", response)])
    judge = FactualJudge(provider, _model())
    output, provenance = judge.run_consensus({"claim_id": "C1"}, dual=True, threshold=1.0)
    assert provenance["mode"] == "dual_agree"
    assert output["score"] == 2


def test_build_citation_lookup() -> None:
    lookup = build_citation_lookup([{"citation_id": "1", "paper_id": "P001"}])
    assert lookup["[1]"] == "P001"
    assert lookup["1"] == "P001"
    assert lookup["[[1]]"] == "P001"
    assert build_citation_lookup([{"citation_id": "", "paper_id": ""}]) == {}


def test_resolve_markers() -> None:
    lookup = build_citation_lookup(
        [{"citation_id": "1", "paper_id": "P001"}, {"citation_id": "2", "paper_id": "P002"}]
    )
    assert resolve_markers(["[1]", "2", "[[2]]", "[3]"], lookup) == ["P001", "P002"]


def test_quiz_answerer_evidence_gating() -> None:
    answerer = QuizAnswerer(RoutingProvider([]), _model())
    answerer.bind_survey([])  # 空 Survey 检索语料
    answer = answerer.answer("Q1", "Any question?")
    assert answer.unanswered
    assert answer.answer == NO_SUFFICIENT_INFORMATION


def test_quiz_answerer_routes_and_cites_sections() -> None:
    provider = RoutingProvider(
        [("Survey-only Quiz Answerer", {"answer": "Some answer.", "used_sections": ["sec_00"]})]
    )
    answerer = QuizAnswerer(provider, _model())
    answerer.bind_survey(
        [
            SurveySection(
                section_id="sec_00",
                title="Intro",
                text="3DGS represents scenes using anisotropic Gaussians.",
            )
        ]
    )
    answer = answerer.answer("Q1", "How does 3DGS represent scenes?")
    assert answer.answer == "Some answer."
    assert answer.used_sections == ["sec_00"]


def test_score_answer_gating_zero() -> None:
    judge = QuizAnswerJudge(RoutingProvider([]), _model())
    # 无 used_sections → gating 0 分（不调用 Judge）
    score = score_answer(
        judge,
        question_id="Q1",
        question="q",
        reference_answer="r",
        answer=QuizAnswer(question_id="Q1", answer="looks correct", used_sections=[]),
        evidence_gating=True,
    )
    assert score.total == 0 and score.gated

    # unanswered → 0 分
    score = score_answer(
        judge,
        question_id="Q1",
        question="q",
        reference_answer="r",
        answer=QuizAnswer(question_id="Q1", answer=NO_SUFFICIENT_INFORMATION),
        evidence_gating=True,
    )
    assert score.total == 0 and score.unanswered


def test_score_answer_full_marks() -> None:
    provider = RoutingProvider(
        [("Quiz Answer Judge", {"accuracy": 4, "completeness": 4, "relevance": 2, "reason": "ok"})]
    )
    judge = QuizAnswerJudge(provider, _model())
    score = score_answer(
        judge,
        question_id="Q1",
        question="q",
        reference_answer="r",
        answer=QuizAnswer(question_id="Q1", answer="a", used_sections=["sec_00"]),
        evidence_gating=True,
    )
    assert score.total == 10
    assert score.normalized == 100.0
