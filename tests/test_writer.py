"""Survey Writer（Step 3）的单元测试：分节生成与整体编号。"""

import asyncio

import pytest

from app.agents.writer import SurveyWriter, WriterConfig, WriterError
from app.config import ModelConfig
from app.core.types import Outline, PaperAnalysis, TaskInput
from app.prompts.loader import PromptLoader

PAYLOAD_P001 = {
    "content": "Vision-language models support driving [[P001]].",
    "claims": [{"text": "VLMs support driving", "citations": ["P001"]}],
}
PAYLOAD_P002 = {
    "content": "Methods fall into families [[P002]].",
    "claims": [{"text": "Methods fall into families", "citations": ["P002"]}],
}


def make_writer(prompt_dir, llm, **kwargs):
    return SurveyWriter(llm, PromptLoader(prompt_dir), ModelConfig(), WriterConfig(**kwargs))


def run_writer(writer, task, outline, analyses, papers):
    return asyncio.run(writer.write(task, outline, analyses, papers))


def test_build_section_messages_scopes_evidence(
    prompt_dir, sample_papers, sample_analyses, sample_outline
):
    writer = make_writer(prompt_dir, object())
    section = sample_outline.sections[0]
    content = writer.build_section_messages(
        TaskInput(topic="Unit Topic"), section, sample_analyses, sample_papers
    )[-1]["content"]
    assert "Unit Topic" in content
    assert "Introduction" in content
    assert "Motivate language-grounded driving" in content
    assert "P001-C1" in content
    assert "P002" not in content
    assert "{{" not in content


def test_write_generates_per_section_and_renumbers(
    prompt_dir, sample_papers, sample_analyses, sample_outline, scripted_provider
):
    llm = scripted_provider([PAYLOAD_P001, PAYLOAD_P002])
    writer = make_writer(prompt_dir, llm, max_concurrency=1)
    result = run_writer(
        writer, TaskInput(topic="Unit Topic"), sample_outline, sample_analyses, sample_papers
    )
    markdown = result.output.survey_markdown
    assert markdown.startswith("## Introduction\n\nVision-language models support driving [1].")
    assert "## Taxonomy\n\nMethods fall into families [2]." in markdown
    assert "[[P001]]" not in markdown and "[[P002]]" not in markdown
    assert markdown.rstrip().endswith(
        "[2] Language-Grounded Trajectory Prediction (2025). ExampleJournal 2025"
    )
    assert [c.claim_id for c in result.output.claims] == ["C001", "C002"]
    assert [c.paper_id for c in result.output.citations] == ["P001", "P002"]
    assert len(result.section_messages) == 2


def test_write_requires_outline(prompt_dir, sample_papers, sample_analyses, scripted_provider):
    writer = make_writer(prompt_dir, scripted_provider([]))
    with pytest.raises(WriterError, match="Outline 为空"):
        run_writer(
            writer,
            TaskInput(topic="Unit Topic"),
            Outline(),
            sample_analyses,
            sample_papers,
        )


def test_write_requires_available_analyses(
    prompt_dir, sample_papers, sample_outline, scripted_provider
):
    writer = make_writer(prompt_dir, scripted_provider([]))
    analyses = [PaperAnalysis.unavailable("P001", "读取失败")]
    with pytest.raises(WriterError, match="没有可用的论文分析结果"):
        run_writer(writer, TaskInput(topic="Unit Topic"), sample_outline, analyses, sample_papers)


def test_write_rejects_empty_section_content(
    prompt_dir, sample_papers, sample_analyses, sample_outline, scripted_provider
):
    llm = scripted_provider([{"content": "   "}, PAYLOAD_P002])
    writer = make_writer(prompt_dir, llm, max_concurrency=1)
    with pytest.raises(WriterError, match="Introduction"):
        run_writer(
            writer, TaskInput(topic="Unit Topic"), sample_outline, sample_analyses, sample_papers
        )
