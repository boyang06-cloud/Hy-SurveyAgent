# Evaluator 架构

## 1. 与 Application 的边界

```text
Application (app/)                    Evaluator (evaluator/)
────────────────────                  ──────────────────────
TaskInput + PaperSet                  Dataset (frozen)
   ↓ run_pipeline                        ↓
result.json 六字段 ──────────────→  D1–D8 评分
   (task/papers/survey/                  ↓
    claims/citations/              results/eval/<run_id>/
    evidence_map)
+ eval_payload.json
```

- Evaluator 只读 Application 的**最终产物**（`runs/<task_id>/result.json` 与 `eval_payload.json`），不 import `app.agents.*`、`app.core.pipeline`。
- 允许复用的 Application 组件：`app.model.provider.LLMProvider`（含 `generate_json`）、`app.config`、`app.io` 的只读部分。
- 生成侧统一入口是 `app.core.generator.SurveyGenerator`（`HySurveyAgentGenerator` / Baseline 实现），Baseline 对比实验只需替换该对象，Evaluator 零改动。

## 2. 四条 Track

```text
                    Generated Survey (result.json)
                           │
      ┌────────────────────┼────────────────────┐
      │                    │                    │
 Evidence Track      Survey Track          Quiz Track
      │                    │                    │
 Claim 抽取          Outline 解析         Quiz 集加载
      │                    │                    │
 Citation 映射       Chapter 切分         Section Retrieval
      │                    │                    │
 证据检索 (top-k)     ┌─────────┼─────────┐  Survey-only 作答
      │              │         │         │        │
   D1 事实        D3 覆盖   D4 综合   D5 结构  答案 Judge
   D2 引用                                │        │
                                        D7 术语   D6
      │
 Metadata / Rule Track → D8
      │
      └──────────────→ 加权聚合 → Critical Failure Gate → FINAL SCORE
```

Track 之间**不共享 Judge**，但共享：dataset 语料、证据检索器、LLM Provider 与成本统计。

## 3. 模块职责

| 模块 | 输入 | 输出 | 禁止 |
|---|---|---|---|
| `evidence/claims.py` | survey markdown | `AtomicClaim[]`（claim_id / text / citation_ids） | 抽取意见性、不可验证的表述 |
| `evidence/retriever.py` | claim + gold paper 语料 | `EvidencePassage[]`（paper_id / section_id / text / score） | 用模型参数知识代替检索 |
| `judges/factual.py` | claim + evidence | `{label, score(0/1/2), reason}` | 无证据时给分 |
| `judges/citation.py` | claims + citations + paper metadata | `{validity, precision, recall, fabricated[]}` | 只检查 `[1]` 格式 |
| `judges/coverage.py` | KIU rubric + survey 段落 | `{unit_id, score(0/1/2), evidence_span}` | 忽略 irrelevant 惩罚 |
| `judges/synthesis.py` | 整篇 survey | `{taxonomy, comparison, evolution, insight}` 各 0–4 | 按论文逐篇摘要给高分 |
| `judges/outline.py` | outline / headings | `{hierarchy, logic, function, relevance}` 各 0–4 | 用正文质量代替结构评价 |
| `quizzes/answerer.py` | quiz + survey | `{answer, used_sections, NO_SUFFICIENT_INFORMATION?}` | 让 Answerer 使用 survey 外知识 |
| `quizzes/scorer.py` | answer + reference_answer | `{accuracy(0-4), completeness(0-4), relevance(0-2)}` | 无 evidence 时给分 |
| `judges/terminology.py` | chapter | `{severe, moderate, minor}` 错误计数 | 把风格问题计为 severe |
| `rules/format.py` | survey markdown | 规则违规列表 | 引入 LLM |
| `rules/metadata.py` | citations + dataset papers | 相关性分布、重复、集中度 | 用引用数代替相关性 |
| `aggregate.py` | D1–D8 + gate 指标 | `final_score` + 应用过的 cap | 跳过 Gate |
| `report.py` | 多次运行 | Markdown 对比表 | 只报总分 |

## 4. 两种评测模式

- **Human-reference 模式**：dataset 提供 human survey + gold papers + KIU + topic quiz，可跑全部 D1–D8。
- **Reference-free 模式**：无 human survey 时仍可跑 D1/D2/D4/D5/General Quiz/D7/D8；D3 与 Topic Quiz 由检索到的权威论文构建，并在报告中标注 `mode=reference_free`。

报告必须标注本次使用的模式，两种模式的分数不可直接横向比较。

## 5. CLI 设计

```bash
uv run python -m evaluator \
  --dataset datasets/hysurveybench_v1.0 \
  --run runs/<task_id> \
  --dimensions D1,D2                 # 可选，默认全部
  --out results/eval/<run_id>        # 默认 results/eval/<时间戳>
  --judge-dual                       # 核心维度启用双 Judge
  --limit-topics 3
```

约定：

- 单个维度失败只记录 `error` 并把该维度置为 `null`，不中断整次评测；`null` 维度在聚合时按剩余权重重新归一化，并在报告中标注。
- `--judge-dual` 只作用于 D1/D2/D4/D6。
- 每次运行必须落 `config.json`（权重、模型名、temperature、prompt 版本与 hash、dataset 版本、git commit）。

## 6. 结果落盘结构

```text
results/eval/<run_id>/
├── config.json          # 复现所需全部元信息（不含密钥）
├── dimensions.json      # {D1: {...}, ..., "gate": {...}}
├── cost.json            # {calls, prompt_tokens, completion_tokens, latency_ms} by dimension
├── report.md            # 八维度表 + D6 分层表
└── per_topic/<topic_id>.json   # Judge 原始输出，可审计
```

`dimensions.json` 最小结构：

```json
{
  "run_id": "e-20260909-120000",
  "method": "Hy-SurveyAgent",
  "dataset_version": "hysurveybench_v1.0",
  "mode": "human_reference",
  "dimensions": {
    "D1": {"score": 78.4, "n_claims": 132, "unsupported": 9},
    "D2": {"score": 71.0, "precision": 0.82, "recall": 0.77, "fabricated_rate": 0.0}
  },
  "gate": {
    "fabricated_citation_rate": 0.0,
    "citation_recall": 0.77,
    "severe_contradictions": 1
  }
}
```

`results/` 必须 gitignore；`dimensions.json` 的字段命名与 `scripts/aggregate_scores.py` 保持一致。

## 7. 长文档策略

- **Document-level**：D4 / D5 / D8 可读性 —— 读取整篇（超长时按 outline 压缩后送入）。
- **Chapter-level**：D1 / D3 / D7 —— 按章节切分后并行 Judge。
- Chapter 分数按 **token/word 数加权**汇总，禁止简单平均（避免极短章节与长章节等权）。
