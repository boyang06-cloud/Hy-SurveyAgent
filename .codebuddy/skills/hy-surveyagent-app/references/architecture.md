# Hy-SurveyAgent Application 架构

## 1. Pipeline 总览

```text
Research Topic (+ optional Research Questions / Constraints)
        ↓
  Task Analyzer            → TaskSpec
        ↓
  Literature Manager       → PaperSet（检索 / 去重 / 过滤 / 元数据归一化）
        ↓
  Paper Reader（并行）      → PaperAnalysis[]（每篇一份结构化表示）
        ↓
  Knowledge Organizer      → KnowledgeBase（主题 / 方法 / 问题 / 数据集 / 论文关系）
        ↓
  Outline Planner          → Outline（每个 Section 含 Purpose + Papers + Key Claims）
        ↓
  Survey Writer            → Draft + Claims + CitationMap
        ↓
  Citation Verifier        → Verification（Claim → Citation → Paper → Evidence）
        ↓
  Final Survey + 结构化结果（进入 Evaluation）
```

每一步只消费上一步的必要信息，并产出可落盘的中间结果。

## 2. 模块职责表

| 模块 | 代码位置 | 输入 | 输出 | 明确禁止 |
|---|---|---|---|---|
| Task Analyzer | `app/agents/task_analyzer.py` | Research Topic、Research Questions、Constraints | `TaskSpec`（subtopics / key_concepts / expected_sections / retrieval_queries） | 禁止在此阶段写作 Survey 内容 |
| Literature Manager | `app/retrieval/retriever.py`、`app/retrieval/benchmark_loader.py` | `TaskSpec` | `PaperSet` | Benchmark 模式下禁止实时联网检索覆盖固定论文集 |
| Paper Reader | `app/agents/paper_reader.py` | 单篇 Paper | `PaperAnalysis`（problem/method/key_idea/advantages/limitations/experiments/claims） | 禁止一次把全部论文塞进同一个 Prompt |
| Knowledge Organizer | `app/agents/organizer.py` | `PaperAnalysis[]` | `KnowledgeBase`（topics/methods/papers/relations） | 第一版禁止引入图数据库，用 Python 对象或 JSON |
| Outline Planner | `app/agents/planner.py` | `TaskSpec` + `KnowledgeBase` | `Outline`（sections: title/purpose/papers/key_claims） | 禁止产出无 Purpose、无关联论文的空 Section |
| Survey Writer | `app/agents/writer.py` | `TaskSpec` + `KnowledgeBase` + `Outline` + 相关证据 | `Draft` + `Claims` + `CitationMap` | 禁止发明不存在的论文、引用或实验数字 |
| Citation Verifier | `app/agents/citation_verifier.py` | `Draft` + `PaperSet` | `Verification[]`（claim_id/citation/support/evidence/confidence） | 禁止只做引用格式检查（Grounding 才是重点） |

## 3. 为什么必须分阶段

反例（禁止）：

```text
50 Papers → Huge Prompt → Survey
```

问题：Context 过大、信息组织能力差、难以控制与调试、无法定位信息来源。

正解：

```text
Paper → Structured Representation → Knowledge Base → Planner → Writer
```

收益：责任单一、中间结果可检查、可单独测试、失败可定位、可与 Baseline 对比、便于 Evaluation。

## 4. Context 传递（最小必要）

| Agent | 允许携带的 Context |
|---|---|
| Task Analyzer | Topic + Questions + Constraints |
| Paper Reader | 单篇 Paper 全文/摘要 |
| Knowledge Organizer | `TaskSpec` + `PaperAnalysis[]`（不含全文） |
| Outline Planner | `TaskSpec` + `KnowledgeBase` |
| Survey Writer | `TaskSpec` + `Outline` + 本节 Relevant Papers 的证据（不含全部论文全文） |
| Citation Verifier | 单条 Claim + 被引论文的定位证据 |

实现准则：**按阶段传递最小必要 Context**，不要每个 Agent 都携带完整上下文。

## 5. 并行化

论文阅读是最适合并行的阶段：

```text
                 Paper Reader
              /      |       \
          Paper A  Paper B  Paper C
              \      |       /
               Knowledge Base
```

- 使用 `asyncio.gather(...)` 并发读取，禁止串行 for 循环。
- 用 `asyncio.Semaphore` 限制并发上限（配置项 `runtime.max_concurrency`），避免触发限流。
- 单篇失败不得影响其它论文（见第 6 节）。

## 6. 失败处理

每个 Stage 必须具备：

