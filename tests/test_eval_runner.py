"""EvalRunner 集成测试：迷你数据集 + ScriptedProvider 跑通 D1–D8。"""

from __future__ import annotations

import json

import pytest

from evaluator.config import EvalConfig
from evaluator.dataset import load_dataset
from evaluator.report import render_report
from evaluator.runner import EvalRunner, EvalRunnerError, TopicInput, load_run_payload
from tests.evalutils import DEFAULT_ROUTES, RoutingProvider, build_dataset, build_run_dir


def _config(tmp_path, **overrides) -> EvalConfig:
    config = EvalConfig(root=tmp_path)
    config.judge.model = "test-model"
    config.judge.cache_enabled = False
    config.dataset_dir = str(build_dataset(tmp_path))
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _runner(tmp_path, routes=None) -> EvalRunner:
    config = _config(tmp_path)
    provider = RoutingProvider(routes if routes is not None else DEFAULT_ROUTES)
    return EvalRunner(load_dataset(config.dataset_dir), config, provider, run_id="e-test")


def _payload(tmp_path, *, fabricated: bool = False) -> dict:
    run_dir = build_run_dir(tmp_path, fabricated=fabricated)
    return load_run_payload(run_dir)


def _topic(dataset):
    return dataset.topic("test_topic")


def test_full_run_all_dimensions(tmp_path) -> None:
    runner = _runner(tmp_path)
    dataset = runner.dataset
    report = runner.run([TopicInput(case=_topic(dataset), payload=_payload(tmp_path))])

    assert report.mode == "human_reference"
    assert report.topics == ["test_topic"]
    scores = report.scores()
    assert scores["D1"] == pytest.approx(100.0)
    assert scores["D2"] == pytest.approx(100.0)
    assert scores["D3"] == pytest.approx(100.0)
    assert scores["D4"] == pytest.approx(100.0)
    assert scores["D5"] == pytest.approx(100.0)
    assert scores["D6"] == pytest.approx(100.0)
    assert scores["D7"] == pytest.approx(100.0)
    assert scores["D8"] == pytest.approx(100.0)
    assert report.raw_score == pytest.approx(100.0)
    assert report.final_score == pytest.approx(100.0)
    assert report.gate_reasons == []

    # gate 指标可追溯
    assert report.gate["fabricated_citation_rate"] == 0.0
    assert report.gate["citation_recall"] == 1.0
    assert report.gate["severe_contradictions"] == 0

    # per_topic 可审计：quiz 明细保留
    per_topic = report.per_topic[0]
    quiz_details = per_topic["dimensions"]["D6"]["details"]
    assert quiz_details["n_questions"] == 2
    assert len(quiz_details["questions"]) == 2
    assert quiz_details["layers"]["easy"] == pytest.approx(100.0)
    assert quiz_details["layers"]["topic"] == pytest.approx(100.0)

    # 成本统计覆盖各维度
    assert set(report.cost) >= {"D1", "D2", "D6"}
    assert report.cost["D1"]["calls"] > 0

    markdown = render_report(report, provenance=runner.prompt_provenance())
    assert "Final Score" in markdown
    assert "Quiz Breakdown" in markdown
    assert "Critical Failure Gate" in markdown
    assert "Provenance" in markdown


def test_gate_caps_final_score_on_fabricated_citation(tmp_path) -> None:
    runner = _runner(tmp_path)
    dataset = runner.dataset
    report = runner.run(
        [TopicInput(case=_topic(dataset), payload=_payload(tmp_path, fabricated=True))]
    )
    # citation 3 → 9999.99999 不在数据集与 papers 中 → fabricated_rate = 1/3 > 30% → ≤40
    assert report.gate["fabricated_citation_rate"] == pytest.approx(1 / 3)
    assert report.final_score <= 40.0
    assert any("Fabricated" in reason for reason in report.gate_reasons)
    assert report.final_score < report.raw_score


def test_dimension_failure_isolated(tmp_path) -> None:
    # 移除 Synthesis 路由 → D4 失败，其余维度不受影响
    routes = [route for route in DEFAULT_ROUTES if route[0] != "Cross-paper Synthesis Judge"]
    runner = _runner(tmp_path, routes=routes)
    dataset = runner.dataset
    report = runner.run([TopicInput(case=_topic(dataset), payload=_payload(tmp_path))])
    assert report.dimensions["D4"].error
    assert report.dimensions["D4"].score is None
    assert report.dimensions["D1"].score == pytest.approx(100.0)
    # D4 缺失 → 按剩余权重归一化
    assert "D4" in report.missing_dimensions
    assert any("归一化" in note for note in report.notes)
    assert report.final_score is not None


def test_partial_dimensions_selection(tmp_path) -> None:
    config = _config(tmp_path)
    config.dimensions = ("D5", "D7")
    provider = RoutingProvider(DEFAULT_ROUTES)
    runner = EvalRunner(load_dataset(config.dataset_dir), config, provider, run_id="e-test")
    dataset = runner.dataset
    report = runner.run([TopicInput(case=_topic(dataset), payload=_payload(tmp_path))])
    assert set(report.dimensions) == {"D5", "D7"}
    assert report.missing_dimensions  # 其余维度按缺失归一化
    assert report.final_score is not None


def test_reference_free_mode(tmp_path) -> None:
    config = _config(tmp_path)
    # 删除 human survey 后应进入 reference_free 模式
    human_survey = tmp_path / "datasets" / "hysurveybench_test" / "human_surveys" / "test_topic.md"
    assert human_survey.is_file()
    human_survey.unlink()
    provider = RoutingProvider(DEFAULT_ROUTES)
    runner = EvalRunner(load_dataset(config.dataset_dir), config, provider, run_id="e-test")
    dataset = runner.dataset
    report = runner.run([TopicInput(case=_topic(dataset), payload=_payload(tmp_path))])
    assert report.mode == "reference_free"


def test_load_run_payload_validation(tmp_path) -> None:
    run_dir = tmp_path / "runs" / "bad"
    run_dir.mkdir(parents=True)
    with pytest.raises(EvalRunnerError):
        load_run_payload(run_dir)
    (run_dir / "result.json").write_text(json.dumps({"task": {}}), encoding="utf-8")
    with pytest.raises(EvalRunnerError):
        load_run_payload(run_dir)


def test_runner_requires_model(tmp_path) -> None:
    config = EvalConfig(root=tmp_path)  # judge.model 为空
    with pytest.raises(EvalRunnerError):
        EvalRunner(
            load_dataset(str(build_dataset(tmp_path))), config, RoutingProvider([]), run_id="x"
        )


def test_match_topic_by_text(tmp_path) -> None:
    dataset = load_dataset(str(build_dataset(tmp_path)))
    case = dataset.match_topic(" test topic ")
    assert case is not None and case.id == "test_topic"
    assert dataset.match_topic("unknown") is None


def test_known_paper_universe(tmp_path) -> None:
    dataset = load_dataset(str(build_dataset(tmp_path)))
    universe = dataset.known_paper_ids()
    assert {"2201.00001", "2201.00002", "2201.00003"} <= universe
    metadata = dataset.metadata("2201.00001")
    assert metadata is not None and metadata.title == "Gaussian Splatting Method"
    assert dataset.metadata("nope") is None
    fulltext = dataset.fulltext("2201.00001")
    assert fulltext is not None and fulltext.sections[0].section_id == "sec_1"
    passages = fulltext.passages(50)
    assert passages and all(len(text) <= 50 for _, _, text in passages)
