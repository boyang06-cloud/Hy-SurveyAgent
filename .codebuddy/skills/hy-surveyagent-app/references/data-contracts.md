# 数据契约（Data Contracts）

所有跨 Stage 传递的数据必须是**可序列化的结构化对象**（dataclass 或 pydantic model），落盘为 JSON / Markdown。
实现时以本文档字段名为准；确需扩展字段时在 `app/core/types.py` 中集中新增，禁止各模块私自拼接字典。

## 1. 任务输入

```yaml
topic: "Vision-Language Models for Autonomous Driving"

research_questions:
  - "How have VLMs been applied to autonomous driving?"
  - "What are the main methodological categories?"

paper_ids:            # Benchmark 模式下指向固定 Source Paper Set
  - paper_001
  - paper_002

time_range:
  start: 2020
  end: 2026

output_style: "academic_survey"
```

Benchmark 模式下输入简化为：`Topic + 固定 Source Paper Set`。

## 2. TaskSpec（Task Analyzer 输出）

```json
{
  "topic": "...",
  "subtopics": ["..."],
  "key_concepts": ["..."],
  "expected_sections": ["Introduction", "Taxonomy"],
  "retrieval_queries": ["..."]
}
```

## 3. Paper（Literature Manager 输出）

```json
{
  "papers": [
    {
      "paper_id": "P001",
      "title": "...",
      "authors": ["..."],
      "year": 2025,
      "abstract": "...",
      "content": "..."
    }
  ]
}
```

归一化要求：去重（同一工作只保留一条）、过滤（时间范围 / 主题相关性）、元数据补齐（缺失字段置 `null`，禁止编造）。

## 4. PaperAnalysis（Paper Reader 输出，每篇一份）

```json
{
  "paper_id": "P001",
  "problem": "...",
  "motivation": "...",
  "method": "...",
  "architecture": "...",
  "dataset": ["..."],
  "experiments": ["..."],
  "results": ["..."],
  "key_idea": "...",
  "advantages": ["..."],
  "limitations": ["..."],
  "claims": [
    { "claim_id": "P001-C1", "text": "...", "evidence": "..." }
  ],
  "status": "ok"
}
```

- `status`：`ok` | `unavailable`（读取失败时标记，禁止中断整体流程）。
- 抽取内容必须来自论文正文，禁止由模型补齐不存在的信息；无对应内容时返回空字符串或空数组。

## 5. KnowledgeBase（Knowledge Organizer 输出）

```json
{
  "topics": ["..."],
  "methods": [
    { "name": "Transformer-based", "papers": ["P001", "P003"] }
  ],
  "problems": [
    { "name": "...", "papers": ["P002"] }
  ],
  "datasets": [
    { "name": "...", "papers": ["P001"] }
  ],
  "papers": ["P001", "P002"],
  "relations": [
    { "source": "P001", "relation": "extends", "target": "P002" }
  ]
}
```

`relation` 取值：`extends` | `compares` | `solves` | `uses_dataset` | `evaluates_on`。
第一版用 Python 对象 / JSON 表示即可，不引入图数据库。

## 6. Outline（Outline Planner 输出）

```json
{
  "sections": [
    {
      "title": "Method Taxonomy",
      "purpose": "对现有方法按技术路线分类，比较其适用条件",
      "papers": ["P001", "P002", "P003"],
      "key_claims": ["P001-C1", "P003-C2"]
    }
  ]
}
```

每个 Section 必须同时具备 `purpose` + `papers` + `key_claims`，否则视为非法 Outline（约束 Writer，避免无约束写作）。

## 7. Draft / Claim / CitationMap（Survey Writer 输出）

Writer 输出 Markdown 正文 + 结构化 Claim 与引用表。

```json
{
  "claims": [
    { "claim_id": "C001", "text": "Method X improves ...", "citations": ["P001"] }
  ],
  "citation_map": [
    { "citation_id": "[1]", "paper_id": "P001", "title": "...", "source": "..." }
  ]
}
```

约定：

- 正文引用统一使用 `[1]` `[2]` `[3]` 数字编号形式。
- `citation_id` 与正文中的编号一一对应；`citation_map` 是编号 → `paper_id` 的唯一映射。
- Writer 禁止输出未在 `citation_map` 中登记的编号，禁止引用 Source Papers 之外的论文。

## 8. Verification（Citation Verifier 输出）

