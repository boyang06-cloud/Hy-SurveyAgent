# SurveyBench 原始数据梳理

## 1. 两个同名 SurveyBench（务必区分）

| 项目 | 来源 | 内容 | 本项目用法 |
|---|---|---|---|
| **InternScience/SurveyBench**（arXiv:2503.04629，SurveyForge） | HF `InternScience/SurveyBench` | topics + 大规模 reference pool + 引用集合（**无综述正文**） | **数据基础** |
| OpenDataBox/SurveyBench（arXiv:2510.03120） | 另一项目 | 完整 Markdown survey、human survey、content/outline/quiz/reader-need 评测 | **只借鉴评测思想与 Quiz 数据结构** |

结论：`InternScience/SurveyBench` 提供数据，`OpenDataBox/SurveyBench` 提供思想，不直接照搬任一方。

## 2. 仓库结构（约 1.36 MB）

```text
SurveyBench/
├── generated_surveys_ref/     # SurveyForge 生成综述的引用
├── human_written_ref/         # 人工综述的引用（非正文）
├── ref_bench/                 # 每个 topic 的 candidate reference pool
├── README.md
├── test.py                    # 原 Citation Coverage 评估
└── topics.txt                 # 10 个主题
```

## 3. topics.txt

10 个 CS/AI 主题（第一版全部保留，避免自造 topic 带来主观性）：

```text
3D Gaussian Splatting / 3D Object Detection in Autonomous Driving /
Evaluation of Large Language Models / LLM-based Multi-Agent /
Generative Diffusion Models / Graph Neural Networks /
Hallucination in Large Language Models / Multimodal Large Language Models /
Retrieval-Augmented Generation for Large Language Models / Vision Transformers
```

topic_id 生成规则：小写、空格/连字符转下划线、去掉非字母数字，如 `3D Gaussian Splatting → 3d_gaussian_splatting`。

## 4. ref_bench

```text
ref_bench/3D Gaussian Splatting_bench.json
```

```json
{
  "2308.04079": { "arxivId": "2308.04079", "title": "3D Gaussian Splatting for Real-Time Radiance Field Rendering" },
  "2310.08528": { "arxivId": "2310.08528", "title": "4D Gaussian Splatting for Real-Time Dynamic Scene Rendering" }
}
```

- key = arXiv ID，value = `{arxivId, title}`。
- 池规模：330（3DGS）～ 994（Diffusion），总计约 6000。
- **定位是 Topic-level Reference Candidate Pool，不是必须覆盖的 Gold Paper Set。**
- 池中含大量弱相关论文（3DGS 池里有 NeRF / diffusion / SLAM / 自动驾驶 / robotics / dataset / reconstruction 甚至基础论文），必须筛选。

## 5. human_written_ref

```text
human_written_ref/A Survey on 3D Gaussian Splatting.json
```

格式与 ref_bench 相同，语义是"人工 Survey 引用了哪些 arXiv papers"，**不是人工综述正文**。

已知异常：

- `Retrieval-augmented generation for large language models` 对应文件为 **0 Bytes**；
- 因此构造脚本必须有 missing / empty 校验，不能假定原始数据完整。

## 6. generated_surveys_ref

```text
generated_surveys_ref/3D Gaussian Splatting/exp_1/ref.json
```

```json
{ "2308.04079": { "arxivId": "2308.04079" } }
```

只是 SurveyForge 某次生成用过的 reference。**不应作为 Gold Data**；可选用途是后续与 SurveyForge 做 baseline 对比时计算 reference pool overlap。第一版默认忽略该目录。

## 7. 原始 test.py 的陷阱

```python
matched_paper_ids = valid_target_ids.intersection(benchmark_paper_dates.keys())
coverage_ratio = len(matched_paper_ids) / len(valid_target_ids)
```

这是 **Reference Pool Precision**（目标综述引用的论文有多少落在 pool 里），不是 Coverage，也不是 Citation Recall。**不可直接用作 D2 / D3**。

## 8. 原始数据能直接提供什么

| 信息 | 是否提供 |
|---|---|
| Topic / Candidate Papers / arXiv ID / Title | 是 |
| Human Survey Reference Set（大部分 topic） | 是 |
| Generated Survey Reference Set | 是 |
| Human Survey 正文 / Abstract / Full Text | **否** |
| Gold KIUs / Taxonomy / Quiz / Reference Answer / Claim-level Evidence | **否** |

因此除了 ingestion 之外，其余全部要靠构造流水线补齐：metadata 抓取 → 相关性筛选 → 全文语料 → KIU → Quiz。
