# Hy-SurveyAgent 评测集构造设计文档

## 1. 目标

本项目计划基于 Hugging Face 数据集：

`InternScience/SurveyBench`

构造 Hy-SurveyAgent 的 Evaluation Dataset。

原始数据集主要提供：

* 研究主题；
* 每个主题对应的大规模 benchmark reference pool；
* 人工综述引用的论文集合；
* SurveyForge 生成综述所引用的论文集合。

但 Hy-SurveyAgent Evaluation Protocol v2.0 需要进一步评价：

* D1 Factual Accuracy；
* D2 Citation Correctness；
* D3 Information Coverage；
* D4 Cross-paper Synthesis；
* D5 Outline & Structure；
* D6 Reader-Need / Quiz Answerability；
* D7 Terminology & Academic Rigor；
* D8 Literature / Readability / Format。

因此需要将 SurveyBench 的 reference-oriented 数据转换并增强为：

> **Topic + Human Reference + Gold Literature + Paper Evidence + Key Information Units + Quizzes**

构成的结构化评测集。

---

# 2. 一个需要首先说明的问题

存在两个同名但不同的 SurveyBench。

## 2.1 本项目当前使用的数据

Hugging Face：

```text
InternScience/SurveyBench
```

对应的是 SurveyForge：

```text
SurveyForge:
On the Outline Heuristics, Memory-Driven Generation,
and Multi-dimensional Evaluation for Automated Survey Writing
```

HF Dataset Card 绑定的是：

```text
arXiv:2503.04629
```

当前仓库大小约 1.36 MB，顶层主要包含：

```text
SurveyBench/
├── generated_surveys_ref/
├── human_written_ref/
├── ref_bench/
├── README.md
├── test.py
└── topics.txt
```

---

## 2.2 上一阶段参考的 SurveyBench

我们上一阶段讨论的：

```text
SurveyBench:
Can LLM(-Agents) Write Academic Surveys
that Align with Reader Needs?
```

对应：

```text
arXiv:2510.03120
OpenDataBox/SurveyBench
```

这是另一个项目，包含：

* 完整 Markdown survey；
* human survey；
* content evaluation；
* outline evaluation；
* quiz evaluation；
* reader-need evaluation。

其公开仓库要求 human / generated survey 使用相同 topic filename，并使用 Markdown 层级结构。

---

## 2.3 本项目建议

**数据基础采用 InternScience/SurveyBench；评测思想与 Quiz 数据结构借鉴 OpenDataBox/SurveyBench。**

即：

```text
InternScience/SurveyBench
        ↓
提供 Topic + Paper Pool
        ↓
我们自行增强
        ↓
Hy-SurveyAgent Eval Dataset
        ↓
支持 Eval Protocol v2.0
```

而不是直接照搬任意一个 SurveyBench。

---

# 3. InternScience/SurveyBench 原始数据梳理

## 3.1 topics.txt

当前包含 10 个主题：

```text
3D Gaussian Splatting

3D Object Detection in Autonomous Driving

Evaluation of Large Language Models

LLM-based Multi-Agent

Generative Diffusion Models

Graph Neural Networks

Hallucination in Large Language Models

Multimodal Large Language Models

Retrieval-Augmented Generation for Large Language Models

Vision Transformers
```

这些主题均属于 CS / AI，和我们的 Survey Agent 使用场景高度匹配。

因此：

> 第一版 Benchmark 建议直接保留全部 10 个 topic。

这样既覆盖：

* CV；
* 3D Vision；
* Generative AI；
* LLM；
* Agent；
* RAG；
* GNN；

又可以避免自行设计 topic 带来的 benchmark 主观性。

---

# 4. ref_bench

目录：

```text
ref_bench/
```

每个 topic 对应一个 JSON：

```text
3D Gaussian Splatting_bench.json
3D Object Detection in Autonomous Driving_bench.json
Evaluation of Large Language Models_bench.json
...
```

共 10 个文件。

---

# 4.1 数据格式

以：

```text
3D Gaussian Splatting_bench.json
```

为例：

