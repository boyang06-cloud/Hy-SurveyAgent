---
name: hy-surveyagent-eval-harness
description: 用于搭建 Hy-SurveyAgent 的 Evaluation Harness（evaluator/ 模块）。当需要根据 eval_protocol.md 实现 D1–D8 八个维度的评分器、编写 decomposed LLM Judge 与 Prompt、实现证据检索与 Quiz 作答协议、做加权聚合与 Critical Failure Gate，或生成评测报告与对比实验表时，应使用本 skill。它强制执行"分解式 Judge + 证据约束 + 结果可复现"，禁止用单一"请给这篇综述打分"式 Judge。
---

# Hy-SurveyAgent Evaluation Harness 开发

## 目标

构建独立于 Application 的评测模块，把 Application 产出的 Survey 结果映射为
**证据可靠性 → 综述质量 → 读者价值** 三层、八个维度的可复现分数。

第一版追求：**维度可单独运行、分数可追溯、Judge 可复现、结果可批量对比**。

## 权威来源

- 评测协议的唯一权威：`eval_harness/eval_protocol.md`（v2.0）。本 skill 与它冲突时以协议为准，并回来修订本 skill。
- Application 输出契约：`app/core/contract.py` + `.codebuddy/skills/hy-surveyagent-app/references/data-contracts.md` 第 10 节。

## 核心原则（不可违反）

1. **分解式 Judge**：D1–D8 各自使用职责单一的 Judge（Factual / Citation / Coverage / Synthesis / Outline / Quiz Answer / Terminology），禁止用 `Rate this survey from 1 to 10` 这类单一整体打分。
2. **证据约束**：Judge 只能基于 `Claim + 原始论文证据` 判断，禁止依赖模型参数知识；证据不足必须判 `UNSUPPORTED` / `NO_SUFFICIENT_INFORMATION`，不得"看起来对就给分"。
3. **维度独立可运行**：每个维度是独立模块，输入（dataset + 生成结果）确定即可单独跑，失败只影响自身维度。
4. **Evaluator 不写 Gold Data**：评测阶段只读 `datasets/<version>/`，禁止在评测流程中构造/修改 Gold Set、Rubric、Quiz（那是 `hy-surveyagent-eval-dataset` skill 的职责）。
5. **Judge 可复现**：`temperature = 0`；核心维度（D1/D2/D4/D6）建议双 Judge，分歧超阈值时引入 Judge C 取中位数。
6. **只依赖输出契约**：Evaluator 只消费六字段结果（`task/papers/survey/claims/citations/evidence_map`）与 `eval_payload`，禁止 import `app.agents.*` 或感知 Pipeline 内部。
7. **Prompt 外置**：Judge Prompt 存放于 `evaluator/prompts/*.md`，带 `version`，禁止写死在 Python 代码中。
8. **Gate 不可绕过**：加权总分之后必须应用 Critical Failure Gate，禁止只报加权平均。
9. **成本可观测**：记录每个维度的 LLM 调用数、token、latency，进入 `results/eval/<run_id>/cost.json`。
10. **密钥不入库**：与 Application 侧一致，只通过 `app.config` / `LLMProvider` 取 Key。

## 何时使用

- 搭建或重构 `evaluator/` 目录、CLI 入口、结果落盘结构
- 实现任一维度（D1–D8）的评分器或 Judge Prompt
- 实现 Quiz 作答协议（Section Retrieval → Survey-only Answer → Answer Judge）
- 实现加权聚合、Critical Failure Gate、报告表生成
- 做 Baseline 对比实验（Direct LLM / Search+LLM / Baseline Agent / Hy-SurveyAgent）
- 排查某个维度分数异常（先定位到 Judge 输入，而不是先改 Prompt 重跑）

需要构造/修订评测数据（Gold Papers、KIU、Quiz）时，改用 `hy-surveyagent-eval-dataset` skill。

## 维度速查

| ID | 维度 | 权重 | 主要方法 |
| -- | ---- | ---: | -------- |
| D1 | Factual & Scientific Accuracy | 18% | Claim 级证据 Judge（0/1/2） |
| D2 | Citation Correctness & Traceability | 18% | Validity + Precision/Recall → F1 |
| D3 | Topic & Information Coverage | 13% | Gold KIU Rubric + LLM Judge + Irrelevant 惩罚 |
| D4 | Cross-Paper Synthesis & Analytical Depth | 15% | Taxonomy/Comparison/Evolution/Insight 各 0–4 |
| D5 | Outline & Structural Quality | 8% | Hierarchy/Logic/Function/Relevance 各 0–4 |
| D6 | Reader-Need / Quiz Answerability | 15% | 0.4×General + 0.6×Topic Quiz |
| D7 | Terminology & Academic Rigor | 7% | 每 1000 词扣分制（Severe/Moderate/Minor） |
| D8 | Literature + Readability + Format | 6% | 3% 文献相关性 + 2% 可读性 + 1% 规则检查 |

总分：`0.18D1 + 0.18D2 + 0.13D3 + 0.15D4 + 0.08D5 + 0.15D6 + 0.07D7 + 0.06D8`，全部归一化到 `[0,100]`。

