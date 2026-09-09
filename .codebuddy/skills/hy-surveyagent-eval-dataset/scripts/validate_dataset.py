#!/usr/bin/env python3
"""HySurveyBench 数据集结构与引用校验（build Step 9 的可复用实现）。

用法：
    python validate_dataset.py --dataset datasets/hysurveybench_v1.0 \
                               [--json-out build/09_final/validation.json]

检查项：
    Structural —— manifest / topics.json / 每个 topic 文件是否存在且一致；
    Paper      —— gold_papers 与 background_papers 必须存在于 metadata store；
    KIU        —— 每个 unit 至少一个 source_paper，且 importance > 0；
    Quiz       —— topic-specific 题目字段非空、type/difficulty 取值合法；
    Path       —— quiz_file / rubric_file / fulltext / human_survey 路径存在。

输出 ERROR（必须修，退出码 1）与 WARN（人工确认）两级。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

QUIZ_TYPES = {
    "concept",
    "taxonomy",
    "historical_evolution",
    "algorithm_principle",
    "method_comparison",
    "performance_benchmark",
    "application",
    "limitations",
    "research_gap",
    "future_direction",
}
DIFFICULTIES = {"easy", "medium", "hard"}


class Report:
    """ERROR / WARN 收集器。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warns: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warns.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "errors": self.errors,
            "warnings": self.warns,
            "ok": not self.errors,
        }


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_json_or_error(path: Path, label: str, report: Report) -> Any | None:
    payload = _load_json(path)
    if payload is None:
        report.error(f"{label} 缺失或不是合法 JSON：{path}")
    return payload


def _resolve(base: Path, value: str) -> Path:
    """解析 topic 文件中的相对路径（形如 ../quizzes/x.json）。"""
    candidate = (base / value) if not Path(value).is_absolute() else Path(value)
    return candidate.resolve()


def validate(dataset_dir: Path, expected_topics: int = 0) -> Report:
    """执行全部确定性校验。"""
    report = Report()

    manifest = _load_json_or_error(dataset_dir / "manifest.json", "manifest.json", report)
    topics_index = _load_json_or_error(dataset_dir / "topics.json", "topics.json", report)

    if manifest is None or topics_index is None:
        return report

    manifest_topics = manifest.get("topics") if isinstance(manifest, dict) else None
    index_topics = topics_index.get("topics") if isinstance(topics_index, dict) else topics_index
    if not isinstance(manifest_topics, list) or not isinstance(index_topics, list):
        report.error("manifest.json / topics.json 缺少 topics 列表")
        return report
    if set(manifest_topics) != set(index_topics):
        report.error("manifest.json 与 topics.json 的 topic 列表不一致")

    if expected_topics and len(manifest_topics) != expected_topics:
        report.error(f"topic 数量应为 {expected_topics}，实际 {len(manifest_topics)}")

    metadata_dir = dataset_dir / "papers" / "metadata"
    fulltext_dir = dataset_dir / "papers" / "fulltext"
    if not metadata_dir.is_dir():
        report.error(f"缺少 papers/metadata 目录：{metadata_dir}")

    known_papers = {path.stem for path in metadata_dir.glob("*.json")} if metadata_dir.is_dir() else set()

    for topic_id in manifest_topics:
        topic_path = dataset_dir / "topics" / f"{topic_id}.json"
        topic = _load_json_or_error(topic_path, f"topic {topic_id}", report)
        if not isinstance(topic, dict):
            continue

        if topic.get("id") not in (None, topic_id) and topic.get("id") != topic_id:
            report.warn(f"{topic_id}：字段 id 与文件名不一致")

        # Paper 集合
        gold = topic.get("gold_papers") or []
        background = topic.get("background_papers") or []
        if not gold:
            report.error(f"{topic_id}：gold_papers 为空")
        for paper_id in [*gold, *background]:
            if paper_id not in known_papers:
                report.error(f"{topic_id}：论文缺少 metadata —— {paper_id}")
            elif not (fulltext_dir / f"{paper_id}.json").is_file():
                report.warn(f"{topic_id}：gold/background 论文缺少 fulltext —— {paper_id}")

        pool = topic.get("benchmark_pool") or []
        if not pool:
            report.warn(f"{topic_id}：benchmark_pool 为空")

        # Rubric（KIU）
        rubric_ref = topic.get("rubric_file")
        if not rubric_ref:
            report.error(f"{topic_id}：缺少 rubric_file")
        else:
            rubric_path = _resolve(topic_path.parent, str(rubric_ref))
            rubric = _load_json_or_error(rubric_path, f"{topic_id} rubric", report)
            units = (rubric or {}).get("units") if isinstance(rubric, dict) else None
            if not units:
                report.error(f"{topic_id}：rubric 缺少 units")
            else:
                seen: set[str] = set()
                for unit in units:
                    unit_id = str(unit.get("id", ""))
                    if not unit_id or unit_id in seen:
                        report.error(f"{topic_id}：KIU id 缺失或重复 —— {unit_id!r}")
                    seen.add(unit_id)
                    sources = unit.get("source_papers") or []
                    if not sources:
                        report.error(f"{topic_id}：KIU {unit_id} 缺少 source_papers")
                    for paper_id in sources:
                        if paper_id not in known_papers:
                            report.error(
                                f"{topic_id}：KIU {unit_id} 引用未知论文 —— {paper_id}"
                            )
                    if not isinstance(unit.get("importance"), int) or unit["importance"] <= 0:
                        report.error(f"{topic_id}：KIU {unit_id} 的 importance 必须为正整数")

        # Quiz
        quiz_ref = topic.get("quiz_file")
        if not quiz_ref:
            report.error(f"{topic_id}：缺少 quiz_file")
        else:
            quiz_path = _resolve(topic_path.parent, str(quiz_ref))
            quiz = _load_json_or_error(quiz_path, f"{topic_id} quiz", report)
            questions = (quiz or {}).get("questions") if isinstance(quiz, dict) else None
            if not questions:
                report.error(f"{topic_id}：quiz 缺少 questions")
            else:
                _validate_quiz(topic_id, questions, known_papers, report)

        # Human survey
        human = topic.get("human_reference") or {}
        if human.get("available"):
            target = _resolve(dataset_dir, str(human.get("path", "")))
            if not target.is_file():
                report.error(f"{topic_id}：human_survey 路径不存在 —— {target}")
        else:
            report.warn(f"{topic_id}：无 human survey（reference-free 模式）")

    return report


