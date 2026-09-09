#!/usr/bin/env python3
"""评测侧工程约定自检。

用法：
    python check_eval_repo.py <repo-root> [--evaluator evaluator]

检查项（FAIL 必须先修复，WARN 需要人工确认）：
    1. 疑似硬编码 API Key（沿用 app skill 的占位值白名单，只回显路径不回显内容）；
    2. `API_key.conf` / `results/` 被 git 跟踪；
    3. Evaluator 直接 import `app.agents.*`（应只依赖输出契约）；
    4. Judge Prompt 文件缺失、缺少六段结构或未记录 version；
    5. Evaluator 中出现 temperature > 0（Judge 与 Answerer 必须可复现）；
    6. 出现整体打分式 Prompt（"rate this survey from 1 to 10"）；
    7. 对 dataset 目录的写打开（评测阶段必须只读）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SECRET_FILE = "API_key.conf"
KEY_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|api[_-]?key\s*[:=]\s*[\"']([^\"'\s]{12,})[\"'])",
    re.IGNORECASE,
)
#: 明显的占位值 / 测试假值，不算硬编码密钥
DUMMY_PATTERN = re.compile(
    r"^(sk[-_](unit|test|smoke|fake|dummy|example|local|demo|xxx)"
    r"|your_|changeme|placeholder|\$\{|x{8,})",
    re.IGNORECASE,
)
WHOLE_SCORING_PATTERNS = (
    re.compile(r"(?i)rate\s+this\s+survey\s+from\s+1\s+to\s+10"),
    re.compile(r"(?i)give\s+an\s+overall\s+score\s+of\s+1"),
)
TEMPERATURE_PATTERN = re.compile(r"temperature\s*[:=]\s*([0-9]*\.?[0-9]+)")
DATASET_WRITE_PATTERN = re.compile(r"(?i)dataset")
WRITE_CALL_PATTERN = re.compile(r"(?i)(open\([^)]*['\"][rwab+]*w|write_text\s*\(|\.write\s*\()")

PROMPT_SECTIONS = ("Role", "Input Schema", "Output Schema", "Rules", "Few-shot", "Failure")
JUDGE_PROMPTS = (
    "factual",
    "citation",
    "coverage",
    "synthesis",
    "outline",
    "quiz_answer",
    "terminology",
)

SCAN_SUFFIXES = {".py", ".yaml", ".yml", ".toml"}
PROMPT_SUFFIXES = {".md", ".py"}
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


def _iter_files(root: Path, suffixes: set[str]):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        parts = set(path.relative_to(root).parts)
        if parts & SKIP_DIRS:
            continue
        if path.name.endswith(".example") or ".example." in path.name:
            continue
        yield path


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def scan_keys(text: str) -> bool:
    """返回是否包含疑似真实密钥；只返回布尔值，不回显密钥原文。"""
    for match in KEY_PATTERN.finditer(text):
        candidate = match.group(2) or match.group(1)
        if DUMMY_PATTERN.search(candidate):
            continue
        return True
    return False


def _git_tracked(root: Path) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return set()
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def check(root: Path, evaluator_dir: str) -> tuple[list[str], list[str]]:
    """返回 (FAIL, WARN) 列表。"""
    fails: list[str] = []
    warns: list[str] = []

    if not (root / "pyproject.toml").is_file():
        fails.append(f"根目录缺少 pyproject.toml：{root}")

    # 1. 密钥（跳过 API_key.conf 本身与 .example 模板）
    for path in _iter_files(root, SCAN_SUFFIXES):
        if path.name == SECRET_FILE:
            continue
        if scan_keys(_read(path)):
            fails.append(f"疑似硬编码密钥：{path.relative_to(root)}")

    # 2. git 跟踪
    tracked = _git_tracked(root)
    for forbidden in (SECRET_FILE, "configs/config.yaml", "configs/eval.yaml"):
        if forbidden in tracked:
            fails.append(f"{forbidden} 不应被 git 跟踪")
    if any(name.startswith("results/") for name in tracked):
        fails.append("results/ 不应被 git 跟踪")

    evaluator = root / evaluator_dir
    if not evaluator.is_dir():
        warns.append(f"未找到 evaluator 目录：{evaluator}（跳过模块级检查）")
        return fails, warns

    python_files = list(_iter_files(evaluator, {".py"}))
    for path in python_files:
        text = _read(path)
        rel = path.relative_to(root)

        # 3. 越界依赖
        if re.search(r"from\s+app\.agents|import\s+app\.agents", text):
            fails.append(f"Evaluator 不应 import app.agents：{rel}")

        # 5. temperature
        for match in TEMPERATURE_PATTERN.finditer(text):
            if float(match.group(1)) > 0:
                fails.append(
                    f"Evaluator 的 temperature 必须为 0（Judge/Answerer 需可复现）："
                    f"{rel}（发现 {match.group(1)}）"
                )
                break

        # 7. dataset 写操作
        for line in text.splitlines():
            if DATASET_WRITE_PATTERN.search(line) and WRITE_CALL_PATTERN.search(line):
                fails.append(f"评测阶段禁止写 dataset：{rel}")
                break

    # 4. Judge Prompt
    prompts_dir = evaluator / "prompts"
    for name in JUDGE_PROMPTS:
        target = prompts_dir / f"{name}.md"
        if not target.is_file():
            warns.append(f"缺少 Judge Prompt：{target.relative_to(root)}")
            continue
        text = _read(target)
        missing = [section for section in PROMPT_SECTIONS if section.lower() not in text.lower()]
        if missing:
            fails.append(f"{target.relative_to(root)} 缺少段落：{missing}")
        if not re.search(r"(?i)version\s*[:=]\s*\d", text):
            fails.append(f"{target.relative_to(root)} 未记录 version")

    # 6. 整体打分式 Prompt
    for path in _iter_files(evaluator, PROMPT_SUFFIXES):
        text = _read(path)
        for pattern in WHOLE_SCORING_PATTERNS:
            if pattern.search(text):
                fails.append(f"禁止整体打分式 Judge：{path.relative_to(root)}")
                break

    return fails, warns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="评测侧工程约定自检。")
    parser.add_argument("root", nargs="?", default=".", help="仓库根目录")
    parser.add_argument("--evaluator", default="evaluator", help="evaluator 目录名")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    fails, warns = check(root, args.evaluator)

    for warn in warns:
        print(f"WARN {warn}")
    for fail in fails:
        print(f"FAIL {fail}")
    print(f"\n{len(fails)} FAIL / {len(warns)} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