```json
{
  "2308.04079": {
    "arxivId": "2308.04079",
    "title": "3D Gaussian Splatting for Real-Time Radiance Field Rendering"
  },

  "2310.08528": {
    "arxivId": "2310.08528",
    "title": "4D Gaussian Splatting for Real-Time Dynamic Scene Rendering"
  }
}
```

也就是说：

```text
key
=
arXiv ID

value
=
{
    arxivId,
    title
}
```

---

# 4.2 数据量

Dataset Card 给出的 reference pool 规模为：

| Topic                               | References |
| ----------------------------------- | ---------: |
| Multimodal Large Language Models    |        912 |
| Evaluation of Large Language Models |        714 |
| 3D Object Detection                 |        441 |
| Vision Transformers                 |        563 |
| LLM Hallucination                   |        500 |
| Diffusion Models                    |        994 |
| 3D Gaussian Splatting               |        330 |
| LLM Multi-Agent                     |        823 |
| Graph Neural Networks               |        670 |
| RAG                                 |        608 |

注意：

这里不能把这些论文理解成：

> “每篇都是必须覆盖的 Gold Paper”。

它们更合理的定位是：

> **Topic-level Reference Candidate Pool**

即：

```text
benchmark_pool
```

---

# 4.3 重要问题

Reference pool 中并不只有核心主题论文。

例如 3D Gaussian Splatting pool 同时存在：

* 3DGS；
* NeRF；
* diffusion；
* SLAM；
* autonomous driving；
* robotics；
* datasets；
* reconstruction；

甚至存在与主题关系较弱的基础论文。

因此：

```text
ref_bench
≠
Gold Paper Set
```

必须经过进一步筛选。

---

# 5. human_written_ref

目录：

```text
human_written_ref/
```

存放不同主题人工综述的 reference extraction。

例如：

```text
A Survey on 3D Gaussian Splatting.json
A Survey on Evaluation of Large Language Models.json
A Survey on Multimodal Large Language Models.json
...
```

---

# 5.1 格式

仍然是：

```json
{
  "2308.04079": {
    "arxivId": "2308.04079",
    "title": "3D Gaussian Splatting for Real-Time Radiance Field Rendering"
  }
}
```

本质上：

```text
human_written_ref
=
“人工 Survey 引用了哪些 arXiv papers”
```

它**不是人工 Survey 正文**。

例如 3DGS 文件实际上就是几十/上百篇 reference 的映射。

---

# 5.2 重要限制

因此现有 Hugging Face 数据：

**没有提供足够的信息直接完成：**

```text
D3 Coverage Gold Rubric
D4 Human-level Synthesis Reference
D5 Human Outline Reference
D6 Topic Quiz
```

因为没有人工综述正文。

---

# 5.3 数据异常

RAG 的 human reference 当前仓库中存在：

```text
Retrieval-augmented generation for large language models
```

但该文件为：

```text
0 Bytes
```

因此构造脚本必须有：

```text
missing / empty file validation
```

不能假定原始数据完整。

---

# 6. generated_surveys_ref

目录格式：

```text
generated_surveys_ref/
└── 3D Gaussian Splatting/
    └── exp_1/
        └── ref.json
```

---

# 6.1 格式

```json
{
  "2308.04079": {
    "arxivId": "2308.04079"
  },

  "2310.08528": {
    "arxivId": "2310.08528"
  }
}
```

这部分只是 SurveyForge 某次生成结果使用过的 reference。

---

# 6.2 对我们的用途

这部分：

**不应该作为 Hy-Survey-Agent 的 Gold Data。**

可选用途只有：

```text
SurveyForge baseline reference statistics
```

例如后续比较：

```text
Hy-Survey-Agent
vs
SurveyForge
```

时计算 reference pool overlap。

所以第一版 Dataset Builder 可以：

```text
默认忽略 generated_surveys_ref/
```

---

# 7. 原始 test.py 的作用

原仓库提供：

```text
test.py
```

用于 Citation Coverage Evaluation。

核心操作为：

