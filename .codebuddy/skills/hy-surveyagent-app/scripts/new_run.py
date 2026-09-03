#!/usr/bin/env python3
"""为一次 Survey 运行创建 runs/<task_id>/ 目录与中间产物占位文件。

用法:
    python new_run.py [--task-id TASK_ID] [--topic "Research Topic"] [--root PROJECT_ROOT] [--force]

产物布局见 .codebuddy/skills/hy-surveyagent-app/references/data-contracts.md 第 12 节。
meta.json 会记录 git commit 与 Python 版本，用于结果复现。
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

JSON_PLACEHOLDERS = {
    "task.json": {"topic": ""},
    "papers.json": [],
    "analyses.json": [],
    "knowledge.json": {},
    "outline.json": {},
    "claims.json": {"claims": [], "citation_map": []},
    "verification.json": {"results": [], "summary": {}},
    "result.json": {},
}
MARKDOWN_FILES = ("draft.md", "final.md")


def auto_task_id() -> str:
    stamp = time.strftime("%Y-%m-%d", time.localtime())
    return f"t-{stamp}-001"


def git_info(root: Path) -> dict[str, str]:
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {"commit": "unknown", "dirty": "unknown"}
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else "unknown",
        "dirty": "yes" if dirty.stdout.strip() else "no",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化一次 Survey 运行的 runs/<task_id>/ 目录")
    parser.add_argument("--task-id", default=None, help=f"任务 ID，默认 {auto_task_id()}")
    parser.add_argument("--topic", default="", help="研究主题，写入 meta.json 与 task.json")
    parser.add_argument("--root", default=".", help="项目根目录，默认当前目录")
    parser.add_argument("--force", action="store_true", help="目录已存在时覆盖已有占位文件")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    task_id = args.task_id or auto_task_id()
    run_dir = root / "runs" / task_id

    if run_dir.exists() and any(run_dir.iterdir()) and not args.force:
        print(f"[FAIL] 目录非空: {run_dir}（使用 --force 覆盖占位文件）")
        return 1

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(exist_ok=True)

    meta = {
        "task_id": task_id,
        "topic": args.topic,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": platform.python_version(),
        "platform": platform.platform(),
        **git_info(root),
        "prompts": {},
        "config": {},
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    for name, payload in JSON_PLACEHOLDERS.items():
        target = run_dir / name
        if target.exists() and not args.force:
            continue
        payload = dict(payload) if isinstance(payload, dict) else payload
        if name == "task.json" and isinstance(payload, dict):
            payload["topic"] = args.topic
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for name in MARKDOWN_FILES:
        target = run_dir / name
        if not target.exists() or args.force:
            target.write_text("", encoding="utf-8")

    log_path = run_dir / "logs" / "stages.jsonl"
    if not log_path.exists() or args.force:
        log_path.write_text("", encoding="utf-8")

    print(f"created: {run_dir}")
    print("next: 运行 Pipeline 后产物将写入该目录，stage 日志见 logs/stages.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
