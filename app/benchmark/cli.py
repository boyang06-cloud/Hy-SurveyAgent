"""Benchmark 批量运行 CLI。

用法：
    uv run python -m app.benchmark --manifest benchmark/manifest.jsonl
    uv run python -m app.benchmark --manifest ... --limit 2

退出码：0 全部任务成功；1 存在失败任务；2 致命错误（配置 / 清单 / 网络）。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from app.benchmark.runner import BenchmarkRunner
from app.config import ConfigError, load_config
from app.io.loader import LoaderError
from app.model.hy3_adapter import Hy3Adapter
from app.model.provider import LLMError
from app.prompts.loader import PromptError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hy-surveyagent-benchmark",
        description="Hy-SurveyAgent：Benchmark Batch Runner（固定 Topic + Source Papers 批量运行）",
    )
    parser.add_argument("--manifest", required=True, help="任务清单文件（JSONL / JSON / YAML）")
    parser.add_argument("--config", help="运行配置路径，默认 configs/config.yaml")
    parser.add_argument("--limit", type=int, help="只执行前 N 个任务（调试用）")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(config_path=args.config)
        with Hy3Adapter.from_config(config) as llm:
            runner = BenchmarkRunner(llm, config, limit=args.limit)
            summary = runner.run(args.manifest)
    except (ConfigError, LoaderError, LLMError, PromptError, OSError) as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"batch_id    : {summary['batch_id']}")
    print(f"tasks       : {summary['total']}（成功 {summary['passed']}，失败 {summary['failed']}）")
    print(f"latency_ms  : {summary['total_latency_ms']}（全部任务累计）")
    print(
        f"tokens      : prompt {summary['total_token_usage']['prompt']}"
        f" / completion {summary['total_token_usage']['completion']}"
    )
    summary_path = (
        config.resolve(config.paths.results_dir)
        / "benchmark"
        / summary["batch_id"]
        / "summary.json"
    )
    print(f"summary     : {summary_path}")
    for record in summary["tasks"]:
        flag = "ok    " if record["status"] == "ok" else "FAILED"
        line = f"  [{flag}] {record['task_id']} → {record['run_id'] or '-'}"
        if record["error"]:
            line += f" | {record['error'][:80]}"
        print(line)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