```text
Generated/Human References
        ↓
Normalize arXiv ID
        ↓
Benchmark Reference Pool
        ↓
Set Intersection
```

但它计算：

```python
matched_paper_ids = valid_target_ids.intersection(
    benchmark_paper_dates.keys()
)

coverage_ratio =
    len(matched_paper_ids)
    /
    len(valid_target_ids)
```

因此其所谓：

```text
Citation Coverage
```

实际上更接近：

```text
Reference Pool Precision
```

即：

> 目标 Survey 引用的论文中，有多少属于 benchmark reference pool。

它不是：

$$
\frac{
Survey覆盖的Gold Papers
}{
Gold Papers
}
$$

因此不能直接作为我们的：

```text
D2 Citation Recall
```

也不能作为：

```text
D3 Information Coverage
```

---

# 8. 原始数据能够直接提供什么

总结如下：

| 信息                             | 原数据是否提供     |
| ------------------------------ | ----------- |
| Topic                          | ✅           |
| Topic Candidate Papers         | ✅           |
| arXiv ID                       | ✅           |
| Paper Title                    | ✅           |
| Human Survey Reference Set     | ✅ 大部分 topic |
| Generated Survey Reference Set | ✅           |
| Human Survey Text              | ❌           |
| Paper Abstract                 | ❌           |
| Paper Full Text                | ❌           |
| Paper Evidence Passages        | ❌           |
| Gold Key Information Units     | ❌           |
| Gold Taxonomy                  | ❌           |
| Quiz                           | ❌           |
| Reference Answer               | ❌           |
| Claim-level Evidence           | ❌           |

所以整个 Dataset Construction 的本质就是：

> **把一个 reference benchmark 扩展为 evidence-grounded survey benchmark。**

---

# 9. Hy-Survey-Agent 所需评测集

建议最终采用：

```text
dataset/
│
├── manifest.json
│
├── topics/
│   ├── 3d_gaussian_splatting.json
│   ├── vision_transformers.json
│   └── ...
│
├── papers/
│   ├── metadata/
│   ├── abstracts/
│   └── fulltext/
│
├── quizzes/
│
├── rubrics/
│
└── human_surveys/
```

不要把所有东西塞到一个 JSON。

原因是：

* paper full text 很大；
* 多个 topic 可能共享论文；
* Eval 时无需重复加载；
* 以后方便升级 Quiz / Rubric；
* dataset versioning 更容易。

---

# 10. manifest.json

顶层：

```json
{
  "dataset_name": "HySurveyBench",
  "version": "1.0",
  "source": "InternScience/SurveyBench",
  "num_topics": 10,

  "eval_protocol": "Hy-Survey-Agent Eval Protocol v2.0",

  "topics": [
    "3d_gaussian_splatting",
    "vision_transformers"
  ]
}
```

主要负责：

```text
dataset identity
+
version
+
topic index
```

---

# 11. Topic Schema

这是最核心的数据文件。

例如：

```text
topics/3d_gaussian_splatting.json
```

建议格式：

```json
{
  "id": "3d_gaussian_splatting",

  "topic": "3D Gaussian Splatting",

  "query": "Write a comprehensive academic survey on 3D Gaussian Splatting.",

  "domain": [
    "computer_vision",
    "3d_vision"
  ],

  "source": {
    "dataset": "InternScience/SurveyBench",
    "benchmark_file":
      "3D Gaussian Splatting_bench.json",

    "human_reference_file":
      "A Survey on 3D Gaussian Splatting.json"
  },

  "benchmark_pool": [
    "2308.04079",
    "2310.08528"
  ],

  "human_reference_set": [
    "2308.04079"
  ],

  "gold_papers": [
    "2308.04079",
    "2310.08528"
  ],

  "key_information_units": [
    "3dgs_definition",
    "gaussian_representation",
    "differentiable_splatting",
    "optimization",
    "dynamic_gs"
  ],

  "quiz_file":
    "../quizzes/3d_gaussian_splatting.json",

  "rubric_file":
    "../rubrics/3d_gaussian_splatting.json"
}
```

---

# 12. 三类 Paper Set 必须区分