def _validate_quiz(
    topic_id: str, questions: list[Any], known_papers: set[str], report: Report
) -> None:
    """校验 quiz 字段完整性与难度分布。"""
    difficulty_counts = {"easy": 0, "medium": 0, "hard": 0}
    seen: set[str] = set()

    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            report.error(f"{topic_id}：quiz[{index}] 必须是对象")
            continue
        qid = str(question.get("id", "") or f"#{index}")
        if qid in seen:
            report.error(f"{topic_id}：quiz id 重复 —— {qid}")
        seen.add(qid)

        if not str(question.get("question", "")).strip():
            report.error(f"{topic_id}：quiz {qid} 缺少 question")
        if not str(question.get("reference_answer", "")).strip():
            report.error(f"{topic_id}：quiz {qid} 缺少 reference_answer")

        qtype = question.get("type")
        if qtype not in QUIZ_TYPES:
            report.error(f"{topic_id}：quiz {qid} 的 type 非法 —— {qtype!r}")

        difficulty = question.get("difficulty")
        if difficulty not in DIFFICULTIES:
            report.error(f"{topic_id}：quiz {qid} 的 difficulty 非法 —— {difficulty!r}")
        else:
            difficulty_counts[difficulty] += 1

        sources = question.get("source_papers") or []
        if not sources:
            report.error(f"{topic_id}：quiz {qid} 缺少 source_papers")
        for paper_id in sources:
            if paper_id not in known_papers:
                report.error(f"{topic_id}：quiz {qid} 引用未知论文 —— {paper_id}")
        if not (question.get("evidence") or []):
            report.warn(f"{topic_id}：quiz {qid} 无 evidence（无法做 evidence-gating）")

    total = sum(difficulty_counts.values())
    if total:
        easy_ratio = difficulty_counts["easy"] / total
        hard_ratio = difficulty_counts["hard"] / total
        if not 0.15 <= easy_ratio <= 0.35:
            report.warn(f"{topic_id}：Easy 占比 {easy_ratio:.0%} 偏离建议 25%")
        if not 0.15 <= hard_ratio <= 0.35:
            report.warn(f"{topic_id}：Hard 占比 {hard_ratio:.0%} 偏离建议 25%")
        if not 15 <= total <= 25:
            report.warn(f"{topic_id}：题目数 {total} 不在建议区间 15–25")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 HySurveyBench 数据集。")
    parser.add_argument("--dataset", required=True, help="数据集目录")
    parser.add_argument("--expected-topics", type=int, default=0, help="期望的 topic 数量，0 不校验")
    parser.add_argument("--json-out", default="", help="校验报告输出路径")
    args = parser.parse_args(argv)

    dataset_dir = Path(args.dataset).resolve()
    if not dataset_dir.is_dir():
        print(f"找不到数据集目录：{dataset_dir}", file=sys.stderr)
        return 2

    report = validate(dataset_dir, args.expected_topics)

    for warn in report.warns:
        print(f"WARN  {warn}")
    for error in report.errors:
        print(f"ERROR {error}")
    print(f"\n{len(report.errors)} ERROR / {len(report.warns)} WARN")

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out_path}")

    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
