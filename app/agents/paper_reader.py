"""Paper Reader（Step 2）：把论文转换成统一的 Research Representation。

设计要点：
    1. 每篇论文独立调用，互不携带上下文（禁止一次把全部论文塞进同一个 Prompt）。
    2. 并行读取（asyncio.gather + Semaphore），显著降低总耗时。
    3. 单篇失败只标记 `unavailable`，绝不中断整体流程；全部失败才判定为 Stage 失败。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.config import ModelConfig
from app.core.types import Paper, PaperAnalysis
from app.io.render import MAX_READING_CHARS, render_paper_for_reading
from app.model.provider import LLMProvider, Message
from app.prompts.loader import PromptLoader

SYSTEM_INSTRUCTION = (
    "你是严格遵守结构化输出约束的助手。"
    "只输出符合用户给定 Output Schema 的 JSON 对象，不要输出解释性文字或 Markdown 代码块标记。"
)


class ReaderError(RuntimeError):
    """全部论文读取失败，无法继续后续 Stage。"""


@dataclass
class ReaderConfig:
    """Paper Reader 运行参数。"""

    prompt_name: str = "paper_reader"
    max_chars_per_paper: int = MAX_READING_CHARS
    max_concurrency: int = 8


class PaperReader:
    """单篇抽取 + 并行编排。"""

    def __init__(
        self,
        llm: LLMProvider,
        prompts: PromptLoader,
        model: ModelConfig,
        config: ReaderConfig | None = None,
    ) -> None:
        self.llm = llm
        self.prompts = prompts
        self.model = model
        self.config = config or ReaderConfig()

    def build_messages(self, paper: Paper) -> list[Message]:
        rendered = self.prompts.render(
            self.config.prompt_name,
            paper_id=paper.paper_id,
            title=paper.title,
            paper_text=render_paper_for_reading(paper, max_chars=self.config.max_chars_per_paper),
        )
        return [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": rendered},
        ]

    def parse(self, payload: dict[str, Any], paper: Paper) -> PaperAnalysis:
        """校验模型输出；核心字段全空视为读取失败。

        `paper_id` 以输入论文为准（Prompt 已声明由系统回填），
        防止模型回显 Prompt 中 few-shot 示例的 ID 污染下游 Stage；
        Claim ID（`P00x-Cn`）随输入 paper_id 一并重编。
        """
        clean_payload = {key: value for key, value in payload.items() if key != "paper_id"}
        analysis = PaperAnalysis.from_dict(clean_payload, paper_id=paper.paper_id)
        if not (analysis.problem or analysis.method or analysis.key_idea or analysis.claims):
            return PaperAnalysis.unavailable(paper.paper_id, "模型未抽取到任何有效信息")
        return analysis

    def read_one(self, paper: Paper) -> PaperAnalysis:
        """同步读取单篇；任何异常都收敛为 unavailable，不向上抛出。"""
        try:
            messages = self.build_messages(paper)
            payload = self.llm.generate_json(
                messages,
                self.model.name,
                self.model.temperature,
                self.model.max_tokens,
                top_p=self.model.top_p,
            )
            return self.parse(payload, paper)
        except Exception as exc:  # noqa: BLE001 - 单篇失败必须可恢复
            return PaperAnalysis.unavailable(paper.paper_id, f"{type(exc).__name__}: {exc}")

    async def read_all(self, papers: list[Paper]) -> list[PaperAnalysis]:
        """并行读取全部论文，返回与输入同序的分析结果。"""
        if not papers:
            return []

        semaphore = asyncio.Semaphore(max(1, self.config.max_concurrency))

        async def _read(paper: Paper) -> PaperAnalysis:
            async with semaphore:
                return await asyncio.to_thread(self.read_one, paper)

        results = await asyncio.gather(*(_read(paper) for paper in papers), return_exceptions=True)

        analyses: list[PaperAnalysis] = []
        for paper, result in zip(papers, results, strict=True):
            if isinstance(result, BaseException):
                analyses.append(
                    PaperAnalysis.unavailable(paper.paper_id, f"{type(result).__name__}: {result}")
                )
            else:
                analyses.append(result)

        if not any(analysis.available for analysis in analyses):
            first_error = next((item.error for item in analyses if item.error), "未知原因")
            raise ReaderError(f"全部 {len(papers)} 篇论文读取失败，首个错误：{first_error}")
        return analyses