尤其不要把下面三者混到一起。

## benchmark_pool

```text
SurveyBench 提供的大规模 candidate set
```

例如：

```text
330 papers
```

---

## human_reference_set

```text
原人工综述实际引用的 papers
```

---

## gold_papers

```text
我们最终确认：
确实属于评价该 topic 所需的重要文献
```

关系大致为：

```text
benchmark_pool
        │
        ├──────────────┐
        ↓              ↓
human_reference     topic relevance
        │              │
        └──────┬───────┘
               ↓
          Gold Papers
```

---

# 13. Gold Paper Construction

不建议：

```text
gold_papers = human_reference_set
```

因为人工 Survey：

* 也可能漏论文；
* 也可能引用大量 background papers；
* 可能已经过时。

建议采用：

```text
Candidate Pool
    =
benchmark_pool
    ∪
human_reference_set
```

然后进行自动筛选。

---

# 13.1 Paper Relevance Judge

对于每篇 paper：

输入：

```text
topic
paper title
paper abstract
```

判断：

```text
CORE
RELEVANT
BACKGROUND
IRRELEVANT
```

定义：

### CORE

论文直接研究该主题中的重要方法 / 任务 / 问题。

### RELEVANT

直接属于该研究领域，但不是核心工作。

### BACKGROUND

综述可能需要引用的前置知识。

### IRRELEVANT

主题相关性不足。

---

# 13.2 Gold Set

建议：

```text
gold_papers
=
CORE
+
selected RELEVANT
```

而：

```text
BACKGROUND
```

保存，但不计入 Gold Coverage denominator。

---

# 14. Paper Metadata Schema

建议：

```text
papers/metadata/2308.04079.json
```

```json
{
  "paper_id": "2308.04079",

  "arxiv_id": "2308.04079",

  "title":
    "3D Gaussian Splatting for Real-Time Radiance Field Rendering",

  "authors": [],

  "abstract": "...",

  "year": 2023,

  "venue": null,

  "doi": null,

  "url": "...",

  "citation_count": null,

  "topics": [
    "3d_gaussian_splatting"
  ]
}
```

---

# 15. Paper Evidence

这是我们相比原 SurveyBench 最重要的数据增强之一。

D1 和 D2 要求 Judge 判断：

```text
Claim
        ↕
Original Paper Evidence
```

因此必须能够访问论文内容。

建议：

```text
papers/fulltext/{paper_id}.json
```

格式：

```json
{
  "paper_id": "2308.04079",

  "sections": [
    {
      "section_id": "sec_1",
      "title": "Introduction",
      "text": "..."
    },

    {
      "section_id": "sec_3_1",
      "title": "3D Gaussian Representation",
      "text": "..."
    }
  ]
}
```

---

# 15.1 不建议预先制作 Claim Evidence

不要提前人为制作：

```text
claim → evidence
```

因为我们不知道 Agent 最终会生成什么 claim。

正确流程是 Eval runtime 动态进行：

```text
Generated Claim
      ↓
Evidence Retriever
      ↓
Gold Paper Corpus
      ↓
Top-k Passages
      ↓
Evidence Judge
```

因此 dataset 只需要提供：

```text
searchable paper corpus
```

---

# 16. Coverage Rubric / Key Information Units

用于：

```text
D3 Information Coverage
```

建议：

```text
rubrics/3d_gaussian_splatting.json
```

格式：

```json
{
  "topic":
    "3D Gaussian Splatting",

  "units": [
    {
      "id":
        "3dgs_definition",

      "name":
        "3DGS definition and motivation",

      "description":
        "Explain what 3D Gaussian Splatting is and the problem it addresses.",

      "importance": 2,

      "source_papers": [
        "2308.04079"
      ]
    },

    {
      "id":
        "gaussian_representation",

      "name":
        "Gaussian scene representation",

      "description":
        "Explain position, covariance, opacity and appearance representation.",

      "importance": 2,

      "source_papers": [
        "2308.04079"
      ]
    }
  ]
}
```

---

# 17. Key Information Unit Construction

推荐：

