"""Survey Pipeline（Step 2）：`Topic + Source Papers → Paper Analysis → Survey`。

Stage 顺序：
    literature_manager → paper_reader → survey_writer → finalize

后续 Step 依次插入 knowledge_organizer / outline_planner / citation_verifier。
约定：每个 Stage 只消费最小必要 Context，产物写入 SurveyState 并落盘到 runs/<task_id>/。
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.agents.paper_reader import PaperReader, ReaderConfig
from app.agents.writer import SimpleSurveyWriter, WriterConfig, WriterResult
from app.config import AppConfig
from app.core.types import PaperSet, SurveyState, TaskInput, WriterOutput
from app.io.exporter import RunWriter
from app.model.provider import LLMError, LLMProvider, LLMResponse
from app.prompts.loader import PromptLoader

STAGE_LITERATURE = "literature_manager"
STAGE_READER = "paper_reader"
STAGE_WRITER = "survey_writer"
STAGE_FINALIZE = "finalize"
WRITER_PROMPT = "writer"
READER_PROMPT = "paper_reader"


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
    writer = SimpleSurveyWriter(provider, prompts, config.model, writer_config)

    with run.stage(STAGE_LITERATURE, "task.json", "papers.json"):
        run.write_json("papers.json", [paper.to_dict() for paper in state.papers])

    reader_usage_before = _usage_snapshot(provider)
    with run.stage(STAGE_READER, "papers.json", "analyses.json") as stats:
        if dry_run:
            if state.papers:
                messages = reader.build_messages(state.papers[0])
                run.write_text("prompts/paper_reader.rendered.md", str(messages[-1]["content"]))
        else:
            state.paper_analyses = await reader.read_all(state.papers)
        stats["token_usage"] = _usage_delta(provider, reader_usage_before)
        run.write_json("analyses.json", [item.to_dict() for item in state.paper_analyses])

    writer_usage_before = _usage_snapshot(provider)
    with run.stage(STAGE_WRITER, "analyses.json", "draft.md") as stats:
        if dry_run:
            messages = writer.build_messages(task, state.paper_analyses, papers)
            run.write_text("prompts/writer.rendered.md", str(messages[-1]["content"]))
            result = WriterResult(output=WriterOutput(), messages=messages)
        else:
            result = await asyncio.to_thread(
                writer.write, task, state.paper_analyses, papers
            )
        stats["token_usage"] = _usage_delta(provider, writer_usage_before)
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


def _usage_snapshot(provider: LLMProvider) -> dict[str, int]:
    return dict(provider.usage or {"prompt": 0, "completion": 0})


def _usage_delta(provider: LLMProvider, before: dict[str, int]) -> dict[str, int]:
    """计算某个 Stage 内的 token 增量（Reader/Writer 可能包含多次调用）。"""
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
