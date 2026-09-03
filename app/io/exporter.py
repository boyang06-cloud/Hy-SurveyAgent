"""运行产物落盘与 Stage 日志。

每次运行写入 ``runs/<task_id>/``，布局见
``.codebuddy/skills/hy-surveyagent-app/references/data-contracts.md`` 第 12 节。
日志只记录输入输出的引用路径，不写入 Prompt 全文、论文正文或密钥。
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class RunWriter:
    """一次运行的所有产物写入器。"""

    def __init__(self, run_dir: Path, task_id: str) -> None:
        self.run_dir = run_dir
        self.task_id = task_id

    @classmethod
    def create(
        cls,
        root: Path,
        runs_dir: str,
        run_id: str | None = None,
        topic: str = "",
    ) -> RunWriter:
        base = Path(runs_dir)
        base = base if base.is_absolute() else root / base
        task_id = run_id or _next_task_id(base)
        run_dir = base / task_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(exist_ok=True)
        if topic:
            (run_dir / "topic.txt").write_text(topic, encoding="utf-8")
        return cls(run_dir=run_dir, task_id=task_id)

    def path(self, name: str) -> Path:
        return self.run_dir / name

    def write_json(self, name: str, payload: Any) -> str:
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return name

    def write_text(self, name: str, text: str) -> str:
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return name

    def write_meta(self, payload: dict[str, Any]) -> str:
        return self.write_json("meta.json", payload)

    def log_stage(
        self,
        stage: str,
        input_ref: str,
        output_ref: str,
        latency_ms: int,
        token_usage: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        record = {
            "task_id": self.task_id,
            "stage": stage,
            "input_ref": input_ref,
            "output_ref": output_ref,
            "latency_ms": latency_ms,
            "token_usage": token_usage or {"prompt": 0, "completion": 0},
            "error": error,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        log_path = self.run_dir / "logs" / "stages.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @contextlib.contextmanager
    def stage(self, name: str, input_ref: str, output_ref: str) -> Iterator[dict[str, Any]]:
        """Stage 计时与日志上下文；异常会被记录后继续向上抛出。

        usage:
            with run.stage("survey_writer", "outline.json", "draft.md") as stats:
                ...
                stats["token_usage"] = response.token_usage
        """
        stats: dict[str, Any] = {"token_usage": {"prompt": 0, "completion": 0}}
        started = time.perf_counter()
        error: str | None = None
        try:
            yield stats
        except Exception as exc:  # noqa: BLE001 - 记录后交还调用方决定回退策略
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.log_stage(
                stage=name,
                input_ref=input_ref,
                output_ref=output_ref,
                latency_ms=int((time.perf_counter() - started) * 1000),
                token_usage=stats.get("token_usage"),
                error=error,
            )


def _next_task_id(base: Path) -> str:
    """生成 `t-<YYYY-MM-DD>-<seq>`，seq 按当天已有运行数递增。"""
    stamp = time.strftime("%Y-%m-%d", time.localtime())
    prefix = f"t-{stamp}-"
    if base.is_dir():
        existing = sum(
            1 for child in base.iterdir() if child.is_dir() and child.name.startswith(prefix)
        )
        seq = existing + 1
    else:
        seq = 1
    return f"{prefix}{seq:03d}"