Critical Failure Gate（聚合后取 min）：

- Fabricated Citation Rate > 10% → `≤ 60`；> 30% → `≤ 40`
- Citation Recall < 40% → `≤ 50`
- Severe Contradictions ≥ 3 → `≤ 60`

精确公式、rubric 与边界见 `references/dimensions.md`。

## 推荐目录

```text
evaluator/
├── __init__.py
├── config.py              # 权重、Judge 温度、阈值、路径（不含密钥）
├── contract.py            # 维度结果 / EvalReport 数据模型
├── runner.py              # 单条样本跑完 D1–D8
├── aggregate.py           # 加权聚合 + Gate
├── report.py              # Markdown / JSON 报告表
├── evidence/
│   ├── retriever.py       # Claim → Gold Paper 语料 → top-k 段落
│   └── claims.py          # atomic claim 抽取与 claim↔citation 对齐
├── judges/
│   ├── base.py            # Judge 抽象（LLMProvider + prompt + schema 校验）
│   ├── factual.py  citation.py  coverage.py  synthesis.py
│   └── outline.py  quiz_answer.py  terminology.py
├── quizzes/
│   ├── answerer.py        # Section Retrieval + Survey-only 作答
│   └── scorer.py          # Accuracy/Completeness/Relevance
├── rules/
│   ├── format.py          # citation/heading/markdown/placeholder 规则检查
│   └── metadata.py        # 文献相关性、重复引用、来源集中度
├── prompts/               # 七类 Judge Prompt（.md，带 version）
└── __main__.py            # python -m evaluator
```

结果落盘（`results/` 不入库）：

```text
results/eval/<run_id>/
├── config.json        # 权重、模型、prompt 版本、dataset 版本、git commit
├── dimensions.json    # 八维度原始分 + 证据明细
├── cost.json          # LLM 调用数 / token / latency
├── report.md          # 对比表
└── per_topic/<topic_id>.json
```

## 开发顺序（增量推进，禁止一次写完）

1. **契约与骨架**：`evaluator/contract.py` + `config.py` + `__main__.py`，跑通"读六字段结果 → 输出空报告"。
2. **Evidence 层**：`evidence/claims.py`（atomic claim）+ `evidence/retriever.py`（top-k 段落）；这是 D1/D2 的地基，先做。
3. **D1 + D2**：Factual Judge 与 Citation Judge，含 Validity（伪造引用识别）。
4. **D5 + D8 的规则部分**：Outline Judge 与纯规则检查（确定性高、无依赖，可提前完成）。
5. **D4 + D3**：Synthesis Judge 与 Coverage Judge（依赖 dataset 的 Rubric/KIU）。
6. **D6 Quiz**：`quizzes/answerer.py` → `scorer.py` → D6。
7. **D7 + 聚合 + 报告**：Terminology Judge，然后 `aggregate.py`（含 Gate）与 `report.py`。
8. **Baseline 与校准**：接入 Direct LLM / Search+LLM / Baseline Agent，做 Human Calibration（Kappa / Spearman ≥ 0.70）。

每个维度完成后补：Prompt 文件、数据模型、unit test（解析 + 公式边界 + 降级）、落盘产物。

## 排查分数异常

自底向上定位：先看 `per_topic/<topic_id>.json` 中该维度的 Judge 输入是否完整（claim 抽取是否为空、证据检索是否命中、citation 映射是否错位），再检查评分公式，最后才改 Judge Prompt。禁止直接调权重让分数"好看"。

## 资源索引

- `references/architecture.md` —— 四条 Track 数据流、模块职责、CLI 设计、结果落盘、与 Application 的边界。
- `references/dimensions.md` —— D1–D8 的 rubric、公式、归一化、chapter-level 加权、Critical Failure Gate 细则。
- `references/judge-design.md` —— 七类 Judge 的输入/输出 JSON Schema、双 Judge 仲裁、evidence-gating、稳定性要求。
- `references/engineering-practices.md` —— uv/测试约定、Judge 缓存、成本记录、Provenance、禁止项与自检。
- `assets/templates/` —— `eval_config.example.yaml`、`judge_prompt_template.md`、`report_template.md`。
- `scripts/init_evaluator.py` —— 生成 `evaluator/` 骨架（模块 + prompts 占位 + config）。
- `scripts/aggregate_scores.py` —— 确定性加权聚合 + Gate（`references/dimensions.md` 的参考实现）。
- `scripts/check_eval_repo.py` —— 评测侧工程约定自检。

## 完成定义

- `python -m evaluator --dataset datasets/hysurveybench_v1.0 --run runs/<task_id>` 可无人介入跑完八维度。
- 每个维度的分数都能追溯到具体 Judge 输出与证据片段（`per_topic/*.json` 可审计）。
- 加权总分之后应用了 Critical Failure Gate，`report.md` 含八维度表与 D6 分层表。
- `python .codebuddy/skills/hy-surveyagent-eval-harness/scripts/check_eval_repo.py .` 无 FAIL 项。