```text
Human Survey References
        +
Gold Paper Abstracts
        +
Representative Paper Sections
        ↓
LLM candidate KIU generation
        ↓
Merge duplicate units
        ↓
Importance scoring
        ↓
Evidence grounding
        ↓
Human review
```

---

# 17.1 KIU 要求

每一个 KIU 必须：

1. 可独立理解；
2. 可在 Survey 中明确判断是否出现；
3. 不与其他 KIU 重复；
4. 有 paper evidence；
5. 对理解 topic 有实际意义。

不要生成：

```text
Discuss important research.
```

这样的 rubric。

应该生成：

```text
Explain the explicit 3D Gaussian representation
including position, covariance, opacity and appearance.
```

---

# 18. Quiz Schema

建议：

```text
quizzes/3d_gaussian_splatting.json
```

```json
{
  "topic": "3D Gaussian Splatting",

  "questions": [
    {
      "id": "3dgs_q001",

      "type": "concept",

      "difficulty": "easy",

      "question":
        "How does 3D Gaussian Splatting represent a scene?",

      "reference_answer":
        "...",

      "source_papers": [
        "2308.04079"
      ],

      "evidence": [
        {
          "paper_id": "2308.04079",
          "section_id": "sec_3"
        }
      ]
    },

    {
      "id": "3dgs_q002",

      "type": "method_comparison",

      "difficulty": "medium",

      "question":
        "How does 3DGS differ from NeRF in scene representation and rendering?",

      "reference_answer":
        "...",

      "source_papers": [
        "2308.04079"
      ],

      "evidence": []
    }
  ]
}
```

---

# 19. Quiz Categories

基于我们的 Eval Protocol v2.0：

```text
Concept / Background
Taxonomy
Historical Evolution
Algorithm Principle
Method Comparison
Performance / Benchmark
Application
Limitations
Research Gap
Future Direction
```

建议每个 topic：

```text
15–25 questions
```

第一版建议：

```text
20 questions / topic
```

10 topics：

```text
≈ 200 quiz questions
```

已经足够形成一个有意义的 benchmark。

---

# 20. 推荐难度比例

建议：

```text
Easy    25%
Medium  50%
Hard    25%
```

即每 topic 20 题：

```text
5 Easy
10 Medium
5 Hard
```

避免大量定义题让简单 LLM 也拿到很高分。

---

# 21. Quiz Construction Pipeline

不要只让 LLM：

```text
Generate 20 questions about 3DGS.
```

这样会大量产生参数知识即可回答的问题。

正确流程：

```text
Gold Papers
      ↓
Select Evidence Passages
      ↓
Generate Question
      ↓
Generate Reference Answer
      ↓
Answerability Validation
      ↓
Evidence Validation
      ↓
Difficulty Classification
      ↓
Deduplication
      ↓
Human Sampling Review
```

---

# 22. Quiz Validation

每道 quiz 至少过三层。

## Q1. Answerability

只给：

```text
question
+
gold evidence
```

Judge 能否稳定回答？

不能：

```text
reject
```

---

## Q2. Evidence Requirement

不给 evidence，仅靠非常普通知识就能回答：

不一定删除，

但最多只能属于：

```text
Easy / General
```

Topic-specific quiz 应优先保留真正依赖 literature 的问题。

---

## Q3. Ambiguity

让两个 Judge 独立回答。

如果答案存在明显分歧：

```text
reject / manual review
```

---

# 23. Human Survey 正文

虽然 InternScience HF repo 没有 human survey text，

**建议 Dataset Builder 尝试通过对应 Survey Title / arXiv ID 获取原论文正文。**

这部分建议单独保存：

```text
human_surveys/
└── 3d_gaussian_splatting.md
```

作用：

```text
D3 rubric construction

D5 outline reference

D6 quiz construction

human-vs-agent experiments
```

但需要注意：

> Human Survey 是 benchmark construction source，不是唯一 Gold Answer。

---

# 24. 最终完整 Case Schema

从 Evaluator 角度，一个 topic 可以抽象为：

