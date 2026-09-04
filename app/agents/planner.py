"""Outline Planner（Step 3）：依据知识结构规划 Survey 章节。

只消费 `TaskInput + KnowledgeBase + 可引用 Claim 清单`，不携带论文全文；
每个 Section 必须具备 Purpose + Papers + Key Claims，否则丢弃并计数。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import ModelConfig
from app.core.types import KnowledgeBase, Outline, PaperAnalysis, PaperSet, TaskInput
from app.io.render import render_claims_context, render_knowledge_context
from app.model.provider import LLMProvider, Message
from app.prompts.loader import PromptLoader

SYSTEM_INSTRUCTION = (
    "你是严格遵守结构化输出约束的助手。"
    "只输出符合用户给定 Output Schema 的 JSON 对象，不要输出解释性文字或 Markdown 代码块标记。"
)


class PlannerError(RuntimeError):
    """无法产出合法 Outline（关键 Stage，允许整体中止）。"""


@dataclass
class PlannerConfig:
    """Outline Planner 运行参数。"""

    prompt_name: str = "planner"
    max_claims_per_paper: int = 5
    max_chars_per_evidence: int = 160


class OutlinePlanner:
    """把 KnowledgeBase 规划成 Outline。"""

    def __init__(
        self,
        llm: LLMProvider,
        prompts: PromptLoader,
        model: ModelConfig,
        config: PlannerConfig | None = None,
    ) -> None:
        self.llm = llm
        self.prompts = prompts
        self.model = model
        self.config = config or PlannerConfig()

    def build_messages(
        self,
        task: TaskInput,
        knowledge: KnowledgeBase,
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> list[Message]:
        rendered = self.prompts.render(
            self.config.prompt_name,
            topic=task.topic,
            research_questions=task.research_questions,
            knowledge_context=render_knowledge_context(knowledge),
            claims_context=render_claims_context(
                analyses,
                papers,
                max_claims_per_paper=self.config.max_claims_per_paper,
                max_chars_per_evidence=self.config.max_chars_per_evidence,
            ),
        )
        return [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": rendered},
        ]

    def plan(
        self,
        task: TaskInput,
        knowledge: KnowledgeBase,
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> Outline:
        """规划 Outline；没有任何合法 Section 时抛出 PlannerError。"""
        available_ids = {item.paper_id for item in analyses if item.available}
        known_claims = {
            claim.claim_id
            for analysis in analyses
            if analysis.available
            for claim in analysis.claims
        }

        messages = self.build_messages(task, knowledge, analyses, papers)
        payload: dict[str, Any] = self.llm.generate_json(
            messages,
            self.model.name,
            self.model.temperature,
            self.model.max_tokens,
            top_p=self.model.top_p,
        )
        outline = Outline.from_dict(payload, known_ids=available_ids, known_claims=known_claims)

        if not outline.sections:
            raise PlannerError(
                "模型未能规划出任何合法 Section（需具备 purpose / papers / key_claims）。"
            )
        return outline

    @staticmethod
    def uncovered_papers(outline: Outline, analyses: list[PaperAnalysis]) -> list[str]:
        """找出未被任何 Section 覆盖的可用论文，供日志与核验使用。"""
        covered = {paper_id for section in outline.sections for paper_id in section.papers}
        return [
            analysis.paper_id
            for analysis in analyses
            if analysis.available and analysis.paper_id not in covered
        ]
