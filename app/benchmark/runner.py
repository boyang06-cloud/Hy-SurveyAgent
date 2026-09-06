"""Benchmark Batch Runner（Step 6，docs 第 33 节 Benchmark Test）。

固定 `Topic + Source Papers`，批量执行完整 Pipeline，逐任务记录：
    - latency_ms：任务墙钟耗时；
    - token_usage：prompt / completion token 消耗（cost 的统一代理指标）；
    - output：claims / citations / survey_chars 与契约校验结果。

单个任务失败只记录错误并继续，绝不中断批次（与 Paper Reader 同级容错）。
汇总写入 ``<results_dir>/benchmark/<batch_id>/summary.json``（results/ 不入库）。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.benchmark.manifest import BenchmarkTask, load_manifest
from app.config import AppConfig
from app.core.generator import HySurveyAgentGenerator
from app.core.meta import build_meta
from app.core.pipeline import PROMPTS
from app.io.exporter import RunWriter
from app.io.loader import LoaderError
from app.model.provider import LLMProvider
from app.prompts.loader import PromptLoader
from app.retrieval.benchmark_loader import load_benchmark_source


@dataclass
class TaskResult:
    """单个 Benchmark 任务的执行记录。"""

    task_id: str
    run_id: str
    topic: str
    status: str  # ok | failed
    latency_ms: int = 0
    token_usage: dict[str, int] = field(default_factory=dict)
    n_papers: int = 0
    n_claims: int = 0
    n_citations: int = 0
    survey_chars: int = 0
    violations: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BenchmarkRunner:
    """按清单批量执行生成任务并落盘汇总结果。"""

    def __init__(
        self,
        llm: LLMProvider,
        config: AppConfig,
        *,
        limit: int | None = None,
    ) -> None:
        self.llm = llm
        self.config = config
        self.limit = limit
        self._batch_id = ""

    def run(self, manifest_path: str | Path) -> dict[str, Any]:
        """执行整批任务；返回汇总字典并写入 results/benchmark/<batch_id>/summary.json。"""
        manifest_file = Path(manifest_path)
        tasks = load_manifest(
            manifest_file,
            search_paths=[manifest_file.parent, self.config.root],
        )
        if self.limit is not None:
            tasks = tasks[: max(0, self.limit)]

        self._batch_id = f"b-{time.strftime('%Y%m%d-%H%M%S')}"
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        started_perf = time.perf_counter()

        results = [self._run_one(task, manifest_file) for task in tasks]
        passed = sum(1 for result in results if result.status == "ok")
        summary: dict[str, Any] = {
            "batch_id": self._batch_id,
            "manifest": str(manifest_file),
            "started_at": started_at,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "wall_ms": int((time.perf_counter() - started_perf) * 1000),
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "total_latency_ms": sum(result.latency_ms for result in results),
            "total_token_usage": {
                "prompt": sum(result.token_usage.get("prompt", 0) for result in results),
                "completion": sum(result.token_usage.get("completion", 0) for result in results),
            },
            "config": self.config.describe(),
            "tasks": [result.to_dict() for result in results],
        }
        self._write_summary(summary)
        return summary

    def _run_one(self, task: BenchmarkTask, manifest_file: Path) -> TaskResult:
        """执行单个任务；任何异常收敛为 failed 记录，不中断批次。"""
        started = time.perf_counter()
        usage_before = _usage_snapshot(self.llm)
        result = TaskResult(task_id=task.task_id, run_id="", topic=task.topic, status="failed")

        try:
            papers = load_benchmark_source(task.papers)
            if not papers.papers:
                raise LoaderError(f"论文集合为空：{task.papers}")
            result.n_papers = len(papers)

            run = RunWriter.create(
                self.config.root, self.config.paths.runs_dir, None, topic=task.topic
            )
            result.run_id = run.task_id
            self._write_run_meta(run, task, manifest_file)

            generator = HySurveyAgentGenerator(self.llm, self.config)
            output = generator.generate(task.topic, papers, run=run)

            result.status = "ok"
            result.n_claims = len(output.claims)
            result.n_citations = len(output.citations)
            result.survey_chars = len(output.survey)
            result.violations = list(output.violations)
            if output.violations:
                result.error = "契约校验违规：" + "；".join(output.violations)
        except Exception as exc:  # noqa: BLE001 - 单任务失败必须可恢复
            result.error = f"{type(exc).__name__}: {exc}"

        result.latency_ms = int((time.perf_counter() - started) * 1000)
        result.token_usage = _usage_delta(self.llm, usage_before)
        return result

    def _write_run_meta(self, run: RunWriter, task: BenchmarkTask, manifest_file: Path) -> None:
        """为批量运行补写 meta.json（含批次上下文），保证可复现。"""
        prompts = PromptLoader(self.config.prompts_dir())
        run.write_meta(
            build_meta(
                self.config.root,
                run.task_id,
                task.topic,
                extra={
                    "config": self.config.describe(),
                    "prompts": prompts.describe(list(PROMPTS)),
                    "benchmark": {
                        "batch_id": self._batch_id,
                        "task_id": task.task_id,
                        "manifest": str(manifest_file),
                        "papers": task.papers,
                    },
                    "research_questions": list(task.research_questions),
                },
            )
        )

    def _write_summary(self, summary: dict[str, Any]) -> Path:
        out_dir = self.config.resolve(self.config.paths.results_dir) / "benchmark" / self._batch_id
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "summary.json"
        target.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target


def _usage_snapshot(provider: LLMProvider) -> dict[str, int]:
    return dict(provider.usage or {"prompt": 0, "completion": 0})


def _usage_delta(provider: LLMProvider, before: dict[str, int]) -> dict[str, int]:
    after = _usage_snapshot(provider)
    return {key: after.get(key, 0) - before.get(key, 0) for key in ("prompt", "completion")}
