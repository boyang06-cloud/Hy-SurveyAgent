# Hy-SurveyAgent Evaluation Report

- Run ID：`<run_id>`
- Dataset：`<dataset_version>`（mode：`human_reference` / `reference_free`）
- Git commit：`<commit>`
- Model / temperature：`<model>` / `0`
- Prompt versions：`<factual 0.1.0, citation 0.1.0, ...>`

## Main Results

| Method             | Overall | D1 Fact | D2 Citation | D3 Coverage | D4 Synthesis | D5 Outline | D6 Quiz | D7 Rigor | D8 Other |
| ------------------ | ------: | ------: | ----------: | ----------: | -----------: | ---------: | ------: | -------: | -------: |
| Direct LLM         |         |         |             |             |              |            |         |          |          |
| Search + LLM       |         |         |             |             |              |            |         |          |          |
| Baseline Agent     |         |         |             |             |              |            |         |          |          |
| **Hy-SurveyAgent** |         |         |             |             |              |            |         |          |          |

## Quiz Breakdown (D6)

| Method         | Easy | Medium | Hard | Topic Quiz | Overall |
| -------------- | ---: | -----: | ---: | ---------: | ------: |
| Direct LLM     |      |        |      |            |         |
| Search + LLM   |      |        |      |            |         |
| Hy-SurveyAgent |      |        |      |            |         |

## Critical Failure Gate

| Run | Fabricated Rate | Citation Recall | Severe Contradictions | Cap Applied | Final |
| --- | --------------: | --------------: | --------------------: | ----------- | ----: |
|     |                 |                 |                       |             |       |

## Engineering Metrics

| Method         | P50 Latency | P95 Latency | LLM Calls | Input Tokens | Output Tokens | Cost / Survey | Success Rate |
| -------------- | ----------: | ----------: | --------: | -----------: | ------------: | ------------: | -----------: |
| Hy-SurveyAgent |             |             |           |              |               |               |              |

## Non-textual Richness（不计入主分）

| Figures / 10k words | Tables / 10k words | Diagrams / 10k words |
| ------------------: | -----------------: | --------------------: |
|                     |                    |                       |

## Human Calibration

| Judge Pair    | Cohen's Kappa | Spearman |
| ------------- | ------------: | -------: |
| Human ↔ Human |               |          |
| LLM ↔ Human   |               |          |

目标：Kappa ≥ 0.70 或 Spearman ≥ 0.70；不达标须修改 Prompt / Rubric 后重跑。

## Notes

<!-- 维度缺失、低置信度、模式差异、调参说明 -->
