#!/usr/bin/env python3
"""生成 evaluator/ 骨架：模块占位、七类 Judge Prompt、配置模板。

用法：
    python init_evaluator.py [--root <repo-root>] [--force]

约定：
    - 已存在的文件默认跳过（不覆盖），`--force` 时覆盖；
    - Prompt 文件按 `assets/templates/judge_prompt_template.md` 的六段结构生成占位；
    - 只创建文件，不安装依赖、不修改 Application 代码。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

MODULES: dict[str, str] = {
    "evaluator/__init__.py": '"""Hy-SurveyAgent Evaluation Harness。"""\n',
    "evaluator/__main__.py": '''"""CLI 入口：uv run python -m evaluator。"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行 Hy-SurveyAgent 评测。")
    parser.add_argument("--dataset", required=True, help="评测数据集目录（冻结版本）")
    parser.add_argument("--run", required=True, help="Application 运行目录 runs/<task_id>")
    parser.add_argument("--out", default="", help="结果输出目录")
    parser.add_argument("--dimensions", default="", help="逗号分隔，默认全部")
    parser.add_argument("--judge-dual", action="store_true", help="核心维度启用双 Judge")
    parser.add_argument("--limit-topics", type=int, default=0, help="只评测前 N 个 topic")
    args = parser.parse_args(argv)

    # TODO: 加载 dataset + result.json，按维度分发，聚合后写报告
    print(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    "evaluator/config.py": '''"""评测配置：权重、Judge 温度、阈值、路径（不含密钥）。"""

from __future__ import annotations

from dataclasses import dataclass, field

#: 维度权重（eval_protocol.md 第 2 节）
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

#: Critical Failure Gate 阈值
GATE = {
    "fabricated_citation_rate_low": 0.10,
    "fabricated_citation_rate_high": 0.30,
    "citation_recall_min": 0.40,
    "severe_contradictions_min": 3,
}


@dataclass
class JudgeConfig:
    """Judge 调用参数；temperature 必须为 0。"""

    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 2048
    dual_judge_dimensions: tuple[str, ...] = ("D1", "D2", "D4", "D6")
    cache_dir: str = "results/eval/.judge_cache"


@dataclass
class EvalConfig:
    """一次评测运行的配置。"""

    dataset_dir: str = ""
    run_dir: str = ""
    out_dir: str = "results/eval"
    weights: dict[str, float] = field(default_factory=lambda: dict(WEIGHTS))
    judge: JudgeConfig = field(default_factory=JudgeConfig)
''',
    "evaluator/contract.py": '''"""评测数据模型：维度结果与评测报告。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DimensionResult:
    """单个维度的结果；score 归一化到 [0,100]，失败时为 None。"""

    dimension: str
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "score": self.score,
            "details": self.details,
            "error": self.error,
        }


@dataclass
class EvalReport:
    """一次评测的完整结果。"""

    run_id: str
    method: str
    dataset_version: str
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    gate: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)

    def scores(self) -> dict[str, float | None]:
        return {key: value.score for key, value in self.dimensions.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "method": self.method,
            "dataset_version": self.dataset_version,
            "dimensions": {key: value.to_dict() for key, value in self.dimensions.items()},
            "gate": self.gate,
            "cost": self.cost,
        }
''',
    "evaluator/aggregate.py": '''"""加权聚合 + Critical Failure Gate。

实现须与 skill 的 scripts/aggregate_scores.py 保持一致（同一套权重与 gate 规则）。
"""

from __future__ import annotations

from evaluator.config import GATE, WEIGHTS


def weighted_score(scores: dict[str, float | None]) -> tuple[float, list[str]]:
    """按权重聚合，缺失维度按剩余权重归一化。"""
    present = {key: value for key, value in scores.items() if value is not None}
    if not present:
        raise ValueError("没有可用维度分数。")
    total_weight = sum(WEIGHTS[key] for key in present if key in WEIGHTS)
    if total_weight <= 0:
        raise ValueError("权重配置异常。")
    total = sum(float(present[key]) * WEIGHTS[key] for key in present if key in WEIGHTS)
    missing = [key for key in WEIGHTS if key not in present]
    return total / total_weight, missing


def apply_gate(score: float, gate: dict[str, float | int]) -> tuple[float, list[str]]:
    """应用 Critical Failure Gate，取最严格上限。"""
    cap = 100.0
    reasons: list[str] = []
    fabricated = gate.get("fabricated_citation_rate")
    if isinstance(fabricated, (int, float)):
        if fabricated > GATE["fabricated_citation_rate_high"]:
            cap, reasons = min(cap, 40.0), reasons + [f"fabricated {fabricated:.1%} → ≤40"]
        elif fabricated > GATE["fabricated_citation_rate_low"]:
            cap, reasons = min(cap, 60.0), reasons + [f"fabricated {fabricated:.1%} → ≤60"]
    recall = gate.get("citation_recall")
    if isinstance(recall, (int, float)) and recall < GATE["citation_recall_min"]:
        cap, reasons = min(cap, 50.0), reasons + [f"recall {recall:.1%} → ≤50"]
    severe = gate.get("severe_contradictions")
    if isinstance(severe, int) and severe >= GATE["severe_contradictions_min"]:
        cap, reasons = min(cap, 60.0), reasons + [f"severe {severe} → ≤60"]
    return min(score, cap), reasons
''',
    "evaluator/runner.py": '''"""单条样本跑完 D1–D8；单维度失败不影响其它维度。"""

from __future__ import annotations

from evaluator.contract import DimensionResult, EvalReport


class EvalRunner:
    """按维度分发评测。TODO: 注入 dataset、LLMProvider、各维度实现。"""

    def run(self) -> EvalReport:
        report = EvalReport(run_id="", method="", dataset_version="")
        for dimension in ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"):
            report.dimensions[dimension] = DimensionResult(dimension=dimension, error="未实现")
        return report
''',
    "evaluator/report.py": '''"""生成 Markdown / JSON 报告表。"""

from __future__ import annotations

from evaluator.contract import EvalReport

DIMENSION_TABLE_HEADER = "| Method | Overall | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 |\\n| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"


def render_main_table(reports: list[EvalReport]) -> str:
    """渲染协议第 26 节的主结果表。"""
    lines = [DIMENSION_TABLE_HEADER]
    for report in reports:
        scores = report.scores()
        cells = [scores.get(f"D{index}") for index in range(1, 9)]
        overall = report.gate.get("final_score", "")
        rendered = ["" if cell is None else f"{cell:.1f}" for cell in cells]
        lines.append(f"| {report.method} | {overall} | " + " | ".join(rendered) + " |")
    return "\\n".join(lines)
''',
    "evaluator/judges/base.py": '''"""Judge 抽象：prompt 加载 → 调用 → 解析 → schema 校验 → 缓存 → 统计。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.model.provider import LLMProvider


class BaseJudge(ABC):
    """所有 Judge 的基类；temperature 由 config 注入，禁止在子类写死。"""

    #: Judge 输出的合法 label 枚举
    LABELS: tuple[str, ...] = ()

    def __init__(self, llm: LLMProvider, model: str, temperature: float = 0.0) -> None:
        self.llm = llm
        self.model = model
        self.temperature = temperature

    @property
    @abstractmethod
    def prompt_name(self) -> str:
        """Prompt 文件名（不含扩展名）。"""

    @abstractmethod
    def build_messages(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """构造 messages；输入必须包含证据字段。"""

    @abstractmethod
    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """校验并归一化 Judge 输出；非法值按 UNSUPPORTED 降级。"""
''',
    "evaluator/evidence/retriever.py": '''"""Claim → Gold Paper 语料 → top-k 证据段落。

禁止用模型参数知识替代检索；检索为空时上层必须判 UNSUPPORTED。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvidencePassage:
    paper_id: str
    section_id: str
    text: str
    score: float = 0.0


class EvidenceRetriever:
    """TODO: 基于 dataset 的 papers/fulltext 建立可检索语料（BM25 或向量）。"""

    def retrieve(self, claim: str, paper_ids: list[str], top_k: int = 5) -> list[EvidencePassage]:
        raise NotImplementedError
''',
    "evaluator/evidence/claims.py": '''"""atomic claim 抽取与 claim↔citation 对齐。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AtomicClaim:
    claim_id: str
    text: str
    citation_ids: list[str] = field(default_factory=list)
    section: str = ""


class ClaimExtractor:
    """TODO: 只抽取可验证的 factual / scientific claims。"""

    def extract(self, survey_markdown: str) -> list[AtomicClaim]:
        raise NotImplementedError
''',
    "evaluator/quizzes/answerer.py": '''"""Quiz 作答：Section Retrieval → Survey-only 作答 → 引用段落。"""

from __future__ import annotations

from dataclasses import dataclass, field

NO_SUFFICIENT_INFORMATION = "NO_SUFFICIENT_INFORMATION"


@dataclass
class QuizAnswer:
    question_id: str
    answer: str
    used_sections: list[str] = field(default_factory=list)

    @property
    def unanswered(self) -> bool:
        return self.answer.strip() == NO_SUFFICIENT_INFORMATION


class QuizAnswerer:
    """TODO: 只允许依据 Survey 内容作答，禁止引入外部知识。"""

    def answer(self, question: str, survey_markdown: str) -> QuizAnswer:
        raise NotImplementedError
''',
    "evaluator/rules/format.py": '''"""纯规则检查：citation 格式、reference 完整性、heading、Markdown、占位符。"""

from __future__ import annotations

import re

PLACEHOLDER_PATTERN = re.compile(r"(?i)\\b(TODO|TBD|FIXME|XXX)\\b")


def check_format(survey_markdown: str) -> list[str]:
    """返回规则违规列表；空列表表示全部通过。"""
    issues: list[str] = []
    if not survey_markdown.strip():
        issues.append("survey 为空")
    if PLACEHOLDER_PATTERN.search(survey_markdown):
        issues.append("存在未替换的占位符")
    if survey_markdown.count("```") % 2:
        issues.append("Markdown 代码块围栏不配对")
    return issues
''',
}

