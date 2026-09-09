# D1–D8 维度实现细则

本协议条目的权威来源为 `eval_harness/eval_protocol.md`；本文件是**实现速查**，把公式、rubric 与边界写死到可直接编码的程度。

所有维度最终归一化到 `[0,100]`。

---

## D1 — Factual & Scientific Accuracy（18%）

流程：`Survey → Atomic Claim 抽取 → Claim↔Citation 映射 → 检索原论文证据 → 证据约束 Judge`。

- 只评价 **factual / scientific claims**（方法定义、机制、架构、数据集、benchmark、数值结果、历史陈述、比较结论、局限、作者结论）。
- 每个 claim 三档：

| 档位 | 含义 |
|---|---|
| 2 | Fully Supported —— 证据明确支持 |
| 1 | Partially Supported —— 核心正确但缺条件 / 过度泛化 / 数值不精确 / 范围扩张 |
| 0 | Unsupported / Contradicted —— 不支持、矛盾、方法描述错误、归因错误、数值错误、捏造 |

$$D_1 = \frac{\sum_i claim_i}{2N} \times 100$$

- 长文档按 chapter-level Judge，chapter 分按 word 数加权汇总。
- Judge 必须看到 `Claim + Paper Evidence`；证据检索为空时直接判 0，不得改用参数知识。
- 统计 `severe_contradictions`（0 分且属于矛盾/捏造的 claim 数），供 Gate 使用。

---

## D2 — Citation Correctness & Traceability（18%）

### Validity

校验论文是否真实存在、title/author/DOI/arXiv ID/metadata 是否一致。
不存在的引用：`Citation Score = 0`，并记入 `Fabricated Citation`。

### Precision

对每个 claim-citation pair：`2 = Direct support / 1 = Partial / 0 = Unsupported`。

$$Precision = \frac{\sum support}{2N_c}$$

### Recall

先识别 **citation-worthy claims**：方法归因、实验结果、历史陈述、量化陈述、比较、文献结论。

