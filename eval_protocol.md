# Hy-SurveyAgent Evaluation Protocol v2.0

## 1. Evaluation Goal

Hy-SurveyAgent 的核心任务为：

> **针对给定科研主题检索真实学术文献，并基于这些文献生成准确、可追溯、覆盖充分、具有跨文献综合能力，并能够满足科研读者核心信息需求的学术综述。**

因此，本项目不采用 ROUGE、BLEU 等文本相似度指标作为主要评价标准，而从以下三个层次评价生成综述：

```text
Evidence Reliability
        ↓
Survey Quality
        ↓
Reader Utility
```

即：

1. **Evidence Reliability**

   * 事实是否正确？
   * Citation 是否真实且支持 Claim？

2. **Survey Quality**

   * 是否覆盖领域核心问题？
   * 是否形成合理结构？
   * 是否进行了跨文献综合与分析？

3. **Reader Utility**

   * 读者能否通过该综述真正回答这个领域的重要问题？

---

# 2. Overall Evaluation Framework

最终采用 **8 个主要维度，总分 100 分**。

| ID | Evaluation Dimension                      |   Weight | Evaluation Method                      |
| -- | ----------------------------------------- | -------: | -------------------------------------- |
| D1 | Factual & Scientific Accuracy             |  **18%** | Claim-Level Evidence Judge             |
| D2 | Citation Correctness & Traceability       |  **18%** | Citation Precision / Recall / Validity |
| D3 | Topic & Information Coverage              |  **13%** | Gold Rubric + LLM Judge                |
| D4 | Cross-Paper Synthesis & Analytical Depth  |  **15%** | Rubric-based LLM Judge                 |
| D5 | Outline & Structural Quality              |   **8%** | Outline-level Judge                    |
| D6 | Reader-Need / Quiz Answerability          |  **15%** | Quiz-based Evaluation                  |
| D7 | Terminology & Academic Rigor              |   **7%** | LLM Judge                              |
| D8 | Literature Quality + Readability + Format |   **6%** | Metadata + Rules + Judge               |
|    | **Total**                                 | **100%** |                                        |

最终得分：

$$
Score =
0.18D_1+
0.18D_2+
0.13D_3+
0.15D_4+
0.08D_5+
0.15D_6+
0.07D_7+
0.06D_8
$$

所有指标归一化至 `[0,100]`。

---

# 3. Design Rationale

本协议主要结合两类评价思想。

## 3.1 Evidence-grounded Evaluation

来自 ScholarQABench / OpenScholar 等 scientific synthesis evaluation：

* factual correctness；
* citation precision；
* citation recall；
* evidence attribution；
* coverage。

这些指标重点回答：

> 生成内容是否可信？

---

## 3.2 Reader-aligned Survey Evaluation

SurveyBench 指出：

单纯让 LLM Judge 阅读整篇 survey 后评价：

* coverage；
* depth；
* coherence；
* fluency；

仍可能高估自动生成综述。

原因是：

> 一篇文章可以结构完整、语言流畅，看起来涵盖很多方向，但真正面对专业读者问题时却无法提供答案。

SurveyBench 因此提出 Quiz-based Evaluation，用：

```text
Survey
   ↓
Reader Question
   ↓
Retrieve Relevant Survey Content
   ↓
Answer Using Survey Only
   ↓
Evaluate Answer
```

间接测量综述的信息价值。

本项目采用这一思想，将 **Quiz Answerability** 作为独立核心指标。

---

# 4. Three-Layer Evaluation Architecture

完整 Evaluation 被划分为三层：

```text
Layer 1 — Evidence Reliability
│
├── D1 Factual Accuracy
└── D2 Citation Correctness

Layer 2 — Survey Construction Quality
│
├── D3 Information Coverage
├── D4 Cross-paper Synthesis
├── D5 Outline & Structure
├── D7 Terminology & Rigor
└── D8 Literature / Format

Layer 3 — Reader Utility
│
└── D6 Quiz Answerability
```

其中：

```text
Evidence Reliability = 36%
Survey Quality        = 49%
Reader Utility        = 15%
```

---

# 5. D1 — Factual & Scientific Accuracy

## Weight

**18%**

---

## 5.1 Objective

评价生成综述中所有可验证科学陈述是否与原始文献一致。

重点包括：

* 方法定义；
* algorithm mechanism；
* model architecture；
* dataset；
* benchmark；
* numerical result；
* historical claim；
* comparative claim；
* limitations；
* author conclusions。

