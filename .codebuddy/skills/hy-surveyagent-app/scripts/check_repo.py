#!/usr/bin/env python3
"""校验 Hy-SurveyAgent 仓库是否符合工程约定。

用法:
    python check_repo.py [project_root]      # project_root 默认当前目录

检查项:
    A. 密钥安全: API_key.conf 是否被 Git 跟踪、是否被 .gitignore 忽略、源码中是否疑似硬编码 Key
    B. 配置模板: API_key.conf.example / configs/config.example.yaml 是否存在
    C. 目录结构: app/ 下核心子目录是否齐全
    D. Prompt: app/prompts 下六个 Prompt 文件是否齐全
    E. Adapter 收敛: Hy3 SDK 的 import 是否只出现在 app/model/ 下

输出 PASS / WARN / FAIL 列表；存在 FAIL 时退出码为 1。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_DIRS = (
    "app/core",
    "app/agents",
    "app/retrieval",
    "app/model",
    "app/prompts",
    "app/io",
)
REQUIRED_PROMPTS = (
    "task_analyzer.md",
    "paper_reader.md",
    "organizer.md",
    "planner.md",
    "writer.md",
    "citation_verifier.md",
)
SECRET_FILE = "API_key.conf"
SECRET_TEMPLATE = "API_key.conf.example"
SDK_ALLOWED_DIR = "app/model"
SCAN_SUFFIXES = {".py", ".yaml", ".yml", ".toml"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "runs",
    "results",
    ".codebuddy",
}

# sk-xxx 形式，或被引号包裹的较长 api_key 字面量
KEY_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|api[_-]?key\s*[:=]\s*[\"']([^\"'\s]{12,})[\"'])",
    re.IGNORECASE,
)
# 明显的占位值 / 测试假值，不算硬编码密钥（单元测试与冒烟脚本使用固定假值是允许的）
DUMMY_PATTERN = re.compile(
    r"^(sk[-_](unit|test|smoke|fake|dummy|example|local|demo|xxx)"
    r"|your_|changeme|placeholder|\$\{|x{8,})",
    re.IGNORECASE,
)
# 疑似直接引用厂商 SDK（Hy3 / OpenAI / Anthropic）
SDK_PATTERN = re.compile(r"^\s*(?:from|import)\s+(hy3[a-z0-9_]*|openai|anthropic)\b", re.IGNORECASE | re.MULTILINE)


def scan_keys(text: str) -> bool:
    """返回是否包含疑似真实密钥。只返回布尔值，不回显密钥原文。"""
    for match in KEY_PATTERN.finditer(text):
        candidate = match.group(2) or match.group(1)
        if DUMMY_PATTERN.search(candidate):
            continue
        return True
    return False


class Report:
    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []

    def add(self, level: str, message: str) -> None:
        self.items.append((level, message))

    @property
    def failed(self) -> bool:
        return any(level == "FAIL" for level, _ in self.items)

    def render(self) -> str:
        order = {"FAIL": 0, "WARN": 1, "PASS": 2}
        lines = [f"[{level}] {msg}" for level, msg in sorted(self.items, key=lambda x: (order[x[0]], x[1]))]
        counts = {level: sum(1 for lv, _ in self.items if lv == level) for level in ("PASS", "WARN", "FAIL")}
        lines.append("")
        lines.append(f"summary: {counts['PASS']} passed, {counts['WARN']} warnings, {counts['FAIL']} failures")
        return "\n".join(lines)


def git_tracked(root: Path, relative: str) -> bool | None:
    """文件是否被 git 跟踪；非 git 仓库或 git 不可用时返回 None。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", relative],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def git_ignored(root: Path, relative: str) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", relative],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode not in (0, 1):
        return None
    return result.returncode == 0


def iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name.endswith(".example") or ".example." in path.name:
            continue
        yield path


def check_secrets(root: Path, report: Report) -> None:
    tracked = git_tracked(root, SECRET_FILE)
    if (root / SECRET_FILE).exists():
        if tracked is True:
            report.add("FAIL", f"{SECRET_FILE} 已被 Git 跟踪，立即从索引移除并轮换 Key")
        elif tracked is False:
            report.add("PASS", f"{SECRET_FILE} 未被 Git 跟踪")
        else:
            report.add("WARN", f"无法确认 {SECRET_FILE} 的 Git 跟踪状态（非 Git 仓库或 git 不可用）")

    ignored = git_ignored(root, SECRET_FILE)
    if ignored is True:
        report.add("PASS", f"{SECRET_FILE} 已被 .gitignore 忽略")
    elif ignored is False:
        report.add("FAIL", f".gitignore 未忽略 {SECRET_FILE}")

    hits: list[str] = []
    for path in iter_source_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if scan_keys(text):
            hits.append(str(path.relative_to(root)))
    if hits:
        report.add("FAIL", "疑似硬编码密钥，改从 API_key.conf 读取: " + ", ".join(hits[:5]))
    else:
        report.add("PASS", "源码中未发现硬编码密钥")


def check_templates(root: Path, report: Report) -> None:
    for template in (SECRET_TEMPLATE, "configs/config.example.yaml"):
        if (root / template).exists():
            report.add("PASS", f"配置模板存在: {template}")
        else:
            report.add("WARN", f"缺少配置模板: {template}")


def check_layout(root: Path, report: Report) -> None:
    missing = [d for d in REQUIRED_DIRS if not (root / d).is_dir()]
    if missing:
        report.add("WARN", "缺少目录（按开发进度可后续创建）: " + ", ".join(missing))
    else:
        report.add("PASS", "app/ 目录结构完整")

    prompts_dir = root / "app" / "prompts"
    if not prompts_dir.is_dir():
        report.add("WARN", "app/prompts 尚未创建，Prompt 必须外置为 .md 文件")
        return
    missing_prompts = [p for p in REQUIRED_PROMPTS if not (prompts_dir / p).is_file()]
    if missing_prompts:
        report.add("WARN", "缺少 Prompt 文件: " + ", ".join(missing_prompts))
    else:
        report.add("PASS", "app/prompts 六个 Prompt 文件齐全")


def check_adapter(root: Path, report: Report) -> None:
    adapter = root / SDK_ALLOWED_DIR / "hy3_adapter.py"
    if adapter.is_file():
        report.add("PASS", "Hy3 Adapter 存在: app/model/hy3_adapter.py")
    else:
        report.add("WARN", "缺少 app/model/hy3_adapter.py，Hy3 调用必须收敛到 Adapter")

    violations: list[str] = []
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(f"{SDK_ALLOWED_DIR}/"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SDK_PATTERN.search(text):
            violations.append(rel)
    if violations:
        report.add("FAIL", "SDK 调用未收敛到 Adapter，Agent 应只依赖 LLMProvider: " + ", ".join(violations[:5]))
    else:
        report.add("PASS", "未发现 Adapter 之外直接引用 SDK 的代码")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 Hy-SurveyAgent 仓库工程约定")
    parser.add_argument("project_root", nargs="?", default=".", help="项目根目录，默认当前目录")
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    if not root.is_dir():
        print(f"[FAIL] 目录不存在: {root}")
        return 1

    report = Report()
    check_secrets(root, report)
    check_templates(root, report)
    check_layout(root, report)
    check_adapter(root, report)

    print(report.render())
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