```text
Input Validation → Timeout → Retry → Fallback → Error Logging
```

Paper Reader 失败示例：

```text
Error → Retry（含 Prompt/解析修正）→ 仍失败 → Mark Paper Unavailable → Continue
```

要求：

- 结构化输出解析失败：重试一次并要求模型只输出 JSON；仍失败则按该 Stage 的 Fallback 处理并记录。
- 单篇论文失败：标记 `unavailable` 并继续，禁止中断整个任务。
- 每个 Stage 记录 `error` 字段到运行日志，不得静默吞异常。

## 7. 推荐目录（Application）

```text
app/
├── core/
│   ├── state.py         # SurveyState
│   ├── types.py         # 数据模型（dataclass / pydantic）
│   └── pipeline.py      # 阶段编排
├── agents/
│   ├── task_analyzer.py
│   ├── paper_reader.py
│   ├── organizer.py
│   ├── planner.py
│   ├── writer.py
│   └── citation_verifier.py
├── retrieval/
│   ├── retriever.py
│   └── benchmark_loader.py
├── model/
│   ├── provider.py      # LLMProvider 抽象
│   └── hy3_adapter.py   # 唯一允许调用 Hy3 SDK 的位置
├── prompts/
│   ├── task_analyzer.md
│   ├── paper_reader.md
│   ├── organizer.md
│   ├── planner.md
│   ├── writer.md
│   └── citation_verifier.md
├── io/
│   ├── loader.py
│   └── exporter.py
└── main.py
```

仓库级结构（含 Evaluation 侧，Application 只关心 `app/` 与 `configs/`、`runs/`）：

```text
Hy-SurveyAgent/
├── app/            configs/        runs/       results/
├── evaluator/      benchmark/      experiments/
├── scripts/        docs/           tests/
├── API_key.conf.example
├── pyproject.toml
└── README.md
```

## 8. 开发顺序（增量，禁止一次性全写）

| Step | 增加内容 | 跑通目标 | 验收 |
|---|---|---|---|
| 1 | Hy3 Adapter + Paper Loader + Simple Writer | `Topic + Papers → Survey` | 能调用 Hy3 产出带引用的草稿 |
| 2 | Paper Reader | `Topic → Paper Analysis → Survey` | 每篇产出合法 `PaperAnalysis`，失败可被标记 |
| 3 | Knowledge Organizer + Outline Planner | 形成真正的 Agent Workflow | `knowledge.json` / `outline.json` 结构合法，Section 有 Purpose 与 Papers |
| 4 | Citation Verifier | Generate + Verify | `verification.json` 给出 support / evidence / confidence |
| 5 | 接入 Evaluation | Application → Evaluation | 输出契约对齐 `data-contracts.md` 的最终输出 |
| 6 | Benchmark Batch Runner | 20 Topics → 20 Runs → Evaluation | 批量运行并记录 latency / cost / score |

## 9. MVP 与 V1 边界

MVP 只做：`Input Topic → 固定 Source Papers → Reader → Organizer → Planner → Writer → Citation Verifier → Final Survey`。

第一版明确不做（避免范围膨胀）：

- Long-term Memory
- Multi-user
- 复杂 Web UI
- 持久化向量库（Persistent Vector DB）
- 多模型自动路由
- 复杂自主循环

V1 再增加：Dynamic Retrieval、Parallel Reading、更强的 Citation Verification、Interactive Review、Evaluation Integration。

## 10. Benchmark Mode 约束

```text
SurveyBench Topic → 固定 Source Papers → Agent
```

禁止：`SurveyBench Topic → 实时搜索 Internet → 随机获得不同论文`。

原因：保证每次实验输入完全一致，结果可复现。

## 11. 与 Evaluation 的边界

- Application 只负责生成，并在最终输出中提供 `task / papers / survey / claims / citations / evidence_map`。
- Evaluation 只消费该结构，Application 不得依赖 Evaluator 的评分逻辑，Evaluator 也不得回写修改 Application 中间状态。
- 这样更换 Evaluator 时无需修改 Agent Pipeline。

## 12. Baseline 接口

为后续对比实验，统一生成器接口：

```python
class SurveyGenerator:
    def generate(self, topic: str, papers: list[Paper]) -> SurveyOutput: ...
```

实现：`SimplePromptGenerator`（单次 Prompt）、`SequentialGenerator`（摘要 → 生成）、`HySurveyAgent`（多阶段 Pipeline）。

三者输出同一 `SurveyOutput` 结构，交给统一 Evaluator。
