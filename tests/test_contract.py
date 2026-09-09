"""Evaluation 输出契约的单元测试：字段对齐、校验不变量与合并结果。"""

from __future__ import annotations

from app.core.contract import (
    build_eval_payload,
    build_evidence_map,
    build_result_payload,
    validate_result_payload,
)
from app.core.types import Citation, Claim, Outline, OutlineSection, Paper, PaperSet, TaskInput


def make_state():
    from app.core.types import SurveyState

    papers = PaperSet(
        papers=[
            Paper(paper_id="P001", title="Paper One", year=2024, source="Conf A"),
            Paper(paper_id="P002", title="Paper Two", year=2025),
        ]
    )
    state = SurveyState(
        task=TaskInput(topic="Unit Topic", research_questions=["Q1"]),
        papers=list(papers.papers),
        outline=Outline(
            sections=[OutlineSection(title="Introduction", purpose="p", papers=["P001"])]
        ),
        draft="## Introduction\n\nBody [1].",
        claims=[Claim(claim_id="C001", text="claim", citations=["P001"])],
        citation_map=[Citation(citation_id="[1]", paper_id="P001", title="Paper One")],
        verification={
            "results": [
                {
                    "claim_id": "C001",
                    "citation": "P001",
                    "support": True,
                    "evidence": "Table 1",
                    "confidence": 0.9,
                    "error": "",
                }
            ],
            "summary": {"total_claims": 1, "supported": 1, "unsupported": 0, "unverifiable": 0},
        },
        final_survey="## Introduction\n\nBody [1].",
    )
    return papers, state


def test_build_result_payload_matches_contract():
    papers, state = make_state()
    payload = build_result_payload(TaskInput(topic="Unit Topic"), state)

    assert list(payload) == ["task", "papers", "survey", "claims", "citations", "evidence_map"]
    assert payload["papers"][0] == {
        "paper_id": "P001",
        "title": "Paper One",
        "year": 2024,
        "source": "Conf A",
    }
    # Verification 的 citation 字段在 evidence_map 中命名为 paper_id，仅保留契约字段
    assert payload["evidence_map"] == [
        {"claim_id": "C001", "paper_id": "P001", "evidence": "Table 1", "support": True}
    ]
    assert validate_result_payload(payload) == []


def test_build_eval_payload_is_merged_machine_readable():
    papers, state = make_state()
    payload = build_eval_payload(state)
    assert list(payload) == [
        "survey_markdown",
        "citations",
        "source_papers",
        "outline",
        "claims",
        "verification",
    ]
    assert payload["survey_markdown"] == state.final_survey
    assert [p["paper_id"] for p in payload["source_papers"]] == ["P001", "P002"]
    assert payload["outline"]["sections"][0]["title"] == "Introduction"
    assert payload["verification"]["summary"]["total_claims"] == 1


def test_build_evidence_map_tolerates_legacy_paper_id_key():
    entry = build_evidence_map(
        {"results": [{"claim_id": "C001", "paper_id": "P001", "support": None, "evidence": ""}]}
    )
    assert entry == [{"claim_id": "C001", "paper_id": "P001", "evidence": "", "support": None}]


def test_validate_rejects_missing_keys():
    assert any("缺少必需字段" in e for e in validate_result_payload({"task": {}}))


def test_validate_rejects_unknown_paper_reference():
    _, state = make_state()
    state.claims.append(Claim(claim_id="C002", text="bad", citations=["P999"]))
    payload = build_result_payload(TaskInput(topic="Unit Topic"), state)
    assert any("C002" in e and "P999" in e for e in validate_result_payload(payload))


def test_validate_rejects_duplicate_and_missing_ids():
    _, state = make_state()
    state.claims.append(Claim(claim_id="C001", text="dup", citations=[]))
    payload = build_result_payload(TaskInput(topic="Unit Topic"), state)
    errors = validate_result_payload(payload)
    assert any("重复的 claim_id" in e for e in errors)


def test_validate_rejects_evidence_map_drift():
    _, state = make_state()
    state.verification = {
        "results": [{"claim_id": "C999", "citation": "P999", "support": "yes", "evidence": ""}]
    }
    payload = build_result_payload(TaskInput(topic="Unit Topic"), state)
    errors = validate_result_payload(payload)
    assert any("C999" in e for e in errors)
    assert any("P999" in e for e in errors)


def test_validate_rejects_duplicate_citation_ids():
    _, state = make_state()
    state.citation_map.append(Citation(citation_id="[1]", paper_id="P002", title="dup"))
    payload = build_result_payload(TaskInput(topic="Unit Topic"), state)
    assert any("重复的 citation_id" in e for e in validate_result_payload(payload))


def test_validate_allows_unverifiable_entries_without_citation():
    _, state = make_state()
    state.verification = {
        "results": [{"claim_id": "C001", "citation": "", "support": None, "evidence": ""}]
    }
    payload = build_result_payload(TaskInput(topic="Unit Topic"), state)
    assert validate_result_payload(payload) == []