$$Recall = \frac{\# cited\ citation\text{-}worthy\ claims}{\# citation\text{-}worthy\ claims}$$

### 合成

$$F1 = \frac{2PR}{P+R},\qquad D_2 = 100 \times F1$$

- `fabricated_citation_rate = fabricated / total_citations`。
- Precision 与 Recall 同时写入 `gate` 字段（见下方 Gate）。

---

## D3 — Topic & Information Coverage（13%）

输入：dataset 的 `rubrics/<topic>.json`（Key Information Units，带 `importance` 权重）。

每个 unit：`2 = fully covered / 1 = partially covered / 0 = missing`。

$$Coverage = \frac{\sum_i w_i r_i}{2\sum_i w_i} \times 100$$

### Irrelevant 惩罚

$$IrrelevantRate = \frac{N_{irrelevant\ paragraph}}{N_{paragraph}}$$

- `> 20%` → `D3 × 0.9`
- `> 40%` → `D3 × 0.7`

目的：防止靠大量扩写骗取 coverage。chapter-level Judge 后按 word 数加权。

---

## D4 — Cross-Paper Synthesis & Analytical Depth（15%）

四个子维度，各 `0–4`，总计 16：

$$D_4 = \frac{Taxonomy + Comparison + Evolution + Insight}{16} \times 100$$

| 子项 | 4 | 3 | 2 | 1 | 0 |
|---|---|---|---|---|---|
| Taxonomy | 明确合理且有解释依据的分类体系 | 分类合理但依据不充分 | 有分组但较浅 | 主要按论文/作者/年份排列 | 无分类 |
| Cross-paper Comparison | 系统多维比较（架构/假设/性能/效率/可扩展性/应用/局限） | 多次有意义的比较 | 少量直接比较 | 几乎都是逐论文摘要 | 无比较 |
| Research Evolution | 清楚说明演进与因果（Problem → Earlier → Limitation → Later） | 主要演进明确 | 有时间线但因果弱 | 只有 "Later work extends..." | 无演进 |
| Critical Insight | 多方向均有 evidence-grounded 批判分析 | 有明确 trade-off / limitation 分析 | 少量 insight | 只有模板化 "More research is needed." | 无分析 |

Document-level 单次 Judge（需观察整体结构）。

---

## D5 — Outline & Structural Quality（8%）

四个子项，各 `0–4`：

$$D_5 = \frac{Hierarchy + LogicalProgression + SectionFunction + OutlineRelevance}{16} \times 100$$

- **Hierarchy**：章节之间层次是否合理
- **Logical Progression**：章节是否形成逻辑推进
- **Section Function**：每个 section 作用清晰、无重复
- **Outline Relevance**：是否存在明显偏离主题的 section

Coverage 已在 D3，此处不重复评价覆盖度。

---

## D6 — Reader-Need / Quiz Answerability（15%）

### 作答协议（强制）

```text
Quiz → Survey Section Retrieval → Relevant Paragraphs
     → Answer using Survey ONLY → Evidence Citation → Answer Judge
```

- Answerer 被明确要求只能依据 Survey 内容；信息不足时输出 `NO_SUFFICIENT_INFORMATION`。
- 禁止直接把整篇 Survey 塞给 Judge 代答。

### 单题评分

| 维度 | 范围 |
|---|---|
| Accuracy | 0–4 |
| Completeness | 0–4 |
| Relevance | 0–2 |

单题满分 10；**evidence-gating**：Survey 中找不到 supporting evidence 时该题直接 `0` 分（答案表面正确也不给分）。

### 合成

- `G` = General Quiz 均分（模板化，所有 topic 共用）
- `T` = Topic-Specific Quiz 均分（由 gold papers + human survey 构造）

$$D_6 = 0.4G + 0.6T$$

建议分层报告：Easy / Medium / Hard / Topic Quiz。

---

## D7 — Terminology & Academic Rigor（7%）

检测：terminology、method name、acronym、概念区分、overclaim、不当 SOTA 表述、无依据的 novelty claim、错误因果措辞。

| 级别 | 含义 | 扣分（每 1000 words） |
|---|---|---|
| Severe | 改变科学含义（如"NeRF 是显式点云表示"） | −20 |
| Moderate | 概念基本正确但不严谨 | −8 |
| Minor | 缩写、命名或轻度表达问题 | −2 |

$$D_7 = \max\left(0,\ 100 - \frac{20N_{severe} + 8N_{moderate} + 2N_{minor}}{words/1000}\right)$$

chapter-level Judge 后按 word 数加权。

---

## D8 — Literature Quality + Readability + Format（6%）

### Literature Relevance — 3%

每篇被引论文：`2 = directly relevant / 1 = partially / 0 = irrelevant`。
同时记录：重复引用、极端来源集中度、明显低质/无关来源；query 强调 recent 时额外检测 temporal relevance。

$$D_{8a} = \frac{\sum relevance}{2N} \times 100$$

### Readability — 2%

Judge 0–4：4 专业紧凑易跟随 / 3 总体清晰少量冗余 / 2 明显重复或跳跃 / 1 大量模板化冗余 / 0 难以阅读。
`D_{8b} = readability / 4 × 100`。

### Format Validity — 1%

纯规则检查：citation 格式、reference 完整性、heading 合法性、Markdown 破损、重复 section、未替换占位符。
违规项扣分，`D_{8c}` 为规则通过率 × 100。

$$D_8 = \frac{3 D_{8a} + 2 D_{8b} + 1 D_{8c}}{6}$$

---

## 加权聚合

$$Score = 0.18D_1 + 0.18D_2 + 0.13D_3 + 0.15D_4 + 0.08D_5 + 0.15D_6 + 0.07D_7 + 0.06D_8$$

- 维度缺失（`null`）时按剩余权重重新归一化，并在报告中标注。
- 参考实现：`scripts/aggregate_scores.py`。

## Critical Failure Gate（聚合后取 min，不可绕过）

| 条件 | 上限 |
|---|---|
| `fabricated_citation_rate > 0.30` | `final ≤ 40` |
| `fabricated_citation_rate > 0.10` | `final ≤ 60` |
| `citation_recall < 0.40` | `final ≤ 50` |
| `severe_contradictions ≥ 3` | `final ≤ 60` |

多个条件同时命中取最严格的上限。

## 工程指标（不进入 100 分，单独报告）

`Latency / P50 / P95 / Input Tokens / Output Tokens / LLM Calls / Search Calls / Cost per Survey / Success Rate / Timeout Rate / Retrieval Failure Rate`，用于分析 Quality↔Cost、Quality↔Latency。

## Optional：Non-textual Richness（不纳入主分）

单独报告 `Figures / 10k words`、`Tables / 10k words`、`Diagrams / 10k words`。

## Human Calibration

正式跑 Benchmark 前随机抽 30–50 样本人工按同一 rubric 评价，计算 Cohen's Kappa 与 Spearman；目标 `≥ 0.70`，否则修订 Prompt / Rubric 后重来。