---

# 5.2 Atomic Claim Extraction

首先将 survey 转换为 atomic factual claims。

例如：

```text
3D Gaussian Splatting represents scenes using anisotropic
3D Gaussians and enables real-time rendering.
```

拆解为：

```text
C1:
3DGS represents scenes using anisotropic 3D Gaussians.

C2:
3DGS supports real-time rendering.
```

只评价 factual / scientific claims。

---

# 5.3 Scoring Rubric

每个 claim：

### 2 — Fully Supported

对应文献中的证据明确支持该 claim。

### 1 — Partially Supported

核心意思正确，但存在：

* missing condition；
* over-generalization；
* imprecise numerical value；
* scope expansion。

### 0 — Unsupported / Contradicted

满足任一：

* paper 不支持；
* 与 paper 矛盾；
* 方法描述错误；
* attribution 错误；
* numerical result 错误；
* fabricated scientific claim。

---

# 5.4 Metric

$$
D_1 =
\frac{\sum_i claim_i}
{2N}
\times100
$$

---

# 5.5 Evaluation Pipeline

```text
Generated Survey
      ↓
Atomic Claim Extraction
      ↓
Claim ↔ Citation Mapping
      ↓
Retrieve Original Paper Evidence
      ↓
Evidence-Constrained LLM Judge
      ↓
Supported / Partial / Unsupported
```

Judge 必须基于：

```text
Claim
+
Paper Evidence
```

而不是自身参数知识。

---

# 6. D2 — Citation Correctness & Traceability

## Weight

**18%**

Citation 是 scientific survey 的核心可靠性机制。

该指标拆为三个部分：

```text
Citation Validity
Citation Precision
Citation Recall
```

---

# 6.1 Citation Validity

验证：

* paper 是否真实存在；
* title 是否对应；
* author 是否对应；
* DOI / arXiv ID 是否真实；
* metadata 是否一致。

对于不存在的 citation：

```text
Citation Score = 0
```

并记录为：

```text
Fabricated Citation
```

---

# 6.2 Citation Precision

问题：

> 这个 citation 是否真的支持它后面的 claim？

每个 claim-citation pair：

```text
2 = Direct support
1 = Partial support
0 = Unsupported
```

$$
Precision =
\frac{\sum support}
{2N_c}
$$

---

# 6.3 Citation Recall

首先识别 citation-worthy claims：

* method attribution；
* experimental result；
* historical claim；
* quantitative claim；
* comparison；
* literature conclusion。

然后判断是否提供有效 citation。

$$
Recall =
\frac{
\# cited\ citation-worthy\ claims
}{
\# citation-worthy\ claims
}
$$

---

# 6.4 Citation F1

$$
F1=
\frac{2PR}{P+R}
$$

最终：

$$
D_2 = 100\times F1
$$

---

# 7. D3 — Topic & Information Coverage

## Weight

**13%**

Coverage 回答：

> 一个真正想了解这个领域的人应该知道的重要内容，Survey 是否覆盖？

---

# 7.1 Key Information Units

对于每个 Benchmark Topic，预先构造：

```text
Key Information Units
```

例如 Topic：

```text
3D Gaussian Splatting
```

Gold Rubric：

```yaml
R1:
  content: Definition and scene representation
  weight: 2

R2:
  content: Differentiable splatting / rasterization
  weight: 2

R3:
  content: Optimization process
  weight: 2

R4:
  content: Comparison with NeRF
  weight: 2

R5:
  content: Dynamic Gaussian methods
  weight: 1

R6:
  content: Compression / efficiency
  weight: 1

R7:
  content: Main limitations
  weight: 1
```

---

# 7.2 Coverage Score

每个 information unit：

```text
2 = fully covered
1 = partially covered
0 = missing
```

$$
Coverage=
\frac{\sum_iw_ir_i}
{2\sum_iw_i}
\times100
$$

---

# 7.3 Relevance

同时检测明显 off-topic 内容。

$$
IrrelevantRate=
\frac{N_{irrelevant\ paragraph}}
{N_{paragraph}}
$$

如果：

```text
IrrelevantRate > 20%
```

则：

```text
D3 × 0.9
```

如果：

```text
IrrelevantRate > 40%
```

则：

```text
D3 × 0.7
```

防止模型通过大量扩写获取虚假 coverage。

---

# 8. D4 — Cross-Paper Synthesis & Analytical Depth

## Weight

**15%**

