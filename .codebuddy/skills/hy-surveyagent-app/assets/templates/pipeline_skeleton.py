"""Hy-SurveyAgent Pipeline 骨架（模板）。

用法：复制为 `app/main.py`，按 TODO 逐项补全实现。
若项目已存在 `app/core/state.py` / `app/core/pipeline.py`，请合并而非覆盖。

约束：
    1. 只有 `app/model/hy3_adapter.py` 允许调用 Hy3 SDK，本文件只依赖 LLMProvider 抽象。
    2. 每个 Stage 只接收最小必要 Context，并把产物写回 SurveyState。
    3. 每个 Stage 落盘 `runs/<task_id>/` 对应产物，并写一条 stage 日志。
    4. 单篇论文读取失败标记 unavailable，不得中断整体流程。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.model.provider import LLMProvider  # TODO: 按实际包路径调整


@dataclass
class SurveyState:
    """跨 Stage 传递的统一执行状态（字段定义见 references/data-contracts.md）。"""

    task_spec: dict[str, Any] = field(default_factory=dict)
    papers: list[dict[str, Any]] = field(default_factory=list)
    paper_analyses: list[dict[str, Any]] = field(default_factory=list)
    knowledge_base: dict[str, Any] = field(default_factory=dict)
    outline: dict[str, Any] = field(default_factory=dict)
    draft: str = ""
    claims: list[dict[str, Any]] = field(default_factory=list)
    citation_map: list[dict[str, Any]] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    final_survey: str = ""


class StageLogger:
    """把每个 Stage 的运行信息追加到 runs/<task_id>/logs/stages.jsonl。"""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / "logs" / "stages.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        stage: str,
        input_ref: str,
        output_ref: str,
        latency_ms: int,
        token_usage: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        record = {
            "task_id": self.path.parent.parent.name,
            "stage": stage,
            "input_ref": input_ref,
            "output_ref": output_ref,
            "latency_ms": latency_ms,
            "token_usage": token_usage or {"prompt": 0, "completion": 0},
            "error": error,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def dump_json(run_dir: Path, name: str, payload: Any) -> str:
    """落盘一个中间产物，返回相对路径供日志引用。"""
    target = run_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return name


async def run_stage(
    logger: StageLogger,
    stage: str,
    input_ref: str,
    output_ref: str,
    fn: Callable[[], Awaitable[tuple[Any, dict[str, int]]]],
) -> Any:
    """统一 Stage 包装：计时、落盘、日志、异常记录。"""
    started = time.perf_counter()
    try:
        payload, token_usage = await fn()
    except Exception as exc:  # noqa: BLE001 - 统一记录后向上抛，由 Pipeline 决定回退
        logger.log(stage, input_ref, output_ref, int((time.perf_counter() - started) * 1000), error=str(exc))
        raise
    logger.log(stage, input_ref, output_ref, int((time.perf_counter() - started) * 1000), token_usage)
    return payload


# --------------------------------------------------------------------------- #
# Step 1-6：各 Stage 实现
# --------------------------------------------------------------------------- #

async def analyze_task(llm: LLMProvider, state: SurveyState, run_dir: Path, logger: StageLogger) -> None:
    """Task Analyzer：Topic + Questions + Constraints → TaskSpec。"""
    # TODO: 加载 app/prompts/task_analyzer.md，调用 llm.generate，解析 JSON 并做 Schema 校验
    raise NotImplementedError


async def load_papers(task_spec: dict[str, Any], benchmark_mode: bool = True) -> list[dict[str, Any]]:
    """Literature Manager：Benchmark 模式下加载固定 Source Paper Set。"""
    # TODO: benchmark_mode=True 时使用固定论文集，禁止联网检索
    raise NotImplementedError


async def read_papers(
    llm: LLMProvider,
    state: SurveyState,
    run_dir: Path,
    logger: StageLogger,
    max_concurrency: int = 8,
) -> None:
    """Paper Reader：并行把每篇论文转成 PaperAnalysis。"""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _read_one(paper: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            # TODO: 加载 app/prompts/paper_reader.md，单篇调用，解析 JSON
            raise NotImplementedError

    raw = await asyncio.gather(*(_read_one(p) for p in state.papers), return_exceptions=True)
    analyses: list[dict[str, Any]] = []
    for paper, result in zip(state.papers, raw, strict=True):
        if isinstance(result, Exception):
            logger.log("paper_reader", "papers.json", "analyses.json", 0, error=str(result))
            analyses.append({"paper_id": paper.get("paper_id"), "status": "unavailable"})
        else:
            analyses.append(result)
    state.paper_analyses = analyses


async def organize_knowledge(llm: LLMProvider, state: SurveyState, run_dir: Path, logger: StageLogger) -> None:
    """Knowledge Organizer：PaperAnalysis[] → KnowledgeBase。"""
    # TODO: 只接收 TaskSpec + PaperAnalysis，禁止注入论文全文
    raise NotImplementedError


async def plan_outline(llm: LLMProvider, state: SurveyState, run_dir: Path, logger: StageLogger) -> None:
    """Outline Planner：TaskSpec + KnowledgeBase → Outline。"""
    # TODO: 每个 Section 必须包含 purpose / papers / key_claims
    raise NotImplementedError


async def write_survey(llm: LLMProvider, state: SurveyState, run_dir: Path, logger: StageLogger) -> None:
    """Survey Writer：Outline + 相关证据 → draft.md + claims + citation_map。"""
    # TODO: 禁止输出 citation_map 之外的引用编号，禁止编造论文
    raise NotImplementedError


async def verify_citations(llm: LLMProvider, state: SurveyState, run_dir: Path, logger: StageLogger) -> None:
    """Citation Verifier：Claim → Citation → Paper → Evidence。"""
    # TODO: 输出 support(true/false/null) + evidence + confidence
    raise NotImplementedError


def finalize(state: SurveyState, run_dir: Path) -> dict[str, Any]:
    """汇总最终结果，输出对齐 Evaluation 接口契约。"""
    result = {
        "task": state.task_spec,
        "papers": [{"paper_id": p.get("paper_id"), "title": p.get("title")} for p in state.papers],
        "survey": state.final_survey or state.draft,
        "claims": state.claims,
        "citations": state.citation_map,
        "evidence_map": state.verification.get("results", []),
    }
    dump_json(run_dir, "result.json", result)
    return result


async def run_pipeline(
    llm: LLMProvider,
    task_input: dict[str, Any],
    run_dir: Path,
    max_concurrency: int = 8,
) -> dict[str, Any]:
    """按固定顺序执行全部 Stage。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = StageLogger(run_dir)
    state = SurveyState()
    dump_json(run_dir, "meta.json", {"task_input": task_input, "max_concurrency": max_concurrency})

    async def _stage(name: str, in_ref: str, out_ref: str, fn: Callable[[], Awaitable[tuple[Any, dict[str, int]]]]) -> Any:
        return await run_stage(logger, name, in_ref, out_ref, fn)

    state.task_spec = await _stage("task_analyzer", "meta.json", "task.json", lambda: analyze_task(llm, state, run_dir, logger))
    dump_json(run_dir, "task.json", state.task_spec)

    state.papers = await load_papers(state.task_spec, benchmark_mode=True)
    dump_json(run_dir, "papers.json", state.papers)

    await read_papers(llm, state, run_dir, logger, max_concurrency=max_concurrency)
    dump_json(run_dir, "analyses.json", state.paper_analyses)

    await organize_knowledge(llm, state, run_dir, logger)
    dump_json(run_dir, "knowledge.json", state.knowledge_base)

    await plan_outline(llm, state, run_dir, logger)
    dump_json(run_dir, "outline.json", state.outline)

    await write_survey(llm, state, run_dir, logger)
    (run_dir / "draft.md").write_text(state.draft, encoding="utf-8")
    dump_json(run_dir, "claims.json", {"claims": state.claims, "citation_map": state.citation_map})

    await verify_citations(llm, state, run_dir, logger)
    dump_json(run_dir, "verification.json", state.verification)

    state.final_survey = state.draft
    (run_dir / "final.md").write_text(state.final_survey, encoding="utf-8")
    return finalize(state, run_dir)


def main() -> None:
    # TODO: 解析 CLI 参数（--topic / --papers / --config），构造 LLMProvider 与 run_dir
    # from app.model.hy3_adapter import Hy3Adapter
    # asyncio.run(run_pipeline(Hy3Adapter.from_config(), task_input, run_dir))
    raise NotImplementedError


if __name__ == "__main__":
    main()
