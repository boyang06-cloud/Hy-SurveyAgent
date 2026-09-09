"""Outline Planner 的单元测试：Section 校验与非法条目过滤。"""

from pathlib import Path

import pytest

from app.agents.planner import OutlinePlanner, PlannerError
from app.config import ModelConfig
from app.core.types import Outline, OutlineSection, TaskInput
from app.model.provider import LLMOutputError
from app.prompts.loader import PromptLoader

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


def make_planner(prompt_dir: Path, llm: object) -> OutlinePlanner:
    return OutlinePlanner(llm, PromptLoader(prompt_dir), ModelConfig())  # type: ignore[arg-type]


def test_build_messages_includes_knowledge_and_claims(
    prompt_dir, sample_papers, sample_knowledge, sample_analyses
) -> None:
    planner = make_planner(prompt_dir, object())
    content = planner.build_messages(
        TaskInput(topic="Unit Topic"), sample_knowledge, sample_analyses, sample_papers
    )[-1]["content"]
    assert "Unit Topic" in content
    assert "Instruction-conditioned" in content
    assert "P001-C1" in content
    assert "{{" not in content


def test_plan_builds_outline(
    prompt_dir, sample_papers, sample_knowledge, sample_analyses, scripted_provider
) -> None:
    planner = make_planner(prompt_dir, scripted_provider([PLANNER_PAYLOAD]))
    outline = planner.plan(
        TaskInput(topic="Unit Topic"), sample_knowledge, sample_analyses, sample_papers
    )
    assert [s.title for s in outline.sections] == ["Introduction", "Taxonomy"]
    assert outline.sections[0].key_claims == ["P001-C1"]
    assert outline.dropped == 0


def test_plan_drops_invalid_sections(
    prompt_dir, sample_papers, sample_knowledge, sample_analyses, scripted_provider
) -> None:
    llm = scripted_provider(
        [
            {
                "sections": [
                    PLANNER_PAYLOAD["sections"][0],
                    {"title": "No papers", "purpose": "x", "papers": []},
                    {"title": "No purpose", "purpose": "", "papers": ["P001"]},
                    {"title": "Unknown paper", "purpose": "x", "papers": ["P999"]},
                    {
                        "title": "Bad claim",
                        "purpose": "x",
                        "papers": ["P001"],
                        "key_claims": ["P999-C1"],
                    },
                    {"title": "introduction", "purpose": "dup", "papers": ["P001"]},
                ]
            }
        ]
    )
    planner = make_planner(prompt_dir, llm)
    outline = planner.plan(
        TaskInput(topic="Unit Topic"), sample_knowledge, sample_analyses, sample_papers
    )
    assert [s.title for s in outline.sections] == ["Introduction", "Bad claim"]
    assert outline.dropped == 4


def test_plan_reports_uncovered_papers(
    prompt_dir, sample_papers, sample_knowledge, sample_analyses, scripted_provider
) -> None:
    planner = make_planner(prompt_dir, scripted_provider([PLANNER_PAYLOAD]))
    outline = planner.plan(
        TaskInput(topic="Unit Topic"), sample_knowledge, sample_analyses, sample_papers
    )
    assert planner.uncovered_papers(outline, sample_analyses) == []
    partial = Outline(sections=[OutlineSection(title="Only", purpose="x", papers=["P001"])])
    assert planner.uncovered_papers(partial, sample_analyses) == ["P002"]
    covered = Outline(sections=[OutlineSection(title="All", purpose="x", papers=["P001", "P002"])])
    assert planner.uncovered_papers(covered, sample_analyses) == []


def test_plan_rejects_empty_outline(
    prompt_dir, sample_papers, sample_knowledge, sample_analyses, scripted_provider
) -> None:
    planner = make_planner(prompt_dir, scripted_provider([{"sections": []}]))
    with pytest.raises(PlannerError, match="Section"):
        planner.plan(
            TaskInput(topic="Unit Topic"), sample_knowledge, sample_analyses, sample_papers
        )


def test_plan_propagates_invalid_json(
    prompt_dir, sample_papers, sample_knowledge, sample_analyses, scripted_provider
) -> None:
    planner = make_planner(prompt_dir, scripted_provider(["no json", "still no json"]))
    with pytest.raises(LLMOutputError):
        planner.plan(
            TaskInput(topic="Unit Topic"), sample_knowledge, sample_analyses, sample_papers
        )
