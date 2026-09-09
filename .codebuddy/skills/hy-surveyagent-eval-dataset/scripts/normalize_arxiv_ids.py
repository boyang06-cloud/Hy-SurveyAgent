#!/usr/bin/env python3
"""arXiv ID 与参考文献规范化（build Step 2 的可复用实现）。

能力：
    - `normalize_arxiv_id`：去版本、去前缀、去空格，返回规范 ID 或 None；
    - `normalize_title`：折叠空白，供重复检测使用；
    - `normalize_ref_map`：规范化 `{id: {arxivId, title}}` 映射，去重并报告异常；
    - `normalize_topics`：规范化 ingest 产出的
      `{"<topic>": {"benchmark_refs": {...}, "human_refs": {...}}}`。

用法：
    python normalize_arxiv_ids.py --input build/01_ingested/topics.json \
                                  --output build/02_normalized/topics.json \
                                  --report build/02_normalized/normalize_report.json

纯标准库、无网络、无 LLM 调用。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

#: 新式 arXiv ID（2023-08 起为 5 位，历史上为 4 位）
NEW_ID = re.compile(r"^\d{4}\.\d{4,5}$")
#: 旧式 arXiv ID，如 cs/0701001、math.GT/0309136
OLD_ID = re.compile(r"^[a-z-]+(\.[A-Z]{2})?/\d{7}$")
VERSION_SUFFIX = re.compile(r"v\d+$", re.IGNORECASE)
PREFIXES = (
    "https://arxiv.org/abs/",
    "http://arxiv.org/abs/",
    "https://arxiv.org/pdf/",
    "http://arxiv.org/pdf/",
    "arxiv:",
    "arxiv.org/abs/",
    "doi:",
)


def normalize_arxiv_id(value: Any) -> str | None:
    """把任意写法归一化为规范 arXiv ID；非法返回 None。

    处理：`2308.04079v2` / `arXiv:2308.04079` / `https://arxiv.org/abs/2308.04079`
    / 前后空格 / 尾部 `.pdf`。
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None

    for prefix in PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.strip()
    if text.endswith(".pdf"):
        text = text[: -len(".pdf")]
    text = VERSION_SUFFIX.sub("", text).strip()
    text = re.sub(r"\s+", "", text)

    if NEW_ID.match(text) or OLD_ID.match(text):
        return text
    return None


def normalize_title(value: Any) -> str:
    """折叠空白，用于展示与去重比较。"""
    return re.sub(r"\s+", " ", str(value or "").strip())


def _title_key(title: str) -> str:
    """重复检测用的比较键：小写 + 去标点 + 折叠空白。"""
    return re.sub(r"[^a-z0-9]+", " ", normalize_title(title).lower()).strip()


def _merge_entry(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """合并同一 ID 的多条记录：优先保留更完整的非空字段。"""
    merged = dict(existing)
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        if key not in merged or merged[key] in (None, "", [], {}):
            merged[key] = value
    return merged


def normalize_ref_map(raw: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """规范化 `{id: {arxivId, title}}`；返回 (规范映射, 问题列表)。"""
    normalized: dict[str, str] = {}
    issues: list[dict[str, Any]] = []

    for raw_id, entry in (raw or {}).items():
        record = entry if isinstance(entry, dict) else {}
        arxiv_id = normalize_arxiv_id(record.get("arxivId") or raw_id)
        title = normalize_title(record.get("title"))

        if arxiv_id is None:
            issues.append({"type": "malformed_id", "raw_id": str(raw_id), "title": title})
            continue
        if not title:
            issues.append({"type": "missing_title", "arxiv_id": arxiv_id})

        if arxiv_id in normalized and normalized[arxiv_id] != title:
            if _title_key(normalized[arxiv_id]) == _title_key(title):
                issues.append(
                    {"type": "title_whitespace_diff", "arxiv_id": arxiv_id, "title": title}
                )
            else:
                issues.append(
                    {
                        "type": "conflicting_title",
                        "arxiv_id": arxiv_id,
                        "kept": normalized[arxiv_id],
                        "incoming": title,
                    }
                )
            continue
        normalized[arxiv_id] = title

    for arxiv_id, title in _duplicate_titles(normalized):
        issues.append({"type": "duplicate_title", "title": title, "arxiv_ids": arxiv_id})

    return normalized, issues


def _duplicate_titles(mapping: dict[str, str]) -> list[tuple[list[str], str]]:
    """找出同标题不同 ID 的分组。"""
    buckets: dict[str, list[str]] = {}
    for arxiv_id, title in mapping.items():
        key = _title_key(title)
        if key:
            buckets.setdefault(key, []).append(arxiv_id)
    return [
        (sorted(ids), mapping[sorted(ids)[0]])
        for ids in buckets.values()
        if len(ids) > 1
    ]


def normalize_topics(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """规范化 ingest 产出的 topics 结构；返回 (规范化结果, report)。"""
    result: dict[str, Any] = {}
    report: dict[str, Any] = {"topics": {}, "issues": [], "counts": {}}

    for topic, payload in (raw or {}).items():
        body = payload if isinstance(payload, dict) else {}
        entry: dict[str, Any] = {}
        for key in ("benchmark_refs", "human_refs"):
            refs, issues = normalize_ref_map(body.get(key) or {})
            entry[key] = refs
            if not refs:
                report["issues"].append({"type": "empty_ref_set", "topic": topic, "field": key})
            for issue in issues:
                report["issues"].append({"topic": topic, "field": key, **issue})
        entry["human_reference_available"] = bool(entry.get("human_refs"))
        result[topic] = entry
        report["topics"][topic] = {
            "benchmark_refs": len(entry["benchmark_refs"]),
            "human_refs": len(entry["human_refs"]),
        }

    report["counts"] = {
        "topics": len(result),
        "benchmark_refs": sum(len(v["benchmark_refs"]) for v in result.values()),
        "human_refs": sum(len(v["human_refs"]) for v in result.values()),
        "issues": len(report["issues"]),
    }
    return result, report


def _looks_like_topics(payload: Any) -> bool:
    """判断输入是 topics 结构还是纯 ref 映射。"""
    if not isinstance(payload, dict) or not payload:
        return False
    first = next(iter(payload.values()))
    return isinstance(first, dict) and (
        "benchmark_refs" in first or "human_refs" in first
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="规范化 arXiv ID 与参考文献。")
    parser.add_argument("--input", required=True, help="输入 JSON（topics 结构或 ref 映射）")
    parser.add_argument("--output", required=True, help="规范化结果输出路径")
    parser.add_argument("--report", default="", help="问题报告输出路径")
    args = parser.parse_args(argv)

    source = Path(args.input)
    if not source.is_file():
        print(f"找不到输入文件：{source}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"JSON 解析失败：{exc}", file=sys.stderr)
        return 1

    if _looks_like_topics(payload):
        result, report = normalize_topics(payload)
    else:
        refs, issues = normalize_ref_map(payload)
        result, report = refs, {"issues": issues, "counts": {"refs": len(refs), "issues": len(issues)}}

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {out_path}（{report['counts']}）")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入报告 {report_path}（{len(report['issues'])} 项问题）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
