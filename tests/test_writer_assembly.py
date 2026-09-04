"""Survey Writer 组装逻辑的单元测试：跨节编号、相邻引用合并与 References。"""

import asyncio

from app.agents.writer import SurveyWriter, WriterConfig
from app.config import ModelConfig
from app.core.types import Outline, TaskInput
from app.prompts.loader import PromptLoader


def make_writer(prompt_dir, llm):
    return SurveyWriter(
        llm, PromptLoader(prompt_dir), ModelConfig(), WriterConfig(max_concurrency=1)
    )


def run_writer(writer, task, outline, analyses, papers):
    return asyncio.run(writer.write(task, outline, analyses, papers))


def test_write_orders_citations_by_first_appearance(
    prompt_dir, sample_papers, sample_analyses, sample_outline, scripted_provider
):
    llm = scripted_provider(
        [
            {"content": "Trajectory work first [[P002]], then driving [[P001]]."},
            {"content": "More on [[P001]]."},
        ]
    )
    writer = make_writer(prompt_dir, llm)
    result = run_writer(
        writer, TaskInput(topic="Unit Topic"), sample_outline, sample_analyses, sample_papers
    )
    intro = result.output.survey_markdown.split("## Taxonomy")[0]
    assert intro.index("[1]") < intro.index("[2]")
    assert [c.paper_id for c in result.output.citations] == ["P002", "P001"]


def test_write_merges_adjacent_citations_and_reports_unknown(
    prompt_dir, sample_papers, sample_analyses, sample_outline, scripted_provider
):
    llm = scripted_provider([{"content": "Two works [[P001]][[P002]] and [[P999]]."}])
    writer = make_writer(prompt_dir, llm)
    outline = Outline(sections=[sample_outline.sections[0]])
    result = run_writer(
        writer, TaskInput(topic="Unit Topic"), outline, sample_analyses, sample_papers
    )
    assert "[1, 2]" in result.output.survey_markdown
    assert result.output.unknown_citations == ["[[P999]]"]
    assert "[[P001]]" not in result.output.survey_markdown


def test_write_strips_model_references(
    prompt_dir, sample_papers, sample_analyses, sample_outline, scripted_provider
):
    llm = scripted_provider([{"content": "Body text [[P001]].\n\n## References\n[1] junk"}])
    writer = make_writer(prompt_dir, llm)
    outline = Outline(sections=[sample_outline.sections[0]])
    result = run_writer(
        writer, TaskInput(topic="Unit Topic"), outline, sample_analyses, sample_papers
    )
    assert result.output.survey_markdown.count("## References") == 1
    assert "junk" not in result.output.survey_markdown


def test_write_drops_unbound_claims(
    prompt_dir, sample_papers, sample_analyses, sample_outline, scripted_provider
):
    llm = scripted_provider(
        [
            {
                "content": "Body [[P001]].",
                "claims": [
                    {"text": "bound", "citations": ["P001"]},
                    {"text": "unbound", "citations": ["P999"]},
                    {"text": ""},
                ],
            }
        ]
    )
    writer = make_writer(prompt_dir, llm)
    outline = Outline(sections=[sample_outline.sections[0]])
    result = run_writer(
        writer, TaskInput(topic="Unit Topic"), outline, sample_analyses, sample_papers
    )
    assert [c.text for c in result.output.claims] == ["bound"]
