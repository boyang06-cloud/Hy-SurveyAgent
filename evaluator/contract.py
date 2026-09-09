"""评测数据模型：维度结果与评测报告。"""

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
    low_confidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "score": self.score,
            "details": self.details,
            "error": self.error,
            "low_confidence": self.low_confidence,
        }


@dataclass
class EvalReport:
    """一次评测（一个 method × 一个或多个 topic）的完整结果。"""

    run_id: str
    method: str
    dataset_version: str
    mode: str = "human_reference"
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    gate: dict[str, Any] = field(default_factory=dict)
    gate_reasons: list[str] = field(default_factory=list)
    raw_score: float | None = None
    final_score: float | None = None
    missing_dimensions: list[str] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    #: 每个 topic 的完整可审计结果（Judge 原始输出、quiz 明细等）
    per_topic: list[dict[str, Any]] = field(default_factory=list)

    def scores(self) -> dict[str, float | None]:
        return {key: value.score for key, value in self.dimensions.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "method": self.method,
            "dataset_version": self.dataset_version,
            "mode": self.mode,
            "dimensions": {key: value.to_dict() for key, value in self.dimensions.items()},
            "gate": self.gate,
            "gate_reasons": self.gate_reasons,
            "raw_score": self.raw_score,
            "final_score": self.final_score,
            "missing_dimensions": self.missing_dimensions,
            "cost": self.cost,
            "notes": self.notes,
            "topics": self.topics,
        }