这是最能区分：

```text
Survey
```

和：

```text
Paper Summary Collection
```

的指标之一。

SurveyBench 同样指出，现有 Survey Agent 的主要问题之一是缺乏独立归纳、聚类和跨论文分析，大量内容只是重新表述 source。

因此，本指标不评价“是否总结了论文”，而评价：

> 是否产生了跨论文层面的知识结构。

---

# 8.1 Four Sub-dimensions

每项 `0–4`。

---

## A. Taxonomy

### 4

形成明确、合理、具有解释依据的技术 taxonomy。

### 3

存在合理 taxonomy，但部分分类依据不充分。

### 2

有方法分组，但分类较浅。

### 1

主要按论文、作者或年份排列。

### 0

无分类。

---

## B. Cross-paper Comparison

检查是否围绕统一维度比较多个方法：

* architecture；
* assumptions；
* performance；
* efficiency；
* scalability；
* application；
* limitations。

### 4

存在系统、多维比较。

### 3

存在多次有意义比较。

### 2

仅少量直接比较。

### 1

绝大多数为逐论文摘要。

### 0

完全没有比较。

---

## C. Research Evolution

理想结构：

```text
Problem
   ↓
Earlier Method
   ↓
Limitation
   ↓
Later Improvement
```

### 4

清楚说明技术演进及因果关系。

### 3

主要演进关系明确。

### 2

存在 chronological description，但因果较弱。

### 1

只说：

"Later work extends..."

### 0

无演进关系。

---

## D. Critical Insight

检查是否分析：

* limitations；
* trade-offs；
* conflicting evidence；
* open problems；
* research gaps；
* promising directions。

### 4

多个核心方向均有 evidence-grounded critical analysis。

### 3

存在明确 trade-off / limitation 分析。

### 2

存在少量 insight。

### 1

仅出现模板化：

```text
More research is needed.
```

### 0

没有 analysis。

---

# 8.2 Score

$$
D_4=
\frac{
Taxonomy+
Comparison+
Evolution+
Insight
}{16}\times100
$$

---

# 9. D5 — Outline & Structural Quality

## Weight

**8%**

SurveyBench 将 Outline Quality 与 Content Quality 分开评价，这是一个值得保留的设计。

因为：

> 一个章节内部写得很好，并不意味着整篇 survey 的知识组织合理。

SurveyBench 的 Outline Evaluation 包括：

* Coverage；
* Relevance；
* Structure。

本项目由于 Coverage 已独立进入 D3，因此这里重点评价：

```text
Hierarchical Organization
Logical Ordering
Section Functionality
Topic Alignment
```

---

# 9.1 Scoring

4 个子项，每项 0–4。

## Hierarchy

章节之间是否存在合理层次。

## Logical Progression

章节是否形成逻辑推进关系。

## Section Function

每个 section 是否有清晰作用，而非重复。

## Outline Relevance

是否存在明显偏离主题的 section。

---

$$
D_5=
\frac{
H+L+F+R
}{16}
\times100
$$

---

# 10. D6 — Reader-Need / Quiz Answerability

## Weight

**15%**

这是 v2.0 相比原方案最重要的变化。

---

# 10.1 Motivation

传统 Judge 评价的是：

> “这篇 Survey 看起来好吗？”

Quiz Evaluation 改为评价：

> “读完这篇 Survey，读者能不能回答这个领域真正重要的问题？”

SurveyBench 实验发现：

即使 LLM-generated survey 在：

* focus；
* coherence；
* fluency；

上接近 human survey，

在 topic-specific quizzes 上仍然出现巨大差距。

因此 Quiz 能有效检测：

```text
Shallow Coverage
Fake Comprehensiveness
Missing Technical Detail
Missing Comparison
Missing Reasoning
```

---

# 10.2 Two Types of Quiz

采用：

```text
General Quiz
+
Topic-Specific Quiz
```

---

# 10.3 General Quiz

所有 topic 使用统一能力模板。

分为三层。

---

## Easy — Foundational Knowledge

### Concept Definition

例如：

```text
What problem does X solve,
and what are its core assumptions?
```

### Taxonomy

```text
What major categories of methods exist,
and what criterion separates them?
```

### Historical Development

```text
What are the major stages in the development of X?
```

---

## Medium — Technical Understanding

### Algorithm Principle

```text
How does method X work,
and what are its key components?
```

### Method Comparison

```text
How do method A and B differ in
assumption, architecture and performance?
```

