"""Paper Reader 的单元测试：单篇抽取、结构化校验、失败降级与并行编排。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.agents.paper_reader import PaperReader, ReaderConfig, ReaderError
from app.config import ModelConfig
from app.core.types import Paper, PaperAnalysis, PaperSet
from app.prompts.loader import PromptLoader
from tests.conftest import SAMPLE_ANALYSIS_PAYLOAD


def make_reader(prompt_dir: Path, llm: object, **kwargs: object) -> PaperReader:
    config = ReaderConfig(**kwargs)  # type: ignore[arg-type]
    return PaperReader(llm, PromptLoader(prompt_dir), ModelConfig(), config)  # type: ignore[arg-type]


def test_build_messages_contains_single_paper_only(
    prompt_dir: Path, sample_papers: PaperSet
) -> None:
    reader = make_reader(prompt_dir, object())
    messages = reader.build_messages(sample_papers.papers[0])
    content = messages[-1]["content"]
    assert "P001" in content
    assert "Vision-Language Models for Driving" in content
    assert "P002" not in content  # 不得携带其它论文
    assert "Predicts trajectories" not in content  # 不得注入其它论文正文
    assert "{{" not in content


def test_parse_extracts_structure(prompt_dir: Path, sample_papers: PaperSet) -> None:
    reader = make_reader(prompt_dir, object())
    analysis = reader.parse(SAMPLE_ANALYSIS_PAYLOAD, sample_papers.papers[0])
    assert analysis.paper_id == "P001"
    assert analysis.available
    assert analysis.method.startswith("A multimodal transformer")
    assert analysis.dataset == ["nuScenes"]
    assert analysis.claims[0].claim_id == "P001-C1"
    assert "Table 2" in analysis.claims[0].evidence


def test_parse_renumbers_claims(prompt_dir: Path, sample_papers: PaperSet) -> None:
    reader = make_reader(prompt_dir, object())
    payload = {
        "key_idea": "idea",
        "claims": [
            {"text": "first", "evidence": "e1"},
            {"text": "", "evidence": "e2"},  # 空论断丢弃
            {"text": "second", "evidence": "e3"},
        ],
    }
    analysis = reader.parse(payload, sample_papers.papers[0])
    assert [claim.claim_id for claim in analysis.claims] == ["P001-C1", "P001-C2"]


def test_parse_marks_empty_extraction_unavailable(
    prompt_dir: Path, sample_papers: PaperSet
) -> None:
    reader = make_reader(prompt_dir, object())
    analysis = reader.parse({"problem": "", "method": ""}, sample_papers.papers[0])
    assert not analysis.available
    assert analysis.status == PaperAnalysis.STATUS_UNAVAILABLE
    assert analysis.error


def test_read_one_degrades_on_model_failure(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    llm = scripted_provider(["not json", "still not json"])
    reader = make_reader(prompt_dir, llm)
    analysis = reader.read_one(sample_papers.papers[0])
    assert not analysis.available
    assert "JSON" in analysis.error


def test_read_all_preserves_order_and_usage(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    llm = scripted_provider([SAMPLE_ANALYSIS_PAYLOAD, SAMPLE_ANALYSIS_PAYLOAD])
    reader = make_reader(prompt_dir, llm, max_concurrency=1)
    analyses = asyncio.run(reader.read_all(list(sample_papers)))

    assert [analysis.paper_id for analysis in analyses] == ["P001", "P002"]
    assert all(analysis.available for analysis in analyses)
    assert llm.usage == {"prompt": 20, "completion": 40}


def test_read_all_marks_single_failure_and_continues(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    # 第一篇两次解析均失败，第二篇成功：单篇失败不得中断整体流程
    llm = scripted_provider(["bad", "bad", SAMPLE_ANALYSIS_PAYLOAD])
    reader = make_reader(prompt_dir, llm, max_concurrency=1)
    analyses = asyncio.run(reader.read_all(list(sample_papers)))

    assert analyses[0].status == PaperAnalysis.STATUS_UNAVAILABLE
    assert analyses[1].available


def test_read_all_raises_when_every_paper_fails(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    llm = scripted_provider(["bad", "bad", "bad", "bad"])
    reader = make_reader(prompt_dir, llm, max_concurrency=1)
    with pytest.raises(ReaderError, match="全部 2 篇论文读取失败"):
        asyncio.run(reader.read_all(list(sample_papers)))


def test_read_all_limits_concurrency(prompt_dir: Path, scripted_provider) -> None:
    """并发上限生效：同一时刻进入模型的论文数不超过配置值。"""
    running = 0
    peak = 0
    base = type(scripted_provider([]))

    class CountingProvider(base):  # type: ignore[misc, valid-type]
        def generate(self, messages, model, temperature, max_tokens, *, top_p=1.0):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            try:
                return super().generate(messages, model, temperature, max_tokens, top_p=top_p)
            finally:
                running -= 1

    llm = CountingProvider([SAMPLE_ANALYSIS_PAYLOAD] * 3)
    reader = make_reader(prompt_dir, llm, max_concurrency=2)
    papers = [Paper(paper_id=f"P{i:03d}", title=f"T{i}") for i in range(1, 4)]

    analyses = asyncio.run(reader.read_all(papers))

    assert len(analyses) == 3
    assert 1 <= peak <= 2


def test_read_all_returns_empty_for_empty_input(prompt_dir: Path) -> None:
    reader = make_reader(prompt_dir, object())
    assert asyncio.run(reader.read_all([])) == []
