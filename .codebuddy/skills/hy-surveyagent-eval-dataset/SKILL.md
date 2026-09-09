---
name: hy-surveyagent-eval-dataset
description: 用于搭建 Hy-SurveyAgent 的评测数据集构造脚本（HySurveyBench）。当需要基于 InternScience/SurveyBench 做 ingestion、arXiv ID 规范化、metadata/abstract 与 full text 获取、Gold Paper 筛选、Key Information Unit 与 Quiz 生成及验证、数据集版本冻结与结构校验时，应使用本 skill。它强制执行"构造与评测分离、分阶段落盘可断点续跑、LLM 产物记录 provenance"，禁止在评测运行时临时生成 Gold Set / Rubric / Quiz。
---

# HySurveyBench 评测数据集构造

## 目标

把 **InternScience/SurveyBench**（只提供 Topic + 参考文献池）增强为支持 Eval Protocol v2.0 的结构化评测集：

```text
Topic + Human Reference + Gold Literature + Paper Evidence + KIUs + Quizzes
```

一句话概括本质：**把一个 reference benchmark 扩展为 evidence-grounded survey benchmark**。

## 权威来源

- 数据集构造设计：`eval_dataset/eval_data_construct.md`。冲突时以该文档为准，并回来修订本 skill。
- 评测协议：`eval_harness/eval_protocol.md`（决定数据集需要提供哪些字段，见 `references/dataset-schema.md` 的映射表）。

## 核心原则（不可违反）

1. **构造与评测分离**：`BUILD ONCE → 冻结 dataset vX.Y → 所有模型共用同一版本`。禁止在 `run_eval` 中生成/修改 Gold Set、Rubric、Quiz。
2. **三类 Paper Set 必须区分**：`benchmark_pool`（原始候选池）≠ `human_reference_set`（人工综述引用）≠ `gold_papers`（最终确认的重要文献）。
3. **ref_bench 不是 Gold Set**：reference pool 含大量弱相关甚至无关论文，必须筛选。
4. **分阶段落盘 + 可续跑**：每步产出中间产物（`01_ingested/` … `08_final/`），重跑时跳过已存在的有效产物，禁止每次从头重跑。
5. **LLM 产物必须带 Provenance**：KIU / Quiz / 相关性判定都要记录 `model / prompt_version / timestamp`，便于 v1 与 v2 对比。
6. **确定性步骤不调 LLM**：ingestion、ID 规范化、结构校验必须是纯确定性逻辑，可单测。
7. **不要预先制作 claim→evidence 映射**：只提供可检索的论文语料，证据检索在 eval runtime 动态进行。
8. **不假设原始数据完整**：RAG 的 human reference 文件是 0 字节，脚本必须有 missing / empty 校验。
9. **不要第一天就全量下载 PDF**：先 metadata/abstract，筛出 Gold 后再取 full text（6000+ → 约 500）。
10. **密钥与缓存分离**：API Key 走 `API_key.conf`；metadata 抓取结果缓存到 `cache/paper_metadata/{arxiv_id}.json`。

## 何时使用

- 搭建或重构 `scripts/build_eval_dataset/` 的 build 流水线与各 step 脚本
- 新增/修改数据集 Schema（topic / paper metadata / fulltext / rubric / quiz）
- 调整 Gold Paper 筛选策略、KIU 生成、Quiz 生成与验证
- 数据集版本冻结、结构校验与人工抽样复核
- 排查数据集质量问题（重复 ID、引用不存在论文、Quiz 无证据）

需要实现评分器或 Judge 时，改用 `hy-surveyagent-eval-harness` skill。

## 目标目录

```text
datasets/hysurveybench_v1.0/
├── manifest.json
├── topics.json
├── topics/{topic_id}.json
├── papers/metadata/{paper_id}.json
├── papers/fulltext/{paper_id}.json
├── human_surveys/{topic_id}.md
├── rubrics/{topic_id}.json
├── quizzes/{topic_id}.json
└── provenance/{build_config.json,models.json,prompts/}
```

不要把全部内容塞进一个 JSON：full text 很大、多 topic 共享论文、便于版本化与增量升级。

## 构造流水线（Step 1–9）

```bash
python build.py ingest          # 1  读取 topics.txt / ref_bench / human_written_ref（不调 LLM）
python build.py normalize       # 2  arXiv ID 规范化 + 去重 + 异常检测
python build.py metadata        # 3  补全 metadata + abstract（arXiv / Semantic Scholar，带缓存）
python build.py select-papers   # 4  Gold Paper 筛选（CORE/RELEVANT/BACKGROUND/IRRELEVANT）
python build.py fetch-fulltext  # 5  仅 Gold Papers 取全文并切 section
python build.py build-rubrics   # 6  KIU 生成 + 去重 + importance
python build.py build-quizzes   # 7  General + Topic-specific Quiz
python build.py validate        # 8+9 Quiz 验证 + 数据集结构校验
python build.py all             # 全流程
```

每个 step 的输入/输出、resume 约定、Provenance 与验证项见 `references/build-steps.md`。

## 关键规模建议

| 项 | 建议值 |
|---|---|
| Topics（第一版） | 10 个（沿用 SurveyBench 全部主题） |
| Gold Papers / Topic | 30–80，第一版 ≈ 50 |
| KIUs / Topic | 10–20 |
| Quizzes / Topic | 15–25，第一版 20（Easy 25% / Medium 50% / Hard 25%） |
| Versioning | v0.1 topics+pool → v0.2 +gold/corpus → v0.3 +KIU/Quiz → v1.0 freeze |

## 资源索引

- `references/source-data.md` —— SurveyBench 原始目录与格式、两个同名 SurveyBench 的区别、已知坑（0 字节文件、generated_surveys_ref 不用、test.py 的 coverage 实为 precision）。
- `references/dataset-schema.md` —— manifest / topic / paper metadata / fulltext / rubric / quiz / provenance 的完整 Schema 与字段含义、Dataset→Eval 维度映射。
- `references/build-steps.md` —— Step 1–9 的 CLI、输入、输出、LLM 使用点、resume 与验证清单。
- `scripts/init_builder.py` —— 生成 `scripts/build_eval_dataset/` 骨架（build.py + 各 step 占位 + config + utils）。
- `scripts/normalize_arxiv_ids.py` —— 确定性 arXiv ID 规范化 / 去重 / 重复标题检测（Step 2 的可复用实现）。
- `scripts/validate_dataset.py` —— 数据集结构与引用校验（Step 9 的可复用实现）。
- `assets/templates/` —— 各 Schema 的 JSON 模板与 `build_config.example.yaml`。

## 完成定义

- 10 个 topic 全部产出，且 `python build.py validate` 无 ERROR。
- `gold_papers ⊆ metadata store`，每个 KIU 至少一个 `source_paper`，每道 topic quiz 的 `question / reference_answer / source_papers` 均非空且证据可追溯。
- `manifest.json` 记录 dataset 版本、来源、topic 索引；`provenance/` 记录所有 LLM 生成步骤的 model / prompt_version / timestamp。
- 冻结后所有模型（Hy-SurveyAgent / Baselines）评测均指向同一 `datasets/hysurveybench_vX.Y/`。
