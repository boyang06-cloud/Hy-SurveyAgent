"""Hy-SurveyAgent CLI 入口。

示例：
    uv run python -m app.main --topic "..." --papers examples/papers_vlm.json
    uv run python -m app.main --topic "..." --papers ... --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import Any

from app.agents.paper_reader import ReaderError
from app.agents.writer import WriterError
from app.config import ConfigError, load_config
from app.core.meta import build_meta
from app.core.pipeline import READER_PROMPT, WRITER_PROMPT, run_pipeline
from app.core.types import PaperSet, TaskInput
from app.io.exporter import RunWriter
from app.io.loader import LoaderError, load_task_input
from app.model.hy3_adapter import Hy3Adapter
from app.model.provider import LLMError
from app.prompts.loader import PromptError, PromptLoader
from app.retrieval.benchmark_loader import build_benchmark_retriever
from app.retrieval.retriever import RetrieverError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hy-surveyagent",
        description="Hy-SurveyAgent：基于 Hy3 的学术 Survey 生成 Agent",
    )
    parser.add_argument("--topic", help="研究主题（与 --task-file 二选一）")
    parser.add_argument(
        "--task-file", help="任务文件（YAML / JSON），可带 research_questions 等字段"
    )
    parser.add_argument("--papers", required=True, help="论文集文件（JSON / JSONL / YAML）")
    parser.add_argument(
        "--config", help="运行配置路径，默认 configs/config.yaml"
    )
    parser.add_argument("--run-id", help="指定运行 ID，默认按日期自增")
    parser.add_argument("--limit", type=int, help="只取前 N 篇论文（调试用）")
    parser.add_argument("--dry-run", action="store_true", help="不调用模型，仅渲染并落盘 Prompt")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.topic and not args.task_file:
            raise ConfigError("必须提供 --topic 或 --task-file 之一。")

        config = load_config(config_path=args.config, require_secrets=not args.dry_run)
        task = (
            load_task_input(args.task_file)
            if args.task_file
            else TaskInput(topic=(args.topic or "").strip())
        )
        if not task.topic:
            raise LoaderError("研究主题为空，请提供 --topic 或在任务文件中填写 topic。")

        # Benchmark 模式：固定 Source Paper Set，运行期不联网检索
        retriever = build_benchmark_retriever(args.papers, limit=args.limit)
        papers = retriever.retrieve(task)
        if not papers.papers:
            raise LoaderError(f"论文集合为空或全部被过滤：{args.papers}")

        run = RunWriter.create(config.root, config.paths.runs_dir, args.run_id, topic=task.topic)
        prompts = PromptLoader(config.prompts_dir())
        run.write_meta(
            build_meta(
                config.root,
                run.task_id,
                task.topic,
                extra={
                    "config": config.describe(),
                    "prompts": prompts.describe([READER_PROMPT, WRITER_PROMPT]),
                    "input": {"papers": str(args.papers), "limit": args.limit},
                },
            )
        )
        run.write_json("task.json", task.to_dict())

        if args.dry_run:
            payload: dict[str, Any] = asyncio.run(
                run_pipeline(None, task, papers, run, config=config, dry_run=True)
            )
        else:
            with Hy3Adapter.from_config(config) as llm:
                payload = asyncio.run(run_pipeline(llm, task, papers, run, config=config))

        _print_summary(run, papers, payload, dry_run=args.dry_run)
        return 0

    except (
        ConfigError,
        LoaderError,
        ReaderError,
        RetrieverError,
        WriterError,
        LLMError,
        PromptError,
        OSError,
    ) as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _print_summary(
    run: RunWriter, papers: PaperSet, payload: dict[str, Any], *, dry_run: bool
) -> None:
    print(f"run_id        : {run.task_id}")
    print(f"run_dir       : {run.run_dir}")
    print(
        f"papers        : {len(papers.papers)}"
        f"（去重移除 {papers.duplicates_removed} 篇，过滤 {papers.filtered_out} 篇）"
    )
    print(f"claims        : {len(payload.get('claims', []))}")
    print(f"citations     : {len(payload.get('citations', []))}")
    print(f"survey_chars  : {len(payload.get('survey', ''))}")
    if dry_run:
        print("dry-run       : 已跳过模型调用，Prompt 见 runs/<run_id>/prompts/")


if __name__ == "__main__":
    sys.exit(main())
