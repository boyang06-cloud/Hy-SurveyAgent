"""CLI 入口：``uv run python -m evaluator``。

示例：
    uv run python -m evaluator --dataset datasets/hysurveybench_v1.0 \
        --run runs/<task_id> --out results/eval/<run_id>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_config  # noqa: E402
from app.model.hy3_adapter import Hy3Adapter  # noqa: E402
from evaluator.config import EvalConfig, load_eval_config  # noqa: E402
from evaluator.dataset import load_dataset  # noqa: E402
from evaluator.report import render_report  # noqa: E402
from evaluator.runner import EvalRunner, EvalRunnerError, TopicInput, load_run_payload  # noqa: E402


def _git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except OSError:
        return "unknown"


def _resolve_topic(dataset: Any, payload: dict[str, Any], topic_id: str | None):
    if topic_id:
        if topic_id not in dataset.topic_ids:
            raise SystemExit(f"未知 topic：{topic_id}（可选：{dataset.topic_ids}）")
        return dataset.topic(topic_id)
    task = payload.get("task") or {}
    case = dataset.match_topic(str(task.get("topic") or ""))
    if case is None:
        raise SystemExit(
            "无法按 topic 文本匹配数据集，请用 --topic-id 指定。"
            f"（task.topic={task.get('topic')!r}，可选：{dataset.topic_ids}）"
        )
    return case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行 Hy-SurveyAgent 评测（D1–D8）。")
    parser.add_argument("--dataset", required=True, help="冻结数据集目录 datasets/<version>")
    parser.add_argument("--run", required=True, help="Application 运行目录 runs/<task_id>")
    parser.add_argument("--config", default="", help="评测配置（configs/eval.yaml，可选）")
    parser.add_argument("--dimensions", default="", help="逗号分隔，默认全部（D1,...,D8）")
    parser.add_argument(
        "--judge-dual", action="store_true", help="核心维度（D1/D2/D4/D6）启用双 Judge"
    )
    parser.add_argument(
        "--limit-topics", type=int, default=0, help="只评测前 N 个 topic（0=不限制）"
    )
    parser.add_argument("--topic-id", default="", help="显式指定 topic id（默认按 topic 文本匹配）")
    parser.add_argument("--method", default="", help="被评测方法名（默认 Hy-SurveyAgent）")
    parser.add_argument("--out", default="", help="结果输出目录（默认 results/eval/<时间戳>）")
    args = parser.parse_args(argv)

    try:
        config: EvalConfig = load_eval_config(args.config or None, root=PROJECT_ROOT)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FAIL 配置加载失败：{exc}", file=sys.stderr)
        return 2
    config.dataset_dir = args.dataset
    config.run_dir = args.run
    if args.dimensions:
        try:
            from evaluator.config import _coerce_dimensions

            config.dimensions = _coerce_dimensions(args.dimensions)
        except ValueError as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
    if args.method:
        config.method = args.method
    if args.judge_dual:
        config.judge.dual_judge = True
        config.judge.dual_judge_dimensions = ("D1", "D2", "D4", "D6")
    if args.limit_topics > 0:
        # 单 run 场景仅有一个 topic；该开关为批量评测预留
        print("WARN --limit-topics 当前单 run 模式下不生效。")

    run_id = args.out or datetime.now().strftime("e-%Y%m%d-%H%M%S")
    out_dir = config.resolve(run_id if args.out else f"results/eval/{run_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        dataset = load_dataset(config.dataset_dir)
        payload = load_run_payload(config.resolve(args.run))
        case = _resolve_topic(dataset, payload, args.topic_id or None)
    except Exception as exc:  # noqa: BLE001 - CLI 统一退出码
        print(f"FAIL {exc}", file=sys.stderr)
        return 2

    app_config = load_config(PROJECT_ROOT, require_secrets=True)
    if not config.judge.model:
        config.judge.model = app_config.model.name

    llm = Hy3Adapter.from_config(app_config)
    runner = EvalRunner(dataset, config, llm, run_id=Path(run_id).name)
    try:
        report = runner.run([TopicInput(case=case, payload=payload)])
    except EvalRunnerError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    provenance = runner.prompt_provenance()
    snapshot: dict[str, Any] = {
        "run_id": Path(run_id).name,
        "method": config.method,
        "git_commit": _git_commit(PROJECT_ROOT),
        "dataset_version": dataset.version,
        "dataset_name": dataset.name,
        "mode": report.mode,
        "model": config.judge.model,
        "temperature": config.judge.temperature,
        "prompts": provenance,
        "config": config.to_dict(),
    }
    _dump(out_dir / "config.json", snapshot)
    _dump(out_dir / "dimensions.json", report.to_dict())
    _dump(out_dir / "cost.json", report.cost)
    per_topic = out_dir / "per_topic"
    per_topic.mkdir(parents=True, exist_ok=True)
    for result in report.per_topic:
        _dump(per_topic / f"{result['topic_id']}.json", result)
    (out_dir / "report.md").write_text(
        render_report(report, provenance=provenance), encoding="utf-8"
    )
    print(f"Final Score: {report.final_score}（raw {report.raw_score}）")
    print(f"结果已写入 {out_dir}")
    return 0


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
