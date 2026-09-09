"""Survey Writer（Step 3）：按 Outline 分节撰写 Survey。

设计要点：
    1. 每个 Section 只注入其规划覆盖的论文证据（最小必要 Context），并支持并行生成。
    2. 正文用 `[[P001]]` 论文标记引用，由代码统一转换为 `[1]`/`[2]` 编号并生成
       References，保证跨 Section 编号全局一致、可追溯。
    3. 只能使用输入论文集中的论文，禁止编造引用；无法绑定论文的 Claim 直接丢弃。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from app.config import ModelConfig
from app.core.types import (
    Citation,
    Claim,
    Outline,
    OutlineSection,
    PaperAnalysis,
    PaperSet,
    TaskInput,
    WriterOutput,
)
from app.io.render import MAX_ANALYSIS_CHARS, render_section_evidence
from app.model.provider import LLMProvider, Message
from app.prompts.loader import PromptLoader

CITATION_MARKER_PATTERN = re.compile(r"\[\[([A-Za-z0-9_\-]+)\]\]")
ADJACENT_CITATION_PATTERN = re.compile(r"\[(\d+)\]\[(\d+)\]")
REFERENCES_PATTERN = re.compile(r"^#{1,6}\s*References\s*$", re.IGNORECASE | re.MULTILINE)

SYSTEM_INSTRUCTION = (
    "你是严格遵守结构化输出约束的助手。"
    "只输出符合用户给定 Output Schema 的 JSON 对象，不要输出解释性文字或 Markdown 代码块标记。"
)


class WriterError(RuntimeError):
    """Writer 输入不合法或模型输出无法解析为合法结构。"""


@dataclass
class WriterConfig:
    """Writer 运行参数。"""

    prompt_name: str = "writer"
    max_papers_per_section: int = 8
    max_chars_per_paper: int = MAX_ANALYSIS_CHARS
    max_concurrency: int = 8


@dataclass
class SectionDraft:
    """单个 Section 的生成结果（正文仍使用 [[Pxxx]] 论文标记）。"""

    section: OutlineSection
    content: str
    claims: list[Claim] = field(default_factory=list)


@dataclass
class WriterResult:
    """Writer 产物与调用上下文，供 Pipeline 落盘 Prompt 与统计 token。"""

    output: WriterOutput
    section_messages: list[list[Message]] = field(default_factory=list)


class SurveyWriter:
    """按 Outline 逐节生成，再统一重排引用编号并生成 References。"""

    def __init__(
        self,
        llm: LLMProvider,
        prompts: PromptLoader,
        model: ModelConfig,
        config: WriterConfig | None = None,
    ) -> None:
        self.llm = llm
        self.prompts = prompts
        self.model = model
        self.config = config or WriterConfig()

    def build_section_messages(
        self,
        task: TaskInput,
        section: OutlineSection,
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> list[Message]:
        """只注入该 Section 规划覆盖的论文证据。"""
        rendered = self.prompts.render(
            self.config.prompt_name,
            topic=task.topic,
            section_title=section.title,
            section_purpose=section.purpose,
            section_papers=[f"[{pid}]" for pid in section.papers],
            section_key_claims=section.key_claims,
            evidence_context=render_section_evidence(
                section,
                analyses,
                papers,
                max_papers=self.config.max_papers_per_section,
                max_chars=self.config.max_chars_per_paper,
            ),
        )
        return [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": rendered},
        ]

    async def write(
        self,
        task: TaskInput,
        outline: Outline,
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> WriterResult:
        """并行生成各 Section，再统一编号组装成完整 Survey。"""
        if not outline.sections:
            raise WriterError("Outline 为空，无法撰写 Survey。")
        if not any(analysis.available for analysis in analyses):
            raise WriterError("没有可用的论文分析结果，无法撰写 Survey。")

        semaphore = asyncio.Semaphore(max(1, self.config.max_concurrency))

        async def _write_section(section: OutlineSection) -> tuple[SectionDraft, list[Message]]:
            messages = self.build_section_messages(task, section, analyses, papers)
            async with semaphore:
                payload = await asyncio.to_thread(self._generate, messages)
            return self.parse_section(payload, section, papers.ids()), messages

        results = await asyncio.gather(*(_write_section(section) for section in outline.sections))
        drafts = [draft for draft, _ in results]
        messages = [section_messages for _, section_messages in results]
        return WriterResult(output=self.assemble(drafts, papers), section_messages=messages)

    def _generate(self, messages: list[Message]) -> dict[str, Any]:
        return self.llm.generate_json(
            messages,
            self.model.name,
            self.model.temperature,
            self.model.max_tokens,
            top_p=self.model.top_p,
        )

    def parse_section(
        self, payload: dict[str, Any], section: OutlineSection, known_ids: set[str]
    ) -> SectionDraft:
        """校验单个 Section 的输出；正文为空或 Claim 无法绑定论文时按规则处理。"""
        content = payload.get("content") or payload.get("section_markdown") or ""
        if not isinstance(content, str) or not content.strip():
            raise WriterError(f"Section `{section.title}` 的正文为空。")

        claims: list[Claim] = []
        for item in _dict_list(payload.get("claims")):
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            refs = [pid for pid in _str_list(item.get("citations")) if pid in known_ids]
            if not refs:
                continue
            claims.append(Claim(claim_id=f"C{len(claims) + 1:03d}", text=text, citations=refs))

        return SectionDraft(section=section, content=_strip_references(content), claims=claims)

    def assemble(self, drafts: list[SectionDraft], papers: PaperSet) -> WriterOutput:
        """合并各 Section：统一引用编号、汇总 Claims、生成 References。"""
        body = "\n\n".join(
            f"## {draft.section.title}\n\n{draft.content.strip()}" for draft in drafts
        )

        known_ids = papers.ids()
        ordered: dict[str, int] = {}
        unknown: list[str] = []

        def replace(match: re.Match[str]) -> str:
            marker = match.group(1)
            if marker not in known_ids:
                if marker not in unknown:
                    unknown.append(marker)
                return match.group(0)
            if marker not in ordered:
                ordered[marker] = len(ordered) + 1
            return f"[{ordered[marker]}]"

        body = CITATION_MARKER_PATTERN.sub(replace, body)
        body = _merge_adjacent_citations(body)

        citations: list[Citation] = []
        for marker, number in sorted(ordered.items(), key=lambda item: item[1]):
            paper = papers.get(marker)
            citations.append(
                Citation(
                    citation_id=f"[{number}]",
                    paper_id=marker,
                    title=paper.title if paper else "",
                    source=paper.source if paper else "",
                )
            )

        claims: list[Claim] = []
        for draft in drafts:
            for claim in draft.claims:
                claims.append(
                    Claim(
                        claim_id=f"C{len(claims) + 1:03d}",
                        text=claim.text,
                        citations=claim.citations,
                    )
                )

        return WriterOutput(
            survey_markdown=_replace_references(body, citations, papers),
            claims=claims,
            citations=citations,
            unknown_citations=[f"[[{marker}]]" for marker in unknown],
        )


def _merge_adjacent_citations(markdown: str) -> str:
    """把相邻的 `[1][2]` 合并成 `[1, 2]`。"""
    previous = None
    while previous != markdown:
        previous = markdown
        markdown = ADJACENT_CITATION_PATTERN.sub(r"[\1, \2]", markdown)
    return markdown


def _strip_references(content: str) -> str:
    """移除 Section 内自行输出的 References（统一由系统生成）。"""
    match = REFERENCES_PATTERN.search(content)
    return content[: match.start()].rstrip() if match else content.rstrip()


def _replace_references(markdown: str, citations: list[Citation], papers: PaperSet) -> str:
    """用规范化后的引用表重建 References 章节。"""
    lines = ["## References", ""]
    for citation in citations:
        paper = papers.get(citation.paper_id)
        label = paper.label() if paper else (citation.title or citation.paper_id)
        suffix = f" {citation.source}" if citation.source else ""
        lines.append(f"{citation.citation_id} {label}.{suffix}")
    block = "\n".join(lines).rstrip() + "\n"
    return markdown.rstrip() + "\n\n" + block


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