```json
{
  "id":
    "3d_gaussian_splatting",

  "query":
    "Write a comprehensive academic survey on 3D Gaussian Splatting.",

  "benchmark_pool": [],

  "human_reference_set": [],

  "gold_papers": [],

  "background_papers": [],

  "rubric": {
    "key_information_units": []
  },

  "quiz": {
    "general": [],
    "topic_specific": []
  },

  "human_reference": {
    "available": true,
    "path":
      "human_surveys/3d_gaussian_splatting.md"
  }
}
```

---

# 25. 推荐 Dataset Builder 工程结构

```text
scripts/
└── build_eval_dataset/
    │
    ├── build.py
    │
    ├── config.py
    │
    ├── ingest_surveybench.py
    │
    ├── normalize_refs.py
    │
    ├── fetch_metadata.py
    │
    ├── fetch_papers.py
    │
    ├── select_gold_papers.py
    │
    ├── build_rubrics.py
    │
    ├── build_quizzes.py
    │
    ├── validate_quizzes.py
    │
    ├── validate_dataset.py
    │
    └── utils/
```

---

# 26. Step 1 — ingest_surveybench.py

负责读取：

```text
topics.txt
ref_bench/
human_written_ref/
```

输出 intermediate：

```text
build/intermediate/topics.json
```

---

## 26.1 输出

```json
{
  "3D Gaussian Splatting": {
    "benchmark_refs": [],
    "human_refs": []
  }
}
```

此阶段：

> **不要调用 LLM。**

只做 deterministic ingestion。

---

# 27. Step 2 — normalize_refs.py

必须统一 arXiv ID。

例如：

```text
2308.04079v1
2308.04079v2
2308.04079
```

统一：

```text
2308.04079
```

同时：

* 去重；
* 去空格；
* 检查 ID regex；
* title normalization；
* 检测重复 title 不同 ID；
* 检测 malformed records。

---

# 28. Step 3 — fetch_metadata.py

原数据只有：

```text
arxivId
title
```

需要扩充：

```text
authors
abstract
year
published_date
categories
DOI
venue
citation count
```

推荐优先使用：

```text
arXiv
+
Semantic Scholar
```

或者你们已经接入的学术搜索服务。

---

# 28.1 Cache

必须缓存：

```text
cache/paper_metadata/{arxiv_id}.json
```

否则：

```text
10 topics
×
数百 papers
```

会产生大量重复 API 请求。

---

# 29. Step 4 — fetch_papers.py

建议至少为：

```text
gold candidate papers
```

保存：

```text
title
abstract
sections
```

没有必要第一天就下载：

```text
10 topics × 600 papers
```

全部 PDF full text。

更合理的两阶段方案：

```text
Phase 1
所有 papers → metadata + abstract

Phase 2
筛出的 Gold Papers → full text
```

这样成本低很多。

---

# 30. Step 5 — select_gold_papers.py

输入：

```text
topic
+
paper title
+
abstract
+
human_reference flag
```

输出：

```json
{
  "paper_id": "...",

  "relevance": "CORE",

  "relevance_score": 4,

  "human_reference": true,

  "reason": "..."
}
```

推荐 4 级：

```text
3 CORE
2 RELEVANT
1 BACKGROUND
0 IRRELEVANT
```

---

# 30.1 控制 Gold Set 大小

不建议一个 topic 仍有：

```text
500 gold papers
```

那基本无法用于 Evidence Evaluation。

建议：

```text
30–80 Gold Papers / Topic
```

第一版推荐：

```text
≈50/topic
```

总计约：

```text
500 Gold Papers
```

既有覆盖，又可控。

---

# 31. Gold Paper Sampling Strategy

为了避免全部集中在最热门方法：

可以先让 LLM / embedding 对 candidate papers 分主题：

例如 3DGS：

```text
Fundamentals
Rendering
Optimization
Dynamic GS
Geometry
Compression
Generation
SLAM
Semantic GS
Human Avatar
Large-scale Scene
```

然后：

```text
每个 cluster
选择 representative papers
```

比单纯 Top Citation 更合理。

---

# 32. Step 6 — build_rubrics.py

