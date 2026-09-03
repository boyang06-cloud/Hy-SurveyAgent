"""Survey Writer 的单元测试：Prompt 渲染、结构化输出解析、引用编号重排与伪引用过滤。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.writer import SimpleSurveyWriter, WriterError
from app.config import ModelConfig
from app.core.types import PaperSet, TaskInput
from app.prompts.loader import PromptLoader


def make_writer(prompt_dir: Path, llm: object) -> SimpleSurveyWriter:
    return SimpleSurveyWriter(llm, PromptLoader(prompt_dir), ModelConfig())  # type: ignore[arg-type]


def test_build_messages_renders_topic_and_papers(prompt_dir: Path, sample_papers: PaperSet) -> None:
    writer = make_writer(prompt_dir, object())
    messages = writer.build_messages(TaskInput(topic="Unit Topic"), sample_papers)
    assert messages[0]["role"] == "system"
    content = messages[-1]["content"]
    assert "Unit Topic" in content
    assert "[P001]" in content
    assert "{{" not in content


def test_write_parses_model_output(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    llm = scripted_provider(
        [
            {
                "survey_markdown": "## Introduction\nVLMs support driving [1].",
                "claims": [{"text": "VLMs support driving", "citations": ["P001"]}],
                "citations": [{"citation_id": "[1]", "paper_id": "P001"}],
            }
        ]
    )
    writer = make_writer(prompt_dir, llm)
    result = writer.write(TaskInput(topic="Unit Topic"), sample_papers)

    assert len(llm.calls) == 1
    assert llm.calls[0]["model"] == ModelConfig().name
    assert result.output.citations[0].paper_id == "P001"
    assert result.output.claims[0].claim_id == "C001"
    assert "## References" in result.output.survey_markdown


def test_write_requires_non_empty_papers(prompt_dir: Path, scripted_provider) -> None:
    writer = make_writer(prompt_dir, scripted_provider([]))
    with pytest.raises(WriterError, match="论文集为空"):
        writer.write(TaskInput(topic="Unit Topic"), PaperSet())


def test_parse_renumbers_by_first_appearance(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    writer = make_writer(prompt_dir, scripted_provider([]))
    output = writer.parse(
        {
            "survey_markdown": "## Introduction\nOld number three [3]; then old one [1].",
            "claims": [
                {"text": "first claim", "citations": ["P002"]},
                {"text": "second claim", "citations": ["P001"]},
            ],
            "citations": [
                {"citation_id": "[1]", "paper_id": "P001"},
                {"citation_id": "[3]", "paper_id": "P002"},
            ],
        },
        sample_papers,
    )
    markdown = output.survey_markdown
    assert markdown.index("[1]") < markdown.index("[2]")
    assert "[3]" not in markdown.split("## References")[0]
    assert [citation.paper_id for citation in output.citations] == ["P002", "P001"]
    assert [claim.claim_id for claim in output.claims] == ["C001", "C002"]
    assert "[1] Language-Grounded Trajectory Prediction (2025)." in markdown
    assert "[2] Vision-Language Models for Driving (2024)." in markdown


def test_parse_drops_hallucinated_citations(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    writer = make_writer(prompt_dir, scripted_provider([]))
    output = writer.parse(
        {
            "survey_markdown": "## Introduction\nA claim [1].",
            "claims": [
                {"text": "valid claim", "citations": ["P001"]},
                {"text": "unbound claim", "citations": ["P999"]},
                {"text": "", "citations": ["P001"]},
            ],
            "citations": [
                {"citation_id": "[1]", "paper_id": "P001"},
                {"citation_id": "[2]", "paper_id": "P999"},
            ],
        },
        sample_papers,
    )
    assert len(output.citations) == 1
    assert len(output.claims) == 1
    assert output.claims[0].text == "valid claim"
    assert "P999" not in output.survey_markdown


def test_parse_keeps_non_citation_numbers_as_unknown(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    writer = make_writer(prompt_dir, scripted_provider([]))
    output = writer.parse(
        {
            "survey_markdown": "## Introduction\nSince [2020] the field grew [1].",
            "claims": [],
            "citations": [{"citation_id": "[1]", "paper_id": "P001"}],
        },
        sample_papers,
    )
    assert "[2020]" in output.survey_markdown
    assert output.unknown_citations == ["[2020]"]


def test_parse_handles_grouped_citations(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    writer = make_writer(prompt_dir, scripted_provider([]))
    output = writer.parse(
        {
            "survey_markdown": "## Introduction\nTwo works [1, 2].",
            "claims": [],
            "citations": [
                {"citation_id": "[1]", "paper_id": "P001"},
                {"citation_id": "[2]", "paper_id": "P002"},
            ],
        },
        sample_papers,
    )
    assert "[1, 2]" in output.survey_markdown
    assert len(output.citations) == 2


def test_parse_appends_references_when_missing(
    prompt_dir: Path, sample_papers: PaperSet, scripted_provider
) -> None:
    writer = make_writer(prompt_dir, scripted_provider([]))
    output = writer.parse(
        {
            "survey_markdown": "## Introduction\nNo references section [1].",
            "claims": [],
            "citations": [{"citation_id": "[1]", "paper_id": "P001"}],
        },
        sample_papers,
    )
    expected = "[1] Vision-Language Models for Driving (2024). ExampleConf 2024"
    assert output.survey_markdown.rstrip().endswith(expected)
