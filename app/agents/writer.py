"""Survey Writer（Step 2：Simple Writer）。

职责：`Topic + Paper Analyses → Survey 草稿 + Claims + Citations`。
约束：只能使用输入论文集中的论文，禁止编造引用；引用编号由代码统一重排，保证可追溯。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.config import ModelConfig
from app.core.types import Citation, Claim, PaperAnalysis, PaperSet, TaskInput, WriterOutput
from app.io.render import MAX_ANALYSIS_CHARS, render_analyses_context
from app.model.provider import LLMProvider, LLMResponse, Message
from app.prompts.loader import PromptLoader

CITATION_TOKEN_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
REFERENCES_PATTERN = re.compile(r"^#{1,6}\s*References\s*$", re.IGNORECASE | re.MULTILINE)
CITATION_ID_PATTERN = re.compile(r"\d+")

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
    max_papers: int | None = None
    max_chars_per_paper: int = MAX_ANALYSIS_CHARS


@dataclass
class WriterResult:
    """Writer 产物与调用上下文，供 Pipeline 记录 token_usage 与落盘 Prompt。"""

    output: WriterOutput
    messages: list[Message] = field(default_factory=list)
    response: LLMResponse | None = None


class SimpleSurveyWriter:
    """Step 2 的 Writer：基于论文分析结果一次性生成 Survey（Step 3 起改为按 Outline 分节写作）。"""

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

    def build_messages(
        self,
        task: TaskInput,
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> list[Message]:
        """只注入可用分析的精简表示，不再携带论文全文。"""
        context = render_analyses_context(
            analyses,
            papers,
            max_papers=self.config.max_papers,
            max_chars=self.config.max_chars_per_paper,
        )
        rendered = self.prompts.render(
            self.config.prompt_name,
            topic=task.topic,
            research_questions=task.research_questions,
            paper_count=sum(1 for analysis in analyses if analysis.available),
            analyses_context=context,
        )
        return [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": rendered},
        ]

    def write(
        self,
        task: TaskInput,
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> WriterResult:
        if not any(analysis.available for analysis in analyses):
            raise WriterError("没有可用的论文分析结果，无法撰写 Survey。")
        messages = self.build_messages(task, analyses, papers)
        payload = self.llm.generate_json(
            messages,
            self.model.name,
            self.model.temperature,
            self.model.max_tokens,
            top_p=self.model.top_p,
        )
        output = self.parse(payload, papers)
        return WriterResult(output=output, messages=messages, response=self.llm.last_response)

    def parse(self, payload: dict[str, Any], papers: PaperSet) -> WriterOutput:
        """把模型输出校验为 WriterOutput：过滤伪引用、重排编号、重建 References。"""
        markdown = payload.get("survey_markdown") or payload.get("survey") or ""
        if not isinstance(markdown, str):
            raise WriterError("survey_markdown 应为字符串。")

        known_ids = papers.ids()
        number_to_paper = _citation_index(payload.get("citations"), known_ids)

        renumbered, ordered, unknown = _renumber(markdown, number_to_paper)
        citations: list[Citation] = []
        for number, paper_id in ordered.items():
            paper = papers.get(paper_id)
            citations.append(
                Citation(
                    citation_id=f"[{number}]",
                    paper_id=paper_id,
                    title=paper.title if paper else "",
                    source=paper.source if paper else "",
                )
            )

        claims: list[Claim] = []
        for item in _dict_list(payload.get("claims")):
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            refs = [pid for pid in _str_list(item.get("citations")) if pid in known_ids]
            if not refs:
                continue  # 无法绑定到真实论文的论断直接丢弃，避免无依据的 Claim
            claims.append(Claim(claim_id=f"C{len(claims) + 1:03d}", text=text, citations=refs))

        return WriterOutput(
            survey_markdown=_replace_references(renumbered, citations, papers),
            claims=claims,
            citations=citations,
            unknown_citations=[f"[{number}]" for number in unknown],
        )


def _citation_index(raw: Any, known_ids: set[str]) -> dict[int, str]:
    """构建 `引用编号 → paper_id`，只保留真实存在的论文。"""
    index: dict[int, str] = {}
    for item in _dict_list(raw):
        paper_id = str(item.get("paper_id") or "").strip()
        if paper_id not in known_ids:
            continue
        match = CITATION_ID_PATTERN.search(str(item.get("citation_id") or ""))
        if not match:
            continue
        number = int(match.group(0))
        if number in index:
            continue  # 同一编号只认第一篇，禁止一篇论文占用多个编号
        index[number] = paper_id
    return index


def _renumber(
    markdown: str, number_to_paper: dict[int, str]
) -> tuple[str, dict[int, str], list[int]]:
    """按正文首次出现顺序重排引用编号。

    返回（新正文, {新编号: paper_id}, 未知编号列表）。未知编号原样保留，
    避免误删正文中形如 `[2020]` 的非引用文本，同时暴露给后续核验。
    """
    new_by_old: dict[int, int] = {}
    unknown: list[int] = []
    counter = 1

    def replace(match: re.Match[str]) -> str:
        nonlocal counter
        numbers: list[int] = []
        for token in match.group(1).split(","):
            token = token.strip()
            if not token.isdigit():
                return match.group(0)
            old = int(token)
            if old not in number_to_paper:
                if old not in unknown:
                    unknown.append(old)
                return match.group(0)
            if old not in new_by_old:
                new_by_old[old] = counter
                counter += 1
            numbers.append(new_by_old[old])
        return "[" + ", ".join(str(number) for number in numbers) + "]"

    text = CITATION_TOKEN_PATTERN.sub(replace, markdown)
    ordered = {
        new: number_to_paper[old]
        for old, new in sorted(new_by_old.items(), key=lambda item: item[1])
    }
    return text, ordered, unknown


def _replace_references(markdown: str, citations: list[Citation], papers: PaperSet) -> str:
    """用规范化后的引用表重建 References 章节，保证编号与论文一一对应。"""
    lines = ["## References", ""]
    for citation in citations:
        paper = papers.get(citation.paper_id)
        label = paper.label() if paper else (citation.title or citation.paper_id)
        suffix = f" {citation.source}" if citation.source else ""
        lines.append(f"{citation.citation_id} {label}.{suffix}")
    block = "\n".join(lines).rstrip() + "\n"

    match = REFERENCES_PATTERN.search(markdown)
    if match:
        return markdown[: match.start()].rstrip() + "\n\n" + block
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
