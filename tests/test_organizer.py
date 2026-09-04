"""Knowledge Organizer 的单元测试：知识结构归一化与非法条目过滤。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.organizer import KnowledgeOrganizer, OrganizerError
from app.config import ModelConfig
from app.core.types import PaperAnalysis, PaperSet, TaskInput
from app.prompts.loader import PromptLoader


def make_organizer(prompt_dir: Path, llm: object) -> KnowledgeOrganizer:
    return KnowledgeOrganizer(llm, PromptLoader(prompt_dir), ModelConfig())  # type: ignore[arg-type]


def test_build_messages_uses_analyses_only(
    prompt_dir: Path, sample_papers: object, sample_analyses: list
) -> None:
    organizer = make_organizer(prompt_dir, object())
    content = organizer.build_messages(
        TaskInput(topic="Unit Topic"), sample_analyses, sample_papers
    )[-1]["content"]
    assert "Unit Topic" in content
    assert "[P001]" in content
    assert "Idea of P001" in content
    assert "{{" not in content


def test_organize_builds_knowledge_base(
    prompt_dir: Path,
    sample_papers: object,
    sample_analyses: list,
    scripted_provider,
) -> None:
    llm = scripted_provider(
        [
            {
                "topics": ["Language-grounded driving"],
                "methods": [{"name": "Instruction-conditioned", "papers": ["P001", "P002"]}],
                "problems": [{"name": "Open-loop evaluation", "papers": ["P001"]}],
                "datasets": [{"name": "nuScenes", "papers": ["P001"]}],
                "papers": ["P001", "P002"],
                "relations": [{"source": "P001", "relation": "extends", "target": "P002"}],
            }
        ]
    )
    organizer = make_organizer(prompt_dir, llm)
    knowledge = organizer.organize(TaskInput(topic="Unit Topic"), sample_analyses, sample_papers)

    assert knowledge.topics == ["Language-grounded driving"]
    assert knowledge.methods[0].papers == ["P001", "P002"]
    assert knowledge.relations[0].relation == "extends"
    assert knowledge.dropped == 0


def test_organize_filters_invalid_entries(
    prompt_dir: Path,
    sample_papers: object,
    sample_analyses: list,
    scripted_provider,
) -> None:
    llm = scripted_provider(
        [
            {
                "topics": ["", "Real topic"],
                "methods": [
                    {"name": "No papers", "papers": []},
                    {"name": "Unknown paper", "papers": ["P999"]},
                    {"name": "Valid", "papers": ["P001"]},
                    {"name": "valid", "papers": ["P002"]},
                ],
                "relations": [
                    {"source": "P001", "relation": "extends", "target": "P001"},
                    {"source": "P001", "relation": "is better", "target": "P002"},
                    {"source": "P001", "relation": "compares", "target": "P002"},
                ],
            }
        ]
    )
    organizer = make_organizer(prompt_dir, llm)
    knowledge = organizer.organize(TaskInput(topic="Unit Topic"), sample_analyses, sample_papers)

    assert [group.name for group in knowledge.methods] == ["Valid"]
    assert [relation.relation for relation in knowledge.relations] == ["compares"]
    assert knowledge.dropped == 5
    assert knowledge.topics == ["Real topic"]


def test_organize_backfills_default_papers(
    prompt_dir: Path, sample_papers: object, sample_analyses: list, scripted_provider
) -> None:
    llm = scripted_provider([{"methods": [{"name": "M", "papers": ["P001"]}]}])
    organizer = make_organizer(prompt_dir, llm)
    knowledge = organizer.organize(TaskInput(topic="Unit Topic"), sample_analyses, sample_papers)
    assert knowledge.papers == ["P001", "P002"]


def test_organize_rejects_empty_knowledge(
    prompt_dir: Path, sample_papers: object, sample_analyses: list, scripted_provider
) -> None:
    organizer = make_organizer(prompt_dir, scripted_provider([{}]))
    with pytest.raises(OrganizerError, match="知识结构"):
        organizer.organize(TaskInput(topic="Unit Topic"), sample_analyses, sample_papers)


def test_organize_requires_available_analyses(prompt_dir: Path, scripted_provider) -> None:
    organizer = make_organizer(prompt_dir, scripted_provider([]))
    analyses = [PaperAnalysis.unavailable("P001", "读取失败")]
    with pytest.raises(OrganizerError, match="没有可用的论文分析结果"):
        organizer.organize(TaskInput(topic="Unit Topic"), analyses, PaperSet())
