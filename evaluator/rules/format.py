"""Format 规则检查（D8c，纯规则，禁止引入 LLM）。

六类检查（每类 pass/fail 各计一次）：非空、无占位符、代码块围栏配对、
标题去重、标题层级合法、引用标记可解析。
"""

from __future__ import annotations

import re
from typing import Any

from evaluator.textutil import headings

_PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|\{\{")
_MARKER_RE = re.compile(r"\[(\d+)\]")

RULE_CATEGORIES: tuple[str, ...] = (
    "survey_nonempty",
    "no_placeholder",
    "balanced_code_fences",
    "unique_headings",
    "valid_heading_levels",
    "citations_resolved",
)


def check_format(survey_markdown: str, citation_ids: list[str]) -> dict[str, Any]:
    """返回 {issues: [...], passed: int, total: int}；issues 为违规说明。"""
    issues: list[str] = []
    known = {str(item) for item in citation_ids}

    if not survey_markdown.strip():
        issues.append("survey 为空")
    if _PLACEHOLDER_RE.search(survey_markdown):
        issues.append("存在未替换的占位符（TODO/TBD/FIXME/XXX/{{ }}）")
    if survey_markdown.count("```") % 2:
        issues.append("Markdown 代码块围栏不配对")

    items = headings(survey_markdown)
    titles = [title.strip().lower() for _, title in items]
    duplicated = sorted({title for title in titles if titles.count(title) > 1})
    if duplicated:
        issues.append(f"存在重复章节标题：{duplicated[:5]}")

    levels = [level for level, _ in items]
    jumped = any(
        current > previous + 1
        for previous, current in zip([0, *levels], levels, strict=False)  # 首个标题相对文档层级 0
    )
    if not items:
        issues.append("缺少任何 Markdown 标题")
    elif jumped:
        issues.append("标题层级跳跃不连续（如 # 之后直接 ###）")

    markers = {match.group(1) for match in _MARKER_RE.finditer(survey_markdown)}
    unresolved = sorted(markers - known)
    if unresolved:
        issues.append(f"引用标记未解析到 references：{unresolved[:5]}")

    passed = len(RULE_CATEGORIES) - len(issues)
    return {"issues": issues, "passed": passed, "total": len(RULE_CATEGORIES)}