### Performance Analysis

```text
What datasets and metrics are commonly used
to evaluate these methods?
```

### Practical Considerations

仅在对应主题适用时：

```text
What implementation constraints or
computational trade-offs matter in practice?
```

---

## Hard — Higher-order Survey Understanding

### Limitations

```text
What fundamental limitations remain?
```

### Research Gaps

```text
Which important problems remain unresolved?
```

### Future Directions

```text
What future directions are supported
by the evidence summarized in the survey?
```

---

# 10.4 Topic-Specific Quiz

从该 topic 的：

```text
Expert Survey
+
Gold Papers
```

构建细粒度 questions。

要求：

1. question self-contained；
2. 存在明确 reference answer；
3. reference answer 有 source evidence；
4. 不能只依靠常识回答；
5. question 必须涉及 substantive scientific content。

例如：

```json
{
  "question":
    "Why does the tile-based rasterizer in 3DGS
     improve rendering efficiency?",

  "reference_answer":
    "...",

  "evidence":
    ["paper_01:p12", "paper_07:p4"]
}
```

---

# 10.5 Quiz Answering Protocol

禁止直接让 Judge 阅读完整 Survey 后回答。

采用：

```text
Quiz
 ↓
Survey Section Retrieval
 ↓
Relevant Paragraphs
 ↓
Answer using Survey ONLY
 ↓
Evidence Citation
 ↓
Answer Judge
```

Answerer 被明确要求：

> 只能依据 Survey 中的信息回答。

如果 Survey 不包含足够信息：

```text
NO_SUFFICIENT_INFORMATION
```

---

# 10.6 Quiz Score

每道题从三个维度评分：

```text
Accuracy      0–4
Completeness  0–4
Relevance     0–2
```

总计：

```text
0–10
```

如果 Survey 中无法找到 supporting evidence：

```text
Quiz Score = 0
```

借鉴 SurveyBench 的 evidence-gating 思想：即使答案表面正确，如果无法由 survey 内容支撑，也不能得分。

---

# 10.7 Final D6

设：

```text
General Quiz Score = G
Topic Quiz Score   = T
```

则：

$$
D_6 =
0.4G + 0.6T
$$

Topic-specific quiz 权重更高，因为更能测试：

> Survey 是否真正覆盖该领域具体、专业的信息需求。

---

# 11. D7 — Terminology & Academic Rigor

## Weight

**7%**

检测：

* terminology；
* method name；
* acronym；
* conceptual distinction；
* overclaim；
* inappropriate SOTA statement；
* unsupported novelty claim；
* incorrect causal wording。

---

# 11.1 Error Levels

## Severe

改变科学含义。

例如：

```text
NeRF is an explicit point-cloud representation.
```

## Moderate

概念基本正确但不严谨。

## Minor

缩写、命名或轻度表达问题。

---

# 11.2 Score

按每 1000 words 归一化：

```text
Severe    -20
Moderate   -8
Minor      -2
```

最低 0。

---

# 12. D8 — Literature Quality, Readability & Format

## Weight

**6%**

该维度只保留必要的 secondary survey quality。

---

# 12.1 Literature Relevance — 3%

检查引用论文：

```text
2 = directly relevant
1 = partially relevant
0 = irrelevant
```

同时记录：

* duplicate references；
* extreme source concentration；
* obvious low-quality / unrelated source。

如果 query 强调 recent：

额外检测 temporal relevance。

---

# 12.2 Readability — 2%

Judge 从 0–4 判断：

### 4

专业、紧凑、容易跟随。

### 3

总体清晰，少量冗余。

### 2

存在明显重复或跳跃。

### 1

大量模板化 / 冗余。

### 0

难以阅读。

---

# 12.3 Format Validity — 1%

规则检查：

* citation format；
* reference completeness；
* heading validity；
* broken Markdown；
* duplicate sections；
* unresolved placeholders。

---

# 13. Optional Metric — Non-textual Richness

SurveyBench 单独评价：

* figure；
* chart；
* table；
* diagram；

等 non-textual elements 的 richness。

本项目 **不将 Richness 纳入主 100 分**。

原因：

Hy-SurveyAgent 当前核心任务是：

```text
Literature Retrieval
+
Evidence Synthesis
+
Survey Generation
```

而非自动出版完整 survey manuscript。

因此 Richness 单独报告：

```text
Figures / 10k words
Tables / 10k words
Diagrams / 10k words
```

