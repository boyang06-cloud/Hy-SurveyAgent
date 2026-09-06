"""Citation Verifier 的单元测试：证据渲染、结果归一化、分批与降级。"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.citation_verifier import CitationVerifier, VerifierConfig
from app.config import ModelConfig
from app.core.types import Citation, Claim, PaperSet
from app.prompts.loader import PromptLoader

VERIFIER_PAYLOAD = {
    "results": [
        {
            "claim_id": "C001",
            "citation": "P001",
            "support": "true",
            "evidence": "Table 2: baseline 1.4m, with text branch 1.1m.",
            "confidence": 0.9,
        },
        {
            "claim_id": "C002",
            "citation": "[2]",
            "support": False,
            "evidence": "",
            "confidence": 2.5,
        },
    ]
}


def make_claims() -> list[Claim]:
    return [
        Claim(claim_id="C001", text="Language grounding reduces L2 error.", citations=["P001"]),
        Claim(claim_id="C002", text="Open-loop results do not transfer.", citations=["[2]"]),
        Claim(claim_id="C003", text="A claim without citations.", citations=[]),
    ]


def make_citation_map() -> list[Citation]:
    return [
        Citation(citation_id="[1]", paper_id="P001"),
        Citation(citation_id="[2]", paper_id="P002"),
    ]


def make_verifier(prompt_dir: Path, llm: object, **kwargs: object) -> CitationVerifier:
    config = VerifierConfig(**kwargs)  # type: ignore[arg-type]
    return CitationVerifier(llm, PromptLoader(prompt_dir), ModelConfig(), config)  # type: ignore[arg-type]


def test_build_messages_contains_claim_and_cited_evidence_only(
    prompt_dir: Path, sample_analyses, sample_papers: PaperSet
) -> None:
    verifier = make_verifier(prompt_dir, object())
    messages = verifier.build_messages(
        make_claims()[:1], make_citation_map(), sample_analyses, sample_papers
    )
    content = messages[-1]["content"]

    assert "C001" in content
    assert "Language grounding reduces L2 error." in content
    assert "Evidence for P001" in content
    assert "Citation Verifier Prompt" in content
    assert "{{" not in content


def test_verify_normalizes_support_and_confidence(
    prompt_dir: Path, sample_analyses, sample_papers: PaperSet, scripted_provider
) -> None:
    llm = scripted_provider([VERIFIER_PAYLOAD])
    verifier = make_verifier(prompt_dir, llm)
    verification = verifier.verify(
        make_claims(), make_citation_map(), sample_analyses, sample_papers
    )

    assert verification.dropped == 0
    assert verification.error == ""
    by_claim = {result.claim_id: result for result in verification.results}
    # C001: 字符串 "true" 归一化为 True，evidence 原样摘录
    assert by_claim["C001"].citation == "P001"
    assert by_claim["C001"].support is True
    assert by_claim["C001"].evidence.startswith("Table 2")
    assert by_claim["C001"].confidence == 0.9
    # C002: 正文编号 "[2]" 解析为 P002；support=False；confidence 截断到 [0, 1]
    assert by_claim["C002"].citation == "P002"
    assert by_claim["C002"].support is False
    assert by_claim["C002"].confidence == 1.0
    # C003: 无引用 → unverifiable
    assert by_claim["C003"].citation == ""
    assert by_claim["C003"].support is None

    payload = verification.to_dict()
    assert payload["summary"] == {
        "total_claims": 3,
        "supported": 1,
        "unsupported": 1,
        "unverifiable": 1,
    }


def test_verify_fills_unassessed_claims(
    prompt_dir: Path, sample_analyses, sample_papers: PaperSet, scripted_provider
) -> None:
    payload = {
        "results": [
            {
                "claim_id": "C001",
                "citation": "P001",
                "support": True,
                "evidence": "e",
                "confidence": 0.8,
            }
        ]
    }
    llm = scripted_provider([payload])
    verifier = make_verifier(prompt_dir, llm)
    verification = verifier.verify(
        make_claims(), make_citation_map(), sample_analyses, sample_papers
    )

    by_claim = {result.claim_id: result for result in verification.results}
    assert by_claim["C002"].support is None
    assert by_claim["C002"].error == "模型未核验该引用"
    assert by_claim["C003"].support is None
    assert verification.summary()["total_claims"] == 3


def test_verify_drops_unknown_claim_ids(
    prompt_dir: Path, sample_analyses, sample_papers: PaperSet, scripted_provider
) -> None:
    payload = {
        "results": [
            {
                "claim_id": "C001",
                "citation": "P001",
                "support": True,
                "evidence": "e",
                "confidence": 0.8,
            },
            {
                "claim_id": "C999",
                "citation": "P001",
                "support": True,
                "evidence": "e",
                "confidence": 0.8,
            },
        ]
    }
    llm = scripted_provider([payload])
    verifier = make_verifier(prompt_dir, llm)
    verification = verifier.verify(
        make_claims(), make_citation_map(), sample_analyses, sample_papers
    )

    assert all(result.claim_id != "C999" for result in verification.results)
    assert verification.dropped == 1


def test_verify_degrades_on_invalid_json(
    prompt_dir: Path, sample_analyses, sample_papers: PaperSet, scripted_provider
) -> None:
    # 单批两次解析均失败（含一次 repair 重试）→ 该批全部 unverifiable，不抛异常
    llm = scripted_provider(["not json", "still not json"])
    verifier = make_verifier(prompt_dir, llm)
    verification = verifier.verify(
        make_claims(), make_citation_map(), sample_analyses, sample_papers
    )

    assert "LLMOutputError" in verification.error
    assert all(result.support is None for result in verification.results)
    assert verification.summary()["unverifiable"] == 3


def test_verify_batches_claims_per_call(
    prompt_dir: Path, sample_analyses, sample_papers: PaperSet, scripted_provider
) -> None:
    claims = make_claims()
    llm = scripted_provider(
        [
            {
                "results": [
                    {
                        "claim_id": "C001",
                        "citation": "P001",
                        "support": True,
                        "evidence": "e",
                        "confidence": 0.9,
                    }
                ]
            },
            {
                "results": [
                    {
                        "claim_id": "C002",
                        "citation": "P002",
                        "support": True,
                        "evidence": "e",
                        "confidence": 0.9,
                    }
                ]
            },
            {"results": []},
        ]
    )
    verifier = make_verifier(prompt_dir, llm, max_claims_per_call=1)
    verification = verifier.verify(claims, make_citation_map(), sample_analyses, sample_papers)

    assert len(llm.calls) == 3
    # 结果顺序与输入 Claim 顺序一致
    assert [result.claim_id for result in verification.results] == ["C001", "C002", "C003"]
    assert "Citation Verifier Prompt" in json.dumps(
        [json.dumps(call["messages"], ensure_ascii=False) for call in llm.calls]
    )


def test_verify_returns_empty_for_no_claims(
    prompt_dir: Path, sample_analyses, sample_papers: PaperSet
) -> None:
    verifier = make_verifier(prompt_dir, object())
    verification = verifier.verify([], [], sample_analyses, sample_papers)
    assert verification.results == []
    assert verification.to_dict()["summary"] == {
        "total_claims": 0,
        "supported": 0,
        "unsupported": 0,
        "unverifiable": 0,
    }