```json
{
  "verification": {
    "results": [
      {
        "claim_id": "C001",
        "citation": "P001",
        "support": true,
        "evidence": "...",
        "confidence": 0.92
      }
    ],
    "summary": {
      "total_claims": 42,
      "supported": 35,
      "unsupported": 5,
      "unverifiable": 2
    }
  }
}
```

- `support`：`true` | `false` | `null`（证据不足，无法判定）。
- 核验链路：`Claim → Citation → Source Paper → Evidence → 比较`。仅检查 `[1]` 是否存在属于**引用格式化**，不算 Citation Verification。

## 9. SurveyState（统一执行状态）

```python
class SurveyState:
    task_spec: TaskSpec
    papers: list[Paper]
    paper_analyses: list[PaperAnalysis]
    knowledge_base: KnowledgeBase
    outline: Outline
    draft: str
    claims: list[Claim]
    citation_map: list[Citation]
    verification: Verification
    final_survey: str
```

流程形态：`State → Analyzer → State → Reader → State → Organizer → ... → Final`。
每个 Stage 接收 State 中的最小必要字段，写回自己的产物字段。State 必须可整体序列化落盘。

## 10. 最终输出（Evaluation 接口）

```json
{
  "task": { "topic": "...", "research_questions": ["..."] },
  "papers": [
    { "paper_id": "P001", "title": "...", "year": 2025 }
  ],
  "survey": "...markdown 正文...",
  "claims": [
    { "claim_id": "C001", "text": "...", "citations": ["P001"] }
  ],
  "citations": [
    { "citation_id": "[1]", "paper_id": "P001", "title": "...", "source": "..." }
  ],
  "evidence_map": [
    { "claim_id": "C001", "paper_id": "P001", "evidence": "...", "support": true }
  ]
}
```

另附机器可读的合并结果（与上述同源，避免重复维护）：

```json
{
  "survey_markdown": "...",
  "citations": [],
  "source_papers": [],
  "outline": {},
  "claims": [],
  "verification": {}
}
```

Application 与 Evaluation 之间只通过该结构交互。

## 11. 输出 Survey 章节

```text
Introduction / Problem Definition / Taxonomy / Method Comparison /
Research Evolution / Limitations / Open Problems / Future Directions / References
```

## 12. runs/ 产物清单

```text
runs/
└── <task_id>/
    ├── meta.json         # task_id、创建时间、git commit、prompt 版本/hash、运行参数
    ├── task.json         # TaskSpec
    ├── papers.json       # PaperSet
    ├── analyses.json     # PaperAnalysis[]
    ├── knowledge.json    # KnowledgeBase
    ├── outline.json      # Outline
    ├── draft.md          # Writer 草稿
    ├── claims.json       # Claim[] + CitationMap
    ├── verification.json # Verification
    ├── final.md          # 最终 Survey
    ├── result.json       # 第 10 节最终输出
    └── logs/
        └── stages.jsonl  # 每个 Stage 一条日志
```

单条 stage 日志字段：

```json
{
  "task_id": "t-2026-09-03-001",
  "stage": "paper_reader",
  "input_ref": "runs/<task_id>/papers.json",
  "output_ref": "runs/<task_id>/analyses.json",
  "latency_ms": 12345,
  "token_usage": { "prompt": 0, "completion": 0 },
  "error": null,
  "timestamp": "2026-09-03T10:00:00Z"
}
```

## 13. ID 命名约定

| 对象 | 格式 | 示例 |
|---|---|---|
| Paper | `P` + 3 位序号 | `P001` |
| 论文内部 Claim | `<paper_id>-C<n>` | `P001-C1` |
| Survey Claim | `C` + 3 位序号 | `C001` |
| 正文引用编号 | `[n]`（按出现顺序） | `[1]` |
| Task | `t-<date>-<seq>` | `t-2026-09-03-001` |

ID 在整条链路中保持稳定，不得在 Stage 之间重新编号，否则 Claim → Citation → Evidence 追溯链断裂。

## 14. 结构化输出解析约定

- 所有 Agent 必须返回 JSON（Prompt 层强制，见 `prompt-spec.md`）。
- 解析流程：`提取 JSON 块 → json.loads → Schema 校验 → 字段补全`。
- 解析失败：重试一次（附带错误说明，要求只输出合法 JSON）；仍失败则该 Stage 走 Fallback 并记 `error`。
- 禁止把未解析的自由文本直接作为结构化字段传入下一 Stage。