未来若系统增加自动图表生成能力，可将其升级为主指标。

---

# 14. Critical Failure Gate

最终分数不能简单做 weighted average。

以下错误属于 scientific survey 的 critical failure。

---

## 14.1 Fabricated Citation

如果：

```text
Fabricated Citation Rate > 10%
```

则：

```text
Final Score ≤ 60
```

如果：

```text
Fabricated Citation Rate > 30%
```

则：

```text
Final Score ≤ 40
```

---

## 14.2 Evidence Failure

若：

```text
Citation Recall < 40%
```

则：

```text
Final Score ≤ 50
```

---

## 14.3 Severe Scientific Errors

核心 scientific claim 中出现：

```text
≥ 3 Severe Contradictions
```

则：

```text
Final Score ≤ 60
```

---

# 15. Human-reference vs Reference-free Evaluation

借鉴 SurveyBench，Evaluation 支持两种模式。

---

# 15.1 Human-reference Mode

Benchmark 存在 high-quality human survey 时：

使用：

```text
Human Survey
+
Gold Reference Papers
```

构造：

* Key Information Units；
* Topic-specific quizzes；
* representative literature；
* taxonomy reference。

注意：

**不直接使用文本相似度比较 human survey。**

Human Survey 被视为：

```text
knowledge source
```

而不是：

```text
唯一正确答案
```

---

# 15.2 Reference-free Mode

不存在 human survey 时：

仍然可评价：

```text
D1 Factuality
D2 Citation
D4 Synthesis
D5 Structure
General Quiz
D7 Terminology
D8 Format
```

D3 Coverage 与 Topic Quiz：

由检索到的 authoritative papers 构建。

---

# 16. LLM-as-Judge Strategy

禁止使用：

```text
Rate this survey from 1 to 10.
```

这样的单一 Judge。

使用 decomposed evaluation：

```text
Factual Judge
Citation Judge
Coverage Judge
Synthesis Judge
Outline Judge
Quiz Answer Judge
Terminology Judge
```

每个 Judge 只解决一个明确问题。

---

# 17. Judge Output Format

统一输出 structured JSON。

例如：

```json
{
  "claim_id": "C12",
  "claim": "...",
  "citation": "P07",
  "evidence": "...",
  "label": "PARTIALLY_SUPPORTED",
  "score": 1,
  "reason": "The paper supports X but not Y."
}
```

---

# 18. Long-document Evaluation

SurveyBench 同时使用：

```text
Document-level Evaluation
+
Chapter-level Evaluation
```

本项目也采用这一策略。

---

## Document-Level

用于：

```text
D4 Synthesis
D5 Outline
D8 Readability
```

需要观察整体结构。

---

## Chapter-Level

用于：

```text
D1 Factuality
D3 Coverage
D7 Terminology
```

避免长上下文 Judge 忽略局部问题。

最终 chapter score 按 token/word 数加权，而不是简单平均，以避免极短章节和长章节拥有同等影响。

---

# 19. Judge Stability

Judge：

```text
temperature = 0
```

核心指标：

```text
D1
D2
D4
D6
```

建议双 Judge。

如果：

```text
|Judge_A - Judge_B| > threshold
```

调用 Judge C。

最终：

```text
median(A,B,C)
```

---

# 20. Human Calibration

正式跑 Benchmark 前：

随机抽取：

```text
30–50 survey samples / sections
```

人工按照相同 rubric 评价。

计算：

```text
Human ↔ Human
LLM ↔ Human
```

建议：

```text
Cohen's Kappa
Spearman Correlation
```

目标：

```text
Kappa ≥ 0.70
```

或：

```text
Spearman ≥ 0.70
```

达不到则修改 prompt / rubric。

---

# 21. Benchmark Construction

每个 benchmark case：

```json
{
  "id": "topic_xxx",

  "topic": "...",

  "human_survey": "...",

  "gold_papers": [],

  "key_information_units": [],

  "general_quizzes": [],

  "topic_quizzes": []
}
```

---

# 22. Quiz Construction Pipeline

Topic-specific Quiz 推荐：

```text
High-quality Human Survey
        +
Gold Papers
        ↓
Retrieve Technical Paragraphs
        ↓
Generate Candidate Quiz
        ↓
Generate Reference Answer
        ↓
Evidence Alignment Check
        ↓
Difficulty Filtering
        ↓
Final Quiz Set
```

每个 quiz 必须保存：

