"""运行元信息采集，写入 runs/<task_id>/meta.json，用于结果复现。"""

from __future__ import annotations

import platform
import subprocess
import time
from pathlib import Path
from typing import Any


def git_info(root: Path) -> dict[str, str]:
    """采集 git 提交号与工作区是否 dirty；非 git 仓库时返回 unknown。"""
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {"commit": "unknown", "dirty": "unknown"}
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else "unknown",
        "dirty": "yes" if status.stdout.strip() else "no",
    }


def build_meta(
    root: Path,
    task_id: str,
    topic: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 meta.json 内容。extra 中禁止包含密钥。"""
    meta: dict[str, Any] = {
        "task_id": task_id,
        "topic": topic,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "app_version": _app_version(),
        **git_info(root),
    }
    if extra:
        meta.update(extra)
    return meta


def _app_version() -> str:
    from app import __version__

    return __version__