利用：

```text
Topic
+
Gold Paper abstracts
+
Human Survey
```

生成：

```text
10–20 KIUs / topic
```

每个必须包含：

```text
description
importance
source_papers
```

然后进行：

```text
semantic deduplication
```

---

# 33. Step 7 — build_quizzes.py

推荐分两套：

```text
general quiz
+
topic-specific quiz
```

General Quiz 可以模板化。

Topic Quiz 必须：

```text
evidence-grounded
```

不能凭 LLM 参数知识凭空生成。

---

# 34. Step 8 — validate_quizzes.py

至少做：

```text
answerability check
evidence support check
duplicate check
difficulty check
ambiguity check
```

最终只保留通过全部检查的题目。

---

# 35. Step 9 — validate_dataset.py

Dataset build 完成之后必须做 deterministic validation。

---

## Structural Validation

检查：

```text
10 topics 是否全部存在
```

---

## Paper Validation

```text
gold_paper ID
必须出现在 paper metadata store
```

---

## KIU Validation

每个 KIU：

```text
至少一个 source_paper
```

---

## Quiz Validation

每道 topic-specific quiz：

```text
question != empty
reference_answer != empty
source_papers != empty
```

---

## Path Validation

所有：

```text
quiz_file
rubric_file
paper files
human survey path
```

必须存在。

---

# 36. Pipeline 应支持 Resume

Dataset 构造涉及大量 API / LLM 调用。

因此：

```text
python build.py
```

不应该每次从头运行。

每个 stage 应产生中间结果：

```text
01_ingested/
02_metadata/
03_classified/
04_gold/
05_papers/
06_rubrics/
07_quizzes/
08_final/
```

再次执行：

```text
skip existing valid artifacts
```

---

# 37. 所有 LLM Build Step 必须记录 Provenance

例如 KIU：

```json
{
  "id": "...",

  "generated_by": {
    "model": "...",
    "prompt_version": "rubric-v1",
    "timestamp": "..."
  }
}
```

Quiz 同样。

这是因为未来我们可能：

```text
修改 prompt
重新生成 benchmark
```

必须能够判断：

> v1 和 v2 的区别来自哪里。

---

# 38. Dataset Construction 与 Eval Runtime 分离

这是工程上非常重要的原则。

不要在：

```text
run_eval.py
```

中临时：

* 构造 Gold Set；
* 生成 Quiz；
* 生成 Rubric。

否则：

```text
Model A
Model B
```

可能面对不同 Judge 生成的数据。

必须：

```text
BUILD ONCE
      ↓
Freeze Dataset v1.0
      ↓
Evaluate All Models
```

---

# 39. Dataset 构造阶段允许 LLM

```text
Gold Paper relevance classification

KIU generation

Quiz generation

Quiz validation
```

---

# 40. Evaluation 阶段禁止修改 Gold Data

运行：

```text
Hy-SurveyAgent
Baseline
Search + LLM
Direct LLM
```

时必须全部使用相同：

```text
dataset/v1.0/
```

---

# 41. Dataset Versioning

推荐：

```text
datasets/
├── hysurveybench_v0.1/
├── hysurveybench_v0.2/
└── hysurveybench_v1.0/
```

其中：

## v0.1

```text
10 Topics
+
Reference pools
+
Metadata
```

---

## v0.2

加入：

```text
Gold Papers
+
Paper Corpus
```

---

## v0.3

加入：

```text
KIUs
+
Quiz
```

---

## v1.0

经过：

```text
validation
+
人工抽样检查
+
freeze
```

之后正式用于实验。

---

# 42. 推荐构建顺序

整个数据集构造建议分成下面 7 步：

```text
STEP 1
下载 InternScience/SurveyBench

        ↓

STEP 2
解析 10 Topics
Benchmark Pool
Human References

        ↓

STEP 3
补全 Paper Metadata / Abstract

        ↓

STEP 4
筛选并冻结 Gold Papers

        ↓

STEP 5
获取 Gold Paper Full Text

        ↓

STEP 6
生成 + 验证 KIUs

        ↓

STEP 7
生成 + 验证 Quiz

        ↓

HySurveyBench v1.0
```

