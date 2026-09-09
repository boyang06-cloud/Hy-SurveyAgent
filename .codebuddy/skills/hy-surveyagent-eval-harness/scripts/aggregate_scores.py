#!/usr/bin/env python3
"""从各维度分数聚合成总分，并应用 Critical Failure Gate。

用法：
    python aggregate_scores.py --scores results/eval/<run_id>/dimensions.json \
                               [--out results/eval/<run_id>/final.json] \
                               [--markdown]

输入（dimensions.json）最小结构：
    {
      "run_id": "...", "method": "...",
      "dimensions": {"D1": 78.4, "D2": 71.0, ...},   # 值可为数字，或 {"score": 78.4}
      "gate": {"fabricated_citation_rate": 0.0, "citation_recall": 0.77,
               "severe_contradictions": 1}
    }

维度缺失时按剩余权重重新归一化；Gate 命中时取最严格上限。
纯标准库实现，可直接被 evaluator/aggregate.py 复用或作为其参考实现。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: 协议权重（eval_protocol.md 第 2 节）
WEIGHTS: dict[str, float] = {
    "D1": 0.18,
    "D2": 0.18,
    "D3": 0.13,
    "D4": 0.15,
    "D5": 0.08,
    "D6": 0.15,
    "D7": 0.07,
    "D8": 0.06,
}

#: Critical Failure Gate：条件名 → (阈值判定函数, 上限)
GATE_FABRICATED_HIGH = 0.30
GATE_FABRICATED_LOW = 0.10
GATE_RECALL_MIN = 0.40
GATE_SEVERE_MIN = 3


class ScoreError(ValueError):
    """分数输入不合法。"""


def _coerce_score(value: Any) -> float | None:
    """把维度值转为 0–100 的浮点；返回 None 表示维度缺失。"""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("score")
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        raise ScoreError(f"维度分数必须是数字，收到：{value!r}")
    score = float(value)
    if score < 0 or score > 100:
        raise ScoreError(f"维度分数必须落在 [0,100]，收到：{score}")
    return score


def weighted_score(dimensions: dict[str, Any]) -> tuple[float, list[str]]:
    """按权重聚合；缺失维度按剩余权重归一化，返回 (分数, 缺失维度列表)。"""
    present: dict[str, float] = {}
    missing: list[str] = []
    for key, weight in WEIGHTS.items():
        score = _coerce_score(dimensions.get(key))
        if score is None:
            missing.append(key)
        else:
            present[key] = score

    unknown = sorted(set(dimensions) - set(WEIGHTS))
    if unknown:
        raise ScoreError(f"存在未知维度：{unknown}")

    if not present:
        raise ScoreError("没有任何可用维度分数，无法聚合。")

    total_weight = sum(WEIGHTS[key] for key in present)
    return sum(present[key] * WEIGHTS[key] for key in present) / total_weight, missing


def apply_gate(score: float, gate: dict[str, Any]) -> tuple[float, list[str]]:
    """应用 Critical Failure Gate，返回 (最终分数, 命中的 gate 描述)。"""
    reasons: list[str] = []
    cap = 100.0

    fabricated = gate.get("fabricated_citation_rate")
    if isinstance(fabricated, (int, float)) and not isinstance(fabricated, bool):
        if fabricated > GATE_FABRICATED_HIGH:
            cap = min(cap, 40.0)
            reasons.append(f"Fabricated Citation Rate {fabricated:.1%} > 30% → ≤40")
        elif fabricated > GATE_FABRICATED_LOW:
            cap = min(cap, 60.0)
            reasons.append(f"Fabricated Citation Rate {fabricated:.1%} > 10% → ≤60")

    recall = gate.get("citation_recall")
    if isinstance(recall, (int, float)) and not isinstance(recall, bool):
        if recall < GATE_RECALL_MIN:
            cap = min(cap, 50.0)
            reasons.append(f"Citation Recall {recall:.1%} < 40% → ≤50")

    severe = gate.get("severe_contradictions")
    if isinstance(severe, int) and not isinstance(severe, bool):
        if severe >= GATE_SEVERE_MIN:
            cap = min(cap, 60.0)
            reasons.append(f"Severe Contradictions {severe} ≥ 3 → ≤60")

    return min(score, cap), reasons


def aggregate(payload: dict[str, Any]) -> dict[str, Any]:
    """完整聚合：加权 → Gate，返回结果字典。"""
    dimensions = payload.get("dimensions") or {}
    if not isinstance(dimensions, dict):
        raise ScoreError("dimensions 必须是对象。")
    gate = payload.get("gate") or {}
    if not isinstance(gate, dict):
        raise ScoreError("gate 必须是对象。")

    raw, missing = weighted_score(dimensions)
    final, reasons = apply_gate(raw, gate)
    return {
        "run_id": payload.get("run_id", ""),
        "method": payload.get("method", ""),
        "dataset_version": payload.get("dataset_version", ""),
        "raw_score": round(raw, 2),
        "final_score": round(final, 2),
        "cap_applied": bool(reasons),
        "gate_reasons": reasons,
        "missing_dimensions": missing,
        "dimensions": {
            key: _coerce_score(dimensions.get(key)) for key in WEIGHTS if key in dimensions
        },
        "weights": dict(WEIGHTS),
    }


def render_markdown(result: dict[str, Any]) -> str:
    """渲染单条运行的 Markdown 摘要。"""
    lines = [
        f"# Eval Report — {result['method'] or result['run_id']}",
        "",
        f"- Final Score：**{result['final_score']}**（raw {result['raw_score']}）",
        f"- Dataset：{result['dataset_version'] or '-'}",
    ]
    if result["missing_dimensions"]:
        lines.append(f"- 缺失维度（已按剩余权重归一化）：{', '.join(result['missing_dimensions'])}")
    if result["gate_reasons"]:
        lines.append("- Critical Failure Gate：")
        lines.extend(f"  - {reason}" for reason in result["gate_reasons"])
    lines.extend(
        [
            "",
            "| Dimension | Score | Weight |",
            "| --- | ---: | ---: |",
        ]
    )
    for key, score in result["dimensions"].items():
        if score is None:
            continue
        lines.append(f"| {key} | {score:.2f} | {result['weights'][key]:.2f} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="聚合 eval 维度分数并应用 Critical Failure Gate。")
    parser.add_argument("--scores", required=True, help="dimensions.json 路径")
    parser.add_argument("--out", help="聚合结果输出路径（JSON）")
    parser.add_argument("--markdown", action="store_true", help="额外输出 Markdown 摘要到 stdout")
    args = parser.parse_args(argv)

    path = Path(args.scores)
    if not path.is_file():
        print(f"找不到分数文件：{path}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = aggregate(payload)
    except (json.JSONDecodeError, ScoreError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out_path}")
    if args.markdown or not args.out:
        print(render_markdown(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
