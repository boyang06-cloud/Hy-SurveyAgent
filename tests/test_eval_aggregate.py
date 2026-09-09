"""聚合与 Critical Failure Gate 的单元测试（公式与 skill 参考实现一致）。"""

from __future__ import annotations

import pytest

from evaluator.aggregate import ScoreError, aggregate, apply_gate, weighted_score
from evaluator.config import WEIGHTS, load_eval_config


def test_weighted_score_full() -> None:
    scores = {key: 80.0 for key in WEIGHTS}
    score, missing = weighted_score(scores)
    assert score == pytest.approx(80.0)
    assert missing == []


def test_weighted_score_renormalizes_missing_dimensions() -> None:
    scores = {"D1": 100.0, "D2": 50.0}  # 其余维度缺失
    score, missing = weighted_score(scores)
    assert missing == [key for key in WEIGHTS if key not in scores]
    assert score == pytest.approx((100 * 0.18 + 50 * 0.18) / (0.18 + 0.18))


def test_weighted_score_rejects_unknown_dimension() -> None:
    with pytest.raises(ScoreError):
        weighted_score({"D9": 10.0})


def test_weighted_score_rejects_out_of_range() -> None:
    with pytest.raises(ScoreError):
        weighted_score({"D1": 120.0})


def test_weighted_score_rejects_empty() -> None:
    with pytest.raises(ScoreError):
        weighted_score({})


def test_gate_fabricated_rate() -> None:
    assert apply_gate(90.0, {"fabricated_citation_rate": 0.05})[0] == 90.0
    assert apply_gate(90.0, {"fabricated_citation_rate": 0.15})[0] == 60.0
    assert apply_gate(90.0, {"fabricated_citation_rate": 0.5})[0] == 40.0


def test_gate_recall_and_severe() -> None:
    assert apply_gate(90.0, {"citation_recall": 0.2})[0] == 50.0
    assert apply_gate(90.0, {"severe_contradictions": 3})[0] == 60.0
    assert apply_gate(90.0, {"severe_contradictions": 2})[0] == 90.0


def test_gate_takes_strictest_cap() -> None:
    score, reasons = apply_gate(
        90.0,
        {"fabricated_citation_rate": 0.5, "citation_recall": 0.1, "severe_contradictions": 5},
    )
    assert score == 40.0
    assert len(reasons) == 3


def test_gate_ignores_missing_metrics() -> None:
    assert apply_gate(75.0, {})[0] == 75.0
    assert apply_gate(75.0, {"fabricated_citation_rate": None})[0] == 75.0


def test_aggregate_end_to_end() -> None:
    result = aggregate(
        {
            "run_id": "r1",
            "method": "M",
            "dataset_version": "v0.1",
            "dimensions": {"D1": {"score": 50.0}, "D2": 50.0},
            "gate": {
                "fabricated_citation_rate": 0.2,
                "citation_recall": 0.8,
                "severe_contradictions": 0,
            },
        }
    )
    assert result["raw_score"] == pytest.approx(50.0)
    assert result["final_score"] == 50.0  # 伪造率 > 10% → ≤60
    assert result["missing_dimensions"] == [key for key in WEIGHTS if key not in ("D1", "D2")]
    assert result["cap_applied"] is True


def test_load_eval_config_yaml(tmp_path) -> None:
    config_file = tmp_path / "eval.yaml"
    config_file.write_text(
        """
dataset_dir: datasets/x
method: MyMethod
dimensions: "D1,D2"
judge:
  model: test-model
  max_tokens: 128
""",
        encoding="utf-8",
    )
    config = load_eval_config(config_file)
    assert config.dataset_dir == "datasets/x"
    assert config.method == "MyMethod"
    assert config.dimensions == ("D1", "D2")
    assert config.judge.model == "test-model"
    assert config.judge.max_tokens == 128
    assert config.judge.temperature == 0.0
    assert config.weights == WEIGHTS


def test_load_eval_config_rejects_unknown_dimension(tmp_path) -> None:
    config_file = tmp_path / "eval.yaml"
    config_file.write_text('dimensions: "D1,D9"', encoding="utf-8")
    with pytest.raises(ValueError):
        load_eval_config(config_file)


def test_load_eval_config_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_eval_config(tmp_path / "nope.yaml")
