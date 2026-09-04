"""Knowledge Organizer（Step 3）：跨论文建立研究领域知识结构。

只消费 `PaperAnalysis[]`（不携带论文全文），产出可落盘的 `KnowledgeBase`；
第一版用 Python 对象 / JSON 表示，不引入图数据库。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import ModelConfig
from app.core.types import KnowledgeBase, PaperAnalysis, PaperSet, TaskInput
from app.io.render import MAX_ANALYSIS_CHARS, render_analyses_context
from app.model.provider import LLMProvider, Message
from app.prompts.loader import PromptLoader

SYSTEM_INSTRUCTION = (
    "你是严格遵守结构化输出约束的助手。"
    "只输出符合用户给定 Output Schema 的 JSON 对象，不要输出解释性文字或 Markdown 代码块标记。"
)


class OrganizerError(RuntimeError):
    """知识结构为空，无法继续规划 Outline。"""


@dataclass
class OrganizerConfig:
    """Knowledge Organizer 运行参数。"""

    prompt_name: str = "organizer"
    max_papers: int | None = None
    max_chars_per_paper: int = MAX_ANALYSIS_CHARS


class KnowledgeOrganizer:
    """把 PaperAnalysis[] 组织成 KnowledgeBase。"""

    def __init__(
        self,
        llm: LLMProvider,
        prompts: PromptLoader,
        model: ModelConfig,
        config: OrganizerConfig | None = None,
    ) -> None:
        self.llm = llm
        self.prompts = prompts
        self.model = model
        self.config = config or OrganizerConfig()

    def build_messages(
        self,
        task: TaskInput,
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> list[Message]:
        available = [item for item in analyses if item.available]
        rendered = self.prompts.render(
            self.config.prompt_name,
            topic=getattr(task, "topic", ""),
            paper_count=len(available),
            analyses_context=render_analyses_context(
                analyses,
                papers,
                max_papers=self.config.max_papers,
                max_chars=self.config.max_chars_per_paper,
            ),
        )
        return [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": rendered},
        ]

    def organize(
        self,
        task: TaskInput,
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> KnowledgeBase:
        """组织知识结构；结果为空时抛出 OrganizerError（关键 Stage 允许整体中止）。"""
        if not any(analysis.available for analysis in analyses):
            raise OrganizerError("没有可用的论文分析结果，无法组织知识结构。")

        messages = self.build_messages(task, analyses, papers)
        payload = self.llm.generate_json(
            messages,
            self.model.name,
            self.model.temperature,
            self.model.max_tokens,
            top_p=self.model.top_p,
        )
        knowledge = KnowledgeBase.from_dict(
            payload,
            known_ids={item.paper_id for item in analyses if item.available},
            default_papers=[item.paper_id for item in analyses if item.available],
        )
        if knowledge.is_empty:
            raise OrganizerError("模型未能从论文分析结果中组织出任何知识结构。")
        return knowledge
