"""Markdown / JSON 报告渲染（协议第 26 节的结果表）。"""

from __future__ import annotations

from evaluator.contract import EvalReport

_DIMENSION_LABELS = {
    "D1": "Fact",
    "D2": "Citation",
    "D3": "Coverage",
    "D4": "Synthesis",
    "D5": "Outline",
    "D6": "Quiz",
    "D7": "Rigor",
    "D8": "Other",
}


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


_MAIN_TABLE_HEADER = (
    "| Method | Overall | D1 Fact | D2 Citation | D3 Coverage "
    "| D4 Synthesis | D5 Outline | D6 Quiz | D7 Rigor | D8 Other |"
)
_MAIN_TABLE_RULES = "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"


def render_report(report: EvalReport, *, provenance: dict | None = None) -> str:
    """渲染单次评测的 Markdown 报告。"""
    lines: list[str] = [
        "# Hy-SurveyAgent Evaluation Report",
        "",
        f"- Run ID：`{report.run_id}`",
        f"- Method：**{report.method}**",
        f"- Topics：{', '.join(report.topics) or '-'}",
        f"- Dataset：`{report.dataset_version}`（mode：`{report.mode}`）",
        f"- Final Score：**{_fmt(report.final_score)}**（raw {_fmt(report.raw_score)}）",
        "",
        "## Main Results",
        "",
        _MAIN_TABLE_HEADER,
        _MAIN_TABLE_RULES,
    ]
    scores = report.scores()
    cells = " | ".join(_fmt(scores.get(f"D{index}")) for index in range(1, 9))
    lines.append(f"| **{report.method}** | {_fmt(report.final_score)} | {cells} |")

    lines.extend(["", "## Quiz Breakdown (D6)", ""])
    d6 = report.dimensions.get("D6")
    layers = (d6.details.get("layers") if d6 else None) or {}
    lines.append("| Easy | Medium | Hard | Topic Quiz | Overall |")
    lines.append("| ---: | ---: | ---: | ---------: | ------: |")
    lines.append(
        "| "
        + " | ".join(
            _fmt(layers.get(key) if isinstance(layers.get(key), (int, float)) else None)
            for key in ("easy", "medium", "hard", "topic")
        )
        + f" | {_fmt(scores.get('D6'))} |"
    )

    lines.extend(["", "## Critical Failure Gate", ""])
    gate = report.gate or {}
    fabricated = gate.get("fabricated_citation_rate")
    recall = gate.get("citation_recall")
    severe = gate.get("severe_contradictions")

    def _pct(value: float | int | str | None) -> str:
        return "-" if value is None else f"{float(value):.1%}"

    lines.append(
        "| Fabricated Rate | Citation Recall | Severe Contradictions | Cap Applied | Final |"
    )
    lines.append("| ---: | ---: | ---: | ----------- | ----: |")
    lines.append(
        f"| {_pct(fabricated)} | {_pct(recall)} | {severe if severe is not None else '-'} "
        f"| {'是' if report.gate_reasons else '否'} | {_fmt(report.final_score)} |"
    )
    for reason in report.gate_reasons:
        lines.append(f"- {reason}")

    lines.extend(["", "## Engineering Metrics", ""])
    lines.append(
        "| Dimension | LLM Calls | Prompt Tokens | Completion Tokens | Latency (ms) | Errors |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    total_calls = 0
    for dimension in sorted(report.cost):
        item = report.cost[dimension]
        total_calls += int(item.get("calls", 0))
        lines.append(
            f"| {dimension} | {item.get('calls', 0)} | {item.get('prompt_tokens', 0)} "
            f"| {item.get('completion_tokens', 0)} "
            f"| {item.get('latency_ms', 0)} | {item.get('errors', 0)} |"
        )
    lines.append(f"| **Total** | **{total_calls}** |  |  |  |  |")

    if provenance:
        lines.extend(["", "## Provenance", ""])
        for name, meta in sorted(provenance.items()):
            lines.append(f"- `{name}`：v{meta.get('version')}（sha256 {meta.get('sha256')}）")

    if report.notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in report.notes)

    low_confidence = [key for key, value in report.dimensions.items() if value.low_confidence]
    errored = [key for key, value in report.dimensions.items() if value.error]
    if low_confidence:
        lines.append(f"- 低置信维度（失败率 > 30%）：{', '.join(low_confidence)}")
    if errored:
        lines.append(f"- 出错的维度：{', '.join(errored)}")

    lines.append("")
    return "\n".join(lines)


def render_comparison(reports: list[EvalReport]) -> str:
    """渲染协议第 26 节的多 method 对比表。"""
    lines = [_MAIN_TABLE_HEADER, _MAIN_TABLE_RULES]
    for report in reports:
        scores = report.scores()
        cells = " | ".join(_fmt(scores.get(f"D{index}")) for index in range(1, 9))
        lines.append(f"| {report.method} | {_fmt(report.final_score)} | {cells} |")
    return "\n".join(lines)