```json
{
  "question": "...",

  "answer": "...",

  "difficulty": "medium",

  "type": "method_comparison",

  "source": ["paper_03"],

  "evidence": ["paper_03:section_4"]
}
```

---

# 23. Recommended Quiz Distribution

每个 topic 建议：

| Type                    | Number |
| ----------------------- | -----: |
| Concept / Background    |      2 |
| Taxonomy                |      2 |
| Historical Evolution    |      1 |
| Algorithm Principle     |      3 |
| Method Comparison       |      3 |
| Performance / Benchmark |      2 |
| Limitations             |      2 |
| Research Gap / Future   |      2 |
| **Total**               | **17** |

建议范围：

```text
15–25 quizzes / topic
```

无需照搬 SurveyBench 的固定数量。

---

# 24. Final Evaluation Pipeline

```text
                    Generated Survey
                           │
          ┌────────────────┴────────────────┐
          │                                 │
     Evidence Track                   Survey Track
          │                                 │
     Claim Extraction                  Outline Parse
          │                                 │
     Citation Mapping                 Chapter Parse
          │                                 │
     Original Papers                         │
          │                    ┌─────────────┼─────────────┐
          │                    │             │             │
      D1 Fact             D3 Coverage   D4 Synthesis   D5 Outline
      D2 Citation                           │
                                            │
                                      D7 Terminology

                           Survey
                              │
                          Quiz Set
                              │
                     Section Retrieval
                              │
                      Survey-only Answer
                              │
                       Answer Evaluation
                              │
                             D6

                    Metadata / Rule Check
                              │
                             D8

                              ↓

                    Weighted Aggregation

                              ↓

                    Critical Failure Gate

                              ↓

                       FINAL SCORE
```

---

# 25. Final Metric Summary

```text
Hy-SurveyAgent Eval v2.0
│
├── D1 Factual Accuracy                 18%
│
├── D2 Citation Correctness             18%
│
├── D3 Information Coverage             13%
│
├── D4 Cross-paper Synthesis            15%
│
├── D5 Outline & Structure               8%
│
├── D6 Reader-Need / Quiz               15%
│
├── D7 Terminology & Rigor               7%
│
└── D8 Literature / Readability           6%
                                      ─────
                                       100%
```

其中三类核心能力：

```text
Reliability
D1 + D2
= 36%

Knowledge Coverage & Synthesis
D3 + D4 + D5
= 36%

Reader Utility
D6
= 15%
```

---

# 26. Final Result Table

正式实验报告：

| Method             | Overall | Fact | Citation | Coverage | Synthesis | Outline | Quiz | Rigor | Other |
| ------------------ | ------: | ---: | -------: | -------: | --------: | ------: | ---: | ----: | ----: |
| Direct LLM         |         |      |          |          |           |         |      |       |       |
| Search + LLM       |         |      |          |          |           |         |      |       |       |
| Baseline Agent     |         |      |          |          |           |         |      |       |       |
| **Hy-SurveyAgent** |         |      |          |          |           |         |      |       |       |

Quiz 进一步单独报告：

| Method         | Easy | Medium | Hard | Topic Quiz | Overall |
| -------------- | ---: | -----: | ---: | ---------: | ------: |
| Direct LLM     |      |        |      |            |         |
| Search + LLM   |      |        |      |            |         |
| Hy-SurveyAgent |      |        |      |            |         |

---

# 27. Secondary Engineering Metrics

不进入正文质量 100 分：

```text
Latency
P50 Latency
P95 Latency

Input Tokens
Output Tokens
LLM Calls
Search Calls
Cost / Survey

Success Rate
Timeout Rate
Retrieval Failure Rate
```

用于分析：

```text
Quality ↔ Cost
Quality ↔ Latency
```

---

# 28. Why This Protocol Is Suitable for Hy-SurveyAgent

本协议最终不是简单问：

> “Judge 觉得这篇文章写得好吗？”

而是连续验证四层问题：

```text
第一层
它写的是不是真的？

        ↓

第二层
它引用的论文真的支持这些话吗？

        ↓

第三层
它有没有把这个研究领域真正重要的内容
组织、比较和综合出来？

        ↓

第四层
真实科研读者带着重要问题阅读这篇综述时，
能不能从中得到准确、完整、有证据的答案？
```

因此最终评价目标为：

> **A high-quality Hy-SurveyAgent output should be factually reliable, evidence-traceable, comprehensively organized, analytically synthesized, and genuinely useful for answering the information needs of scientific readers.**
