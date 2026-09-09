"""评测配置：维度权重、Judge 参数、Gate 阈值与路径（不含任何密钥）。

权威来源：``eval_harness/eval_protocol.md`` 第 2 / 14 节；
权重与阈值只能整体修改并在评测报告中说明理由，禁止散落在各维度模块。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]

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

DIMENSIONS: tuple[str, ...] = tuple(WEIGHTS)

#: Critical Failure Gate 阈值（eval_protocol.md 第 14 节）
GATE: dict[str, float] = {
    "fabricated_citation_rate_low": 0.10,
    "fabricated_citation_rate_high": 0.30,
    "citation_recall_min": 0.40,
    "severe_contradictions_min": 3,
}


@dataclass
class JudgeConfig:
    """Judge 调用参数；temperature 必须为 0 以保证可复现。"""

    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 2048
    dual_judge: bool = False
    dual_judge_dimensions: tuple[str, ...] = ("D1", "D2", "D4", "D6")
    agree_threshold: float = 1.0
    cache_dir: str = "results/eval/.judge_cache"
    cache_enabled: bool = True


@dataclass
class EvidenceConfig:
    """证据检索参数。"""

    top_k: int = 5
    max_passage_chars: int = 1200


@dataclass
class QuizConfig:
    """D6 Quiz 参数（eval_protocol.md 第 10 节）。"""

    general_weight: float = 0.4
    topic_weight: float = 0.6
    evidence_gating: bool = True
    section_top_k: int = 4


@dataclass
class EvalConfig:
    """一次评测运行的配置快照（不含密钥）。"""

    dataset_dir: str = ""
    run_dir: str = ""
    out_dir: str = "results/eval"
    method: str = "Hy-SurveyAgent"
    dimensions: tuple[str, ...] = DIMENSIONS
    weights: dict[str, float] = field(default_factory=lambda: dict(WEIGHTS))
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)
    quiz: QuizConfig = field(default_factory=QuizConfig)
    root: Path = PROJECT_ROOT

    def resolve(self, relative: str | Path) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else self.root / path

    def to_dict(self) -> dict[str, Any]:
        """可安全落盘的配置快照。"""
        return {
            "dataset_dir": self.dataset_dir,
            "run_dir": self.run_dir,
            "out_dir": self.out_dir,
            "method": self.method,
            "dimensions": list(self.dimensions),
            "weights": dict(self.weights),
            "judge": {
                f.name: (
                    list(getattr(self.judge, f.name))
                    if f.name == "dual_judge_dimensions"
                    else getattr(self.judge, f.name)
                )
                for f in fields(JudgeConfig)
            },
            "evidence": {f.name: getattr(self.evidence, f.name) for f in fields(EvidenceConfig)},
            "quiz": {f.name: getattr(self.quiz, f.name) for f in fields(QuizConfig)},
        }


def _section(cls: type, raw: dict[str, Any], key: str, source: Path | None) -> Any:
    data = raw.get(key) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置项 {key} 应为映射（来源：{source}）。")
    allowed = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        warnings.warn(f"忽略未知配置项：{key}.{', '.join(unknown)}（来源：{source}）", stacklevel=2)
    return cls(**{k: v for k, v in data.items() if k in allowed})


def _coerce_dimensions(value: Any) -> tuple[str, ...]:
    if not value:
        return DIMENSIONS
    items = [str(item).strip().upper() for item in str(value).split(",") if str(item).strip()]
    unknown = sorted(set(items) - set(DIMENSIONS))
    if unknown:
        raise ValueError(f"未知维度：{unknown}，合法取值：{list(DIMENSIONS)}")
    if not items:
        return DIMENSIONS
    return tuple(items)


def load_eval_config(
    path: str | Path | None = None,
    root: Path | None = None,
) -> EvalConfig:
    """加载评测配置；``path`` 为空时使用 dataclass 默认值。

    文件不存在但显式指定时抛错；yaml 中 ``dimensions`` 支持列表或逗号分隔字符串。
    """
    base = (root or PROJECT_ROOT).resolve()
    if path is None:
        raw: dict[str, Any] = {}
    else:
        config_path = Path(path)
        if not config_path.is_absolute():
            config_path = base / config_path
        if not config_path.is_file():
            raise FileNotFoundError(f"评测配置不存在：{config_path}")
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError(f"评测配置应为映射：{config_path}")
        raw = loaded or {}

    weights = dict(raw.get("weights") or {}) or dict(WEIGHTS)
    unknown_weights = sorted(set(weights) - set(WEIGHTS))
    if unknown_weights:
        raise ValueError(f"未知维度权重：{unknown_weights}")
    dimensions = _coerce_dimensions(raw.get("dimensions"))

    config = EvalConfig(
        dataset_dir=str(raw.get("dataset_dir") or ""),
        run_dir=str(raw.get("run_dir") or ""),
        out_dir=str(raw.get("out_dir") or "results/eval"),
        method=str(raw.get("method") or "Hy-SurveyAgent"),
        dimensions=dimensions,
        weights={key: float(value) for key, value in weights.items()},
        judge=_section(JudgeConfig, raw, "judge", None),
        evidence=_section(EvidenceConfig, raw, "evidence", None),
        quiz=_section(QuizConfig, raw, "quiz", None),
        root=base,
    )
    return config