PROMPT_TEMPLATE = """<!-- version: 0.1.0 -->
# {title} Judge

## Role

<!-- TODO: 一句话说明该 Judge 只解决什么问题 -->

## Input Schema

<!-- TODO: JSON 输入字段；必须包含证据字段 -->

## Output Schema

```json
{{
  "claim_id": "C001",
  "label": "SUPPORTED",
  "score": 2,
  "reason": "..."
}}
```

## Rules

- 只能依据提供的 evidence 判断，禁止使用自身知识；
- 证据不足时返回 UNSUPPORTED（score = 0）；
- 字段缺失时返回 "" / [] / 0，禁止编造；
- score 必须是整数且落在 rubric 允许范围内。

## Few-shot Examples

<!-- TODO: 至少 2 个示例（含一个 UNSUPPORTED 反例）；示例 ID 不要使用 P001/C001 等真实 ID 空间 -->

## Failure Constraints

<!-- TODO: 输出非 JSON、label 非法、score 越界的处理 -->
"""

JUDGE_TITLES = {
    "factual": "Factual Accuracy (D1)",
    "citation": "Citation Correctness (D2)",
    "coverage": "Information Coverage (D3)",
    "synthesis": "Cross-paper Synthesis (D4)",
    "outline": "Outline & Structure (D5)",
    "quiz_answer": "Quiz Answer (D6)",
    "terminology": "Terminology & Rigor (D7)",
}


def write(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return f"skip  {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"write {path}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 evaluator/ 骨架。")
    parser.add_argument("--root", default=".", help="仓库根目录")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    for rel, content in MODULES.items():
        print(write(root / rel, content, args.force))

    for name, title in JUDGE_TITLES.items():
        target = root / "evaluator" / "prompts" / f"{name}.md"
        print(write(target, PROMPT_TEMPLATE.format(title=title), args.force))

    config_src = SKILL_DIR / "assets" / "templates" / "eval_config.example.yaml"
    if config_src.is_file():
        target = root / "configs" / "eval.example.yaml"
        print(write(target, config_src.read_text(encoding="utf-8"), args.force))

    print("\n下一步：按 skill 的开发顺序逐个填充维度实现与 Judge Prompt。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
