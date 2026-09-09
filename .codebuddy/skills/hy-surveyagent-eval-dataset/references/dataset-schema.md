# HySurveyBench 数据集 Schema

命名约定：`paper_id` 默认等于规范化后的 arXiv ID（如 `2308.04079`）；`topic_id` 为小写下划线形式；`section_id` 形如 `sec_3_1`。

---

## 1. manifest.json

```json
{
  "dataset_name": "HySurveyBench",
  "version": "1.0",
  "source": "InternScience/SurveyBench",
  "num_topics": 10,
  "eval_protocol": "Hy-SurveyAgent Evaluation Protocol v2.0",
  "topics": ["3d_gaussian_splatting", "vision_transformers"]
}
```

职责：dataset identity + version + topic 索引。

## 2. topics/{topic_id}.json

```json
{
  "id": "3d_gaussian_splatting",
  "topic": "3D Gaussian Splatting",
  "query": "Write a comprehensive academic survey on 3D Gaussian Splatting.",
  "domain": ["computer_vision", "3d_vision"],
  "source": {
    "dataset": "InternScience/SurveyBench",
    "benchmark_file": "3D Gaussian Splatting_bench.json",
    "human_reference_file": "A Survey on 3D Gaussian Splatting.json"
  },
  "benchmark_pool": ["2308.04079", "2310.08528"],
  "human_reference_set": ["2308.04079"],
  "gold_papers": ["2308.04079", "2310.08528"],
  "background_papers": [],
  "key_information_units": ["3dgs_definition", "gaussian_representation"],
  "quiz_file": "../quizzes/3d_gaussian_splatting.json",
  "rubric_file": "../rubrics/3d_gaussian_splatting.json",
  "human_reference": {
    "available": true,
    "path": "human_surveys/3d_gaussian_splatting.md"
  }
}
```

字段语义（**三者不可混用**）：

| 字段 | 含义 |
|---|---|
| `benchmark_pool` | SurveyBench 原始候选池（数百篇） |
| `human_reference_set` | 人工综述实际引用 |
| `gold_papers` | 最终确认评价该 topic 所需的重要文献 |
| `background_papers` | 前置知识论文，保留但不计入 Gold Coverage 分母 |

关系：

```text
benchmark_pool ──┬── human_reference_set
                 └── topic relevance
                            ↓
                       Gold Papers
```

## 3. papers/metadata/{paper_id}.json

```json
{
  "paper_id": "2308.04079",
  "arxiv_id": "2308.04079",
  "title": "3D Gaussian Splatting for Real-Time Radiance Field Rendering",
  "authors": [],
  "abstract": "...",
  "year": 2023,
  "venue": null,
  "doi": null,
  "url": "https://arxiv.org/abs/2308.04079",
  "citation_count": null,
  "topics": ["3d_gaussian_splatting"]
}
```

缺字段用 `null` / `[]`，禁止编造。

## 4. papers/fulltext/{paper_id}.json

```json
{
  "paper_id": "2308.04079",
  "sections": [
    { "section_id": "sec_1", "title": "Introduction", "text": "..." },
    { "section_id": "sec_3_1", "title": "3D Gaussian Representation", "text": "..." }
  ]
}
```

- 只保存可检索的 section 文本，不做向量化（eval runtime 自行建索引）。
- **不要预先制作 claim → evidence 映射**：不知道 Agent 会生成什么 claim，证据检索必须在评测时动态进行。

## 5. rubrics/{topic_id}.json

```json
{
  "topic": "3D Gaussian Splatting",
  "units": [
    {
      "id": "3dgs_definition",
      "name": "3DGS definition and motivation",
      "description": "Explain what 3DGS is and the problem it addresses.",
      "importance": 2,
      "source_papers": ["2308.04079"]
    }
  ]
}
```

KIU 五条硬性要求：可独立理解 / 可在 Survey 中明确判断是否出现 / 不与其他 KIU 重复 / 有 paper evidence / 对理解 topic 有实际意义。

禁止出现 `Discuss important research.` 这类空泛条目；应写成
`Explain the explicit 3D Gaussian representation including position, covariance, opacity and appearance.`

## 6. quizzes/{topic_id}.json

```json
{
  "topic": "3D Gaussian Splatting",
  "questions": [
    {
      "id": "3dgs_q001",
      "type": "concept",
      "difficulty": "easy",
      "question": "How does 3D Gaussian Splatting represent a scene?",
      "reference_answer": "...",
      "source_papers": ["2308.04079"],
      "evidence": [{ "paper_id": "2308.04079", "section_id": "sec_3" }]
    }
  ]
}
```

- `type` 取值：`concept / taxonomy / historical_evolution / algorithm_principle / method_comparison / performance_benchmark / application / limitations / research_gap / future_direction`
- `difficulty`：`easy / medium / hard`，建议 25% / 50% / 25%。
- 难度分布（每 topic 20 题建议）：Concept 2、Taxonomy 2、Historical 1、Algorithm 3、Comparison 3、Performance 2、Limitations 2、Gap/Future 2。
- Topic-specific quiz 必须 evidence-grounded：question / reference_answer / source_papers / evidence 齐全，且不能只靠常识回答。

## 7. human_surveys/{topic_id}.md

原 HF 数据没有正文，建议通过 Survey Title / arXiv ID 尝试获取；获取不到则 `human_reference.available = false`。
用途：D3 rubric 构造、D5 outline 参考、D6 quiz 构造、human-vs-agent 实验。
**Human Survey 是构造来源，不是唯一 Gold Answer。**

## 8. provenance/

```text
provenance/
├── build_config.json   # 版本、源数据路径、阈值、模型名
├── models.json         # 各 LLM step 使用的模型
└── prompts/            # 各 step 使用的 Prompt 与版本
```

每个 LLM 生成对象内嵌：

```json
{ "generated_by": { "model": "...", "prompt_version": "rubric-v1", "timestamp": "..." } }
```

## 9. Dataset → Eval 维度映射

| Dataset 组件 | 服务的维度 |
|---|---|
| Paper Full Text / Gold Paper Evidence | D1 |
| Paper Metadata / 原文内容 | D2 |
| KIUs | D3 |
| Gold Papers | D3 / D7 |
| Survey 文本（Human Survey） | D4 / D5 |
| Quiz | D6 |
| Terminology Evidence | D7 |
| Topic Metadata | D8 |

核心四类资产：**Gold Papers + Paper Corpus + KIUs + Quiz**。

## 10. 版本规划

| 版本 | 内容 |
|---|---|
| v0.1 | 10 Topics + Reference pools + Metadata |
| v0.2 | + Gold Papers + Paper Corpus |
| v0.3 | + KIUs + Quiz |
| v1.0 | validation + 人工抽样 + freeze |

冻结后所有模型评测指向同一目录；修订数据必须产出新版本，禁止原地改。