---

# 43. 第一阶段建议不要做得过重

一个很容易出现的问题是：

> 一开始就试图把所有 6000+ papers 的 PDF 全下载、解析、向量化。

没有必要。

推荐：

```text
SurveyBench
约 6000 candidate references
        ↓
metadata / abstract
        ↓
relevance filtering
        ↓
约 500 Gold Papers
        ↓
full-text processing
```

数量直接下降一个数量级。

---

# 44. 与 Eval Protocol 的映射

最终 Dataset 的不同字段服务于不同指标：

| Dataset Component      | Eval    |
| ---------------------- | ------- |
| Paper Full Text        | D1      |
| Gold Paper Evidence    | D1      |
| Paper Metadata         | D2      |
| Original Paper Content | D2      |
| KIUs                   | D3      |
| Gold Papers            | D3 / D7 |
| Survey Text            | D4 / D5 |
| Quiz                   | D6      |
| Terminology Evidence   | D7      |
| Topic Metadata         | D8      |

因此：

```text
Gold Papers
+
Paper Corpus
+
KIUs
+
Quiz
```

是整个 HySurveyBench 最核心的四类资产。

---

# 45. 最终推荐目录

```text
hysurveybench_v1/
│
├── manifest.json
│
├── topics.json
│
├── topics/
│   ├── 3d_gaussian_splatting.json
│   ├── vision_transformers.json
│   └── ...
│
├── papers/
│   ├── metadata/
│   │   └── {paper_id}.json
│   │
│   └── fulltext/
│       └── {paper_id}.json
│
├── human_surveys/
│   └── {topic}.md
│
├── rubrics/
│   └── {topic}.json
│
├── quizzes/
│   └── {topic}.json
│
└── provenance/
    ├── build_config.json
    ├── models.json
    └── prompts/
```

---

# 46. 推荐 Builder CLI

最终建议实现：

```bash
python build.py ingest
```

```bash
python build.py metadata
```

```bash
python build.py select-papers
```

```bash
python build.py fetch-fulltext
```

```bash
python build.py build-rubrics
```

```bash
python build.py build-quizzes
```

```bash
python build.py validate
```

或者：

```bash
python build.py all
```

完整构造。

---

# 47. 第一版开发优先级

## P0 — 必须

```text
SurveyBench ingestion
arXiv ID normalization
metadata enrichment
Gold Paper selection
paper evidence corpus
KIU generation
Quiz generation
dataset validation
```

---

## P1 — 建议

```text
human survey acquisition
Semantic Scholar metadata
citation count
topic clustering
multi-judge quiz validation
```

---

## P2 — 可以以后补

```text
venue quality
figure/table annotations
citation graph
manual annotation UI
advanced taxonomy annotation
```

---

# 48. 最终方案

我们不应该把：

```text
InternScience/SurveyBench
```

直接视为最终 Eval Dataset。

更准确的关系是：

```text
InternScience/SurveyBench
           │
           │ supplies
           ↓
Topic + Candidate Literature Pool
           │
           ↓
Metadata Enrichment
           │
           ↓
Gold Literature Selection
           │
       ┌───┴───────────┐
       ↓               ↓
Paper Evidence      Human Survey
       │               │
       ├───────┬───────┤
       ↓       ↓       ↓
      KIUs    Quiz   Reference Structure
       │       │
       └───┬───┘
           ↓
     HySurveyBench v1.0
           ↓
    Hy-SurveyAgent Eval
```

最终的数据集定位为：

> **HySurveyBench 是在 SurveyBench reference pool 基础上构造的、面向 evidence-grounded academic survey generation 的细粒度评测集。**

它与原 SurveyBench 最大的区别不是增加更多 topic，而是增加：

```text
Gold Evidence
+
Structured Coverage Rubrics
+
Reader-oriented Quizzes
```

从而真正支持：

```text
事实
+
引用
+
覆盖
+
综合
+
读者价值
```

五类核心 Survey 能力的评估。
