# Prompt 规范

## 1. 存放位置与文件清单

```text
app/prompts/
├── task_analyzer.md
├── paper_reader.md
├── organizer.md
├── planner.md
├── writer.md
└── citation_verifier.md
```

规则：

- Prompt 一律外置为 `.md`，**禁止写死在 Python 代码里**。
- 一个 Agent 对应一个 Prompt 文件；需要多轮调用的 Agent 可在同一文件内用 `##` 分节（如 `## extraction`、`## retry`）。
- Prompt 通过 `app/prompts/loader.py`（或 `app/core/prompt_registry.py`）统一加载、渲染变量并缓存，禁止各 Agent 各自 `open()`。
- Prompt 文件头必须包含版本注释，修改后递增版本；运行日志 `meta.json` 记录每个 Prompt 的版本与内容 hash，用于复现。

## 2. 六段式结构（每个 Prompt 必含）

```text
Role
Input Schema
Output Schema
Rules
Few-shot Examples
Failure Constraints
```

| 段 | 要求 |
|---|---|
| Role | 一句话定义角色与唯一职责，并写明"不负责什么" |
| Input Schema | 列出渲染变量与类型，说明允许省略的字段 |
| Output Schema | 给出**精确 JSON 模板**（字段名、类型、枚举值），声明只输出 JSON |
| Rules | 逐条编号的硬性约束，使用"必须 / 禁止"，禁止使用"较好 / 尽量 / 尽可能"等模糊表述 |
| Few-shot Examples | 至少 1 个正例 + 1 个反例，反例说明为何违反规则 |
| Failure Constraints | 信息不足、格式冲突、超长输入、无关输入时的处理方式（返回空数组 / `null` / 固定枚举），禁止编造 |

## 3. 强制结构化输出

所有 Agent 输出必须是 JSON（Writer 输出 Markdown 正文时，另行输出结构化 Claim/Citation 部分）。

Prompt 中统一使用如下表述（可本地化，但语义不可弱化）：

```text
只输出一个 JSON 对象，不要输出任何解释性文字、Markdown 代码块标记或额外说明。
若某项信息在输入中不存在，返回空字符串 "" 或空数组 []，禁止推测或编造。
```

各 Agent 输出形状（完整字段见 `data-contracts.md`）：

| Agent | 输出形状 |
|---|---|
| Task Analyzer | `{"subtopics": [], "key_concepts": [], "expected_sections": [], "retrieval_queries": []}` |
| Paper Reader | `{"problem": "", "method": "", "key_idea": "", "advantages": [], "limitations": [], "experiments": [], "claims": []}` |
| Knowledge Organizer | `{"topics": [], "methods": [], "problems": [], "datasets": [], "relations": []}` |
| Outline Planner | `{"sections": []}` |
| Survey Writer | `{"survey_markdown": "", "claims": [], "citations": []}` |
| Citation Verifier | `{"results": [{"claim_id": "", "citation": "", "support": true, "evidence": "", "confidence": 0.0}]}` |

## 4. 各 Prompt 的输入契约速查

| Prompt | 允许注入的 Context | 禁止注入 |
|---|---|---|
| `task_analyzer.md` | Topic、Research Questions、Constraints | 论文内容 |
| `paper_reader.md` | 单篇 Paper 的元信息与正文 | 其它论文、Outline |
| `organizer.md` | `TaskSpec` + `PaperAnalysis[]` | 论文全文 |
| `planner.md` | `TaskSpec` + `KnowledgeBase` | 论文全文 |
| `writer.md` | `TaskSpec` + `Outline` + 本节 Relevant Papers 的证据 | 全部论文全文 |
| `citation_verifier.md` | 单条 Claim + 对应 Paper 的定位证据 | 无关论文、评分标准 |

## 5. 通用禁止事项

- 禁止让模型输出 Source Papers 中不存在的论文、作者、数据集、实验数字。
- 禁止使用"写得更好、更全面、更深入"这类不可判定指令；把"全面"翻译成可操作条款（如"至少覆盖 Outline 中每个 Section 的 purpose"）。
- 禁止在 Prompt 中内嵌 API Key、模型厂商私有参数或环境相关信息。
- 禁止把 Schema 校验逻辑写在 Prompt 里替代代码校验；Prompt 负责约束输出形状，代码负责校验。

## 6. 模板

使用 `assets/templates/prompt_template.md` 作为新 Prompt 的起点，复制后按六段式补齐内容。
