# 构造流水线 Step 1–9

## 通用约定

- CLI：`python build.py <step>` 或 `python build.py all`；配置项来自 `config.py` / `build_config.yaml`。
- **每个 step 落盘到编号目录，重跑时跳过已存在的有效产物**：

```text
build/
├── 01_ingested/    topics.json
├── 02_normalized/  topics.json + normalize_report.json
├── 03_metadata/    papers_metadata.json + fetch_report.json
├── 04_classified/  relevance/{topic_id}.json
├── 05_gold/        gold/{topic_id}.json
├── 06_papers/      fulltext/{paper_id}.json
├── 07_rubrics/     {topic_id}.json
├── 08_quizzes/     {topic_id}.json + validation_report.json
└── 09_final/       datasets/hysurveybench_vX.Y/
```

- 涉及 API/LLM 的 step 必须：缓存（metadata）或 Provenance（KUI/Quiz）、限流、指数退避重试、单条失败不中断。
- 每个 step 结束写一份 report（成功/失败/跳过计数），`validate` 阶段统一检查。

---

## Step 1 — ingest_surveybench.py

- 输入：`topics.txt`、`ref_bench/`、`human_written_ref/`。
- 输出：`build/01_ingested/topics.json`，形如 `{"3D Gaussian Splatting": {"benchmark_refs": [], "human_refs": []}}`。
- **不调用 LLM**，纯 deterministic ingestion。
- 校验：文件缺失 / 0 字节（RAG 的 human ref）→ 记 `warning` 并置空，不抛异常中断。
- 默认忽略 `generated_surveys_ref/`。

## Step 2 — normalize_refs.py

- 统一 arXiv ID：`2308.04079v1` / `2308.04079v2` → `2308.04079`（去版本、去空格、正则校验 `^\d{4}\.\d{4,5}$` 与旧式 `cs/0701001`）。
- 去重（同 ID 合并，保留最完整记录）；title 归一化（去多余空白/大小写折叠）用于重复检测。
- 检测：重复 title 不同 ID、malformed 记录、空 title。
- 可直接复用 `scripts/normalize_arxiv_ids.py`。

## Step 3 — fetch_metadata.py

- 补全 `authors / abstract / year / published_date / categories / DOI / venue / citation_count`。
- 优先 arXiv，其次 Semantic Scholar（或已接入的学术搜索服务）。
- **必须缓存** `cache/paper_metadata/{arxiv_id}.json`，否则 10 topics × 数百 papers 会产生大量重复请求。
- 限制并发 + 退避重试；失败的 ID 写入 report，不阻塞。

## Step 4 — select_gold_papers.py

- 输入：`topic + title + abstract + human_reference flag`。
- LLM 判定四级：`CORE(3) / RELEVANT(2) / BACKGROUND(1) / IRRELEVANT(0)`。
- 输出：

```json
{ "paper_id": "...", "relevance": "CORE", "relevance_score": 3,
  "human_reference": true, "reason": "..." }
```

- Gold Set = `CORE + selected RELEVANT`；`BACKGROUND` 保存但不计入 Coverage 分母。
- 控制规模：**30–80 / topic，第一版 ≈ 50**（总计约 500），否则无法做 Evidence Evaluation。
- 采样策略：先按主题聚类（如 Fundamentals / Rendering / Optimization / Dynamic GS / Compression / SLAM …），再每簇选代表论文；比单纯 Top Citation 更合理。

## Step 5 — fetch_papers.py

- 两阶段，禁止第一天就下载全部 6000 篇 PDF：

```text
Phase 1  所有 papers → metadata + abstract
Phase 2  筛出的 Gold Papers → full text
```

- 输出 `papers/fulltext/{paper_id}.json`：`{paper_id, sections:[{section_id,title,text}]}`。
- 全文获取失败时降级为 abstract-only，并在 report 标注（不得静默丢弃）。

## Step 6 — build_rubrics.py

```text
Topic + Gold Paper abstracts + Human Survey
      ↓ LLM 候选 KIU 生成（10–20 / topic）
      ↓ 语义去重
      ↓ importance 打分（1–2）
      ↓ evidence grounding（每个 KIU 至少一个 source_paper）
      ↓ 人工复核
```

- 每条 KIU 必须含 `description / importance / source_papers`。
- 过滤空泛条目（如 "Discuss important research."）。

## Step 7 — build_quizzes.py

- General Quiz：模板化，所有 topic 共用（Easy 概念/分类/历史，Medium 原理/比较/性能/实践，Hard 局限/空白/未来）。
- Topic-specific Quiz：**必须 evidence-grounded**，禁止凭参数知识凭空出题。

```text
Gold Papers → 选证据段落 → 生成问题 → 生成参考答案
      → answerability 校验 → evidence 校验 → 难度分类 → 去重 → 人工抽样复核
```

- 每 topic 15–25 题（第一版 20），难度 25/50/25。

## Step 8 — validate_quizzes.py

每道题至少过三层：

1. **Answerability**：只给 `question + gold evidence`，Judge 能否稳定回答？不能 → reject。
2. **Evidence Requirement**：不给 evidence 靠常识就能回答的，最多只能归为 Easy/General；topic-specific 优先保留依赖文献的问题。
3. **Ambiguity**：两个 Judge 独立回答，明显分歧 → reject / 人工复核。

最终只保留通过全部检查的题目，并输出 `validation_report.json`（reject 原因分布）。

## Step 9 — validate_dataset.py

确定性校验（可直接复用 `scripts/validate_dataset.py`）：

- **Structural**：10 个 topic 是否齐全、manifest 与 topics.json 一致。
- **Paper**：`gold_papers` 每个 ID 必须存在于 metadata store；`background_papers` 同理。
- **KIU**：每个 unit 至少一个 `source_paper`，且该 paper 在 metadata store 中；`importance > 0`。
- **Quiz**：topic-specific 每题 `question / reference_answer / source_papers` 非空；`type` / `difficulty` 取值合法；难度分布落在建议区间（warn）。
- **Path**：`quiz_file` / `rubric_file` / fulltext / human survey 路径均存在。

输出 `ERROR`（必须修）与 `WARN`（人工确认）两级，ERROR 存在时退出码非 0。

---

## 构造阶段允许使用 LLM 的位置

仅四处：Gold Paper 相关性判定、KIU 生成、Quiz 生成、Quiz 验证。
其余全部为确定性逻辑，必须可单测且无需 API Key。

## 完成后

1. `python build.py validate` 无 ERROR；
2. 人工抽样复核（每 topic 抽查 KIU 与 Quiz）；
3. 复制到 `datasets/hysurveybench_vX.Y/` 并写入 `manifest.json` 与 `provenance/`；
4. 冻结：后续评测只读该目录。
