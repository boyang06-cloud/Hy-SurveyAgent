"""Survey Pipeline（Step 3）：完整的多阶段 Agent Workflow。

Stage 顺序：
    literature_manager → paper_reader → knowledge_organizer
    → outline_planner → survey_writer → finalize

约定：每个 Stage 只消费最小必要 Context，产物写入 SurveyState 并落盘到 runs/<task_id>/；
关键 Stage（organizer / planner）无合法产物时整体中止，其余 Stage 单点失败可降级。
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.agents.organizer import KnowledgeOrganizer
from app.agents.paper_reader import PaperReader, ReaderConfig
from app.agents.planner import OutlinePlanner
from app.agents.writer import SurveyWriter, WriterConfig, WriterResult
from app.config import AppConfig
from app.core.types import (
    Outline,
    OutlineSection,
    PaperAnalysis,
    PaperSet,
    SurveyState,
    TaskInput,
    WriterOutput,
)
from app.io.exporter import RunWriter
from app.model.provider import LLMError, LLMProvider, LLMResponse
from app.prompts.loader import PromptLoader

STAGE_LITERATURE = "literature_manager"
STAGE_READER = "paper_reader"
STAGE_ORGANIZER = "knowledge_organizer"
STAGE_PLANNER = "outline_planner"
STAGE_WRITER = "survey_writer"
STAGE_FINALIZE = "finalize"
PROMPTS = ("paper_reader", "organizer", "planner", "writer")


class _DryRunProvider(LLMProvider):
    """dry-run 占位实现：任何调用都视为错误，确保离线检查不会触发真实请求。"""

    def generate(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        *,
        top_p: float = 1.0,
    ) -> LLMResponse:
        raise LLMError("dry-run 模式下不调用模型。")


async def run_pipeline(
    llm: LLMProvider | None,
    task: TaskInput,
    papers: PaperSet,
    run: RunWriter,
    *,
    config: AppConfig,
    dry_run: bool = False,
    writer_config: WriterConfig | None = None,
    reader_config: ReaderConfig | None = None,
) -> dict[str, Any]:
    """执行 Survey Pipeline，返回对齐 Evaluation 接口的结果字典。"""
    if llm is None and not dry_run:
        raise ValueError("dry_run=False 时必须提供 LLMProvider。")

    state = SurveyState(task=task, papers=list(papers.papers))
    prompts = PromptLoader(config.prompts_dir())
    provider = llm if llm is not None else _DryRunProvider()
    reader = PaperReader(
        provider,
        prompts,
        config.model,
        reader_config or ReaderConfig(max_concurrency=config.runtime.max_concurrency),
    )
    organizer = KnowledgeOrganizer(provider, prompts, config.model)
    planner = OutlinePlanner(provider, prompts, config.model)
    writer = SurveyWriter(provider, prompts, config.model, writer_config)

    with run.stage(STAGE_LITERATURE, "task.json", "papers.json"):
        run.write_json("papers.json", [paper.to_dict() for paper in state.papers])

    reader_before = _usage_snapshot(provider)
    with run.stage(STAGE_READER, "papers.json", "analyses.json") as stats:
        if dry_run and state.papers:
            messages = reader.build_messages(state.papers[0])
            run.write_text("prompts/paper_reader.rendered.md", str(messages[-1]["content"]))
        elif not dry_run:
            state.paper_analyses = await reader.read_all(state.papers)
        stats["token_usage"] = _usage_delta(provider, reader_before)
        run.write_json("analyses.json", [item.to_dict() for item in state.paper_analyses])

    organizer_before = _usage_snapshot(provider)
    with run.stage(STAGE_ORGANIZER, "analyses.json", "knowledge.json") as stats:
        if dry_run:
            messages = organizer.build_messages(task, state.paper_analyses, papers)
            run.write_text("prompts/organizer.rendered.md", str(messages[-1]["content"]))
        else:
            state.knowledge_base = await asyncio.to_thread(
                organizer.organize, task, state.paper_analyses, papers
            )
        stats["token_usage"] = _usage_delta(provider, organizer_before)
        run.write_json("knowledge.json", state.knowledge_base.to_dict())

    planner_before = _usage_snapshot(provider)
    with run.stage(STAGE_PLANNER, "knowledge.json", "outline.json") as stats:
        if dry_run:
            messages = planner.build_messages(
                task, state.knowledge_base, state.paper_analyses, papers
            )
            run.write_text("prompts/planner.rendered.md", str(messages[-1]["content"]))
            # dry-run 无模型产出，使用默认章节骨架以便渲染 Writer Prompt
            state.outline = _default_outline(state.paper_analyses)
        else:
            state.outline = await asyncio.to_thread(
                planner.plan, task, state.knowledge_base, state.paper_analyses, papers
            )
        stats["token_usage"] = _usage_delta(provider, planner_before)
        run.write_json("outline.json", state.outline.to_dict())

    writer_before = _usage_snapshot(provider)
    with run.stage(STAGE_WRITER, "outline.json", "draft.md") as stats:
        if dry_run:
            render_writer_prompts(writer, task, state, papers, run)
            result = WriterResult(output=WriterOutput())
        else:
            result = await writer.write(task, state.outline, state.paper_analyses, papers)
            for index, messages in enumerate(result.section_messages, start=1):
                body = str(messages[-1]["content"])
                run.write_text(f"prompts/writer/{index:02d}.rendered.md", body)
        stats["token_usage"] = _usage_delta(provider, writer_before)
        state.draft = result.output.survey_markdown
        state.claims = result.output.claims
        state.citation_map = result.output.citations
        run.write_text("draft.md", state.draft)
        run.write_json(
            "claims.json",
            {
                "claims": [claim.to_dict() for claim in state.claims],
                "citation_map": [citation.to_dict() for citation in state.citation_map],
                "unknown_citations": result.output.unknown_citations,
            },
        )

    with run.stage(STAGE_FINALIZE, "draft.md", "result.json"):
        state.final_survey = state.draft
        # Step 4 接入 Citation Verifier 后由核验结果填充；此处保持结构稳定
        state.verification = {
            "results": [],
            "summary": {
                "total_claims": len(state.claims),
                "supported": 0,
                "unsupported": 0,
                "unverifiable": len(state.claims),
            },
        }
        run.write_text("final.md", state.final_survey)
        run.write_json("verification.json", state.verification)
        payload = build_result(task, state)
        run.write_json("result.json", payload)

    return payload


DEFAULT_SECTION_TITLES = (
    "Introduction",
    "Problem Definition",
    "Taxonomy",
    "Method Comparison",
    "Future Directions",
)


def _default_outline(analyses: list[PaperAnalysis]) -> Outline:
    """dry-run 专用：无模型产出时给出默认章节骨架，仅用于离线检查 Prompt。"""
    available = [item.paper_id for item in analyses if item.available]
    sections = [
        OutlineSection(
            title=title,
            purpose=f"Dry-run placeholder: {title}.",
            papers=list(available),
        )
        for title in DEFAULT_SECTION_TITLES
    ]
    return Outline(sections=sections)


def render_writer_prompts(
    writer: SurveyWriter,
    task: TaskInput,
    state: SurveyState,
    papers: PaperSet,
    run: RunWriter,
) -> None:
    """dry-run：渲染全部 Section 的 Prompt，便于离线检查。"""
    for index, section in enumerate(state.outline.sections, start=1):
        messages = writer.build_section_messages(task, section, state.paper_analyses, papers)
        run.write_text(f"prompts/writer/{index:02d}.rendered.md", str(messages[-1]["content"]))


def _usage_snapshot(provider: LLMProvider) -> dict[str, int]:
    return dict(provider.usage or {"prompt": 0, "completion": 0})


def _usage_delta(provider: LLMProvider, before: dict[str, int]) -> dict[str, int]:
    """计算某个 Stage 内的 token 增量（Reader/Writer 包含多次调用）。"""
    after = _usage_snapshot(provider)
    return {key: after.get(key, 0) - before.get(key, 0) for key in ("prompt", "completion")}


def build_result(task: TaskInput, state: SurveyState) -> dict[str, Any]:
    """构造对外的结构化结果（Evaluation 接口契约）。"""
    return {
        "task": {
            "topic": task.topic,
            "research_questions": list(task.research_questions),
        },
        "papers": [
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "year": paper.year,
                "source": paper.source,
            }
            for paper in state.papers
        ],
        "survey": state.final_survey,
        "claims": [claim.to_dict() for claim in state.claims],
        "citations": [citation.to_dict() for citation in state.citation_map],
        "evidence_map": list(state.verification.get("results", [])),
    }
