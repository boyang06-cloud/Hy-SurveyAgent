"""复用现有 Pipeline，在后台执行任务并汇总真实产物。"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import AppConfig, load_config
from app.core.meta import build_meta
from app.core.pipeline import PROMPTS, run_pipeline
from app.core.types import PaperSet, TaskInput
from app.io.exporter import RunWriter
from app.io.workspace import ARTIFACTS, read_json, run_path, stage_records
from app.model.hy3_adapter import Hy3Adapter
from app.prompts.loader import PromptLoader
from app.web.schemas import RunRequest

LOGGER = logging.getLogger(__name__)


class BusyError(RuntimeError):
    pass


@dataclass
class Workspace:
    config: AppConfig
    config_path: Path | None = None
    active: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def submit(self, request: RunRequest, papers: PaperSet) -> str:
        # 先校验配置；失败时不创建空任务，也不把原始异常发往浏览器。
        config = load_config(
            root=self.config.root,
            config_path=self.config_path,
            require_secrets=request.mode == "generate",
        )
        config.pipeline.enable_citation_verification = True
        with self.lock:
            if self.active:
                raise BusyError("已有任务正在运行，请完成后再创建新任务。")
            run_id = f"t-{datetime.now(UTC):%Y-%m-%d}-{uuid4().hex[:8]}"
            run = RunWriter.create(config.root, config.paths.runs_dir, run_id, request.topic)
            task = TaskInput(topic=request.topic, research_questions=request.research_questions)
            run.write_meta(
                build_meta(
                    config.root,
                    run_id,
                    task.topic,
                    extra={
                        "config": config.describe(),
                        "prompts": PromptLoader(config.prompts_dir()).describe(list(PROMPTS)),
                        "web_mode": request.mode,
                    },
                )
            )
            run.write_json("task.json", task.to_dict())
            run.write_json("papers.json", [paper.to_dict() for paper in papers])
            run.write_json("web_status.json", {"status": "running", "mode": request.mode})
            self.active.add(run_id)
            threading.Thread(
                target=self._execute,
                args=(config, task, papers, run, request.mode),
                daemon=True,
            ).start()
        return run_id

    def _execute(
        self,
        config: AppConfig,
        task: TaskInput,
        papers: PaperSet,
        run: RunWriter,
        mode: str,
    ) -> None:
        status = "dry_run" if mode == "dry_run" else "completed"
        error = ""
        try:
            if mode == "dry_run":
                asyncio.run(run_pipeline(None, task, papers, run, config=config, dry_run=True))
            else:
                with Hy3Adapter.from_config(config) as provider:
                    asyncio.run(run_pipeline(provider, task, papers, run, config=config))
        except Exception as exc:
            status = "failed"
            # 只落异常类型：原始信息可能包含凭据或请求体，不适合写入产物与日志。
            error = type(exc).__name__
            LOGGER.error("后台任务失败 run_id=%s error=%s", run.task_id, error)
        finally:
            try:
                payload: dict[str, str] = {"status": status, "mode": mode}
                if error:
                    payload["error"] = error
                run.write_json("web_status.json", payload)
            finally:
                with self.lock:
                    self.active.discard(run.task_id)

    def summary(self, folder: Path) -> dict[str, Any]:
        task = read_json(folder / "task.json", {})
        meta = read_json(folder / "meta.json", {})
        state = read_json(folder / "web_status.json", {})
        logs = stage_records(folder)
        status = state.get("status", "")
        with self.lock:
            running = folder.name in self.active
        if running:
            status = "running"
        elif status == "running":
            status = "interrupted"
        elif not status:
            if any(row.get("error") for row in logs):
                status = "failed"
            elif read_json(folder / "result.json") is not None:
                status = (
                    "completed"
                    if read_json(folder / "result.json", {}).get("survey")
                    else "dry_run"
                )
            else:
                status = "incomplete"
        papers = read_json(folder / "papers.json", [])
        if isinstance(papers, dict):
            papers = papers.get("papers", [])
        verification = read_json(folder / "verification.json", {})
        return {
            "id": folder.name,
            "topic": task.get("topic") or meta.get("topic") or folder.name,
            "created_at": meta.get("created_at", ""),
            "status": status,
            "paper_count": len(papers),
            "verification": verification.get("summary", {}),
            "stages": logs,
        }

    def list_runs(self) -> list[dict[str, Any]]:
        base = self.config.runs_dir()
        if not base.is_dir():
            return []
        summaries = []
        for folder in base.iterdir():
            try:
                safe = run_path(base, folder.name)
                if (safe / "task.json").is_file():
                    summaries.append(self.summary(safe))
            except FileNotFoundError:
                continue
        return sorted(summaries, key=lambda row: (row["created_at"], row["id"]), reverse=True)

    def status(self, run_id: str) -> dict[str, Any]:
        """轮询用的轻量状态：不含产物全文。"""
        return self.summary(run_path(self.config.runs_dir(), run_id))

    def detail(self, run_id: str) -> dict[str, Any]:
        folder = run_path(self.config.runs_dir(), run_id)
        result = self.summary(folder)
        artifacts: dict[str, Any] = {}
        for name in ARTIFACTS:
            path = folder / name
            if path.is_symlink() or not path.is_file():
                continue
            # 阶段未完成时会写入空产物（如离线检查的 draft.md），不展示为可下载结果。
            if name.endswith(".json"):
                data = read_json(path)
                if data not in (None, {}, [], ""):
                    artifacts[name] = data
            else:
                text = path.read_text(encoding="utf-8")
                if text.strip():
                    artifacts[name] = text
        result["artifacts"] = artifacts
        return result
