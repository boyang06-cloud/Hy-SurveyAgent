# AGENTS.md

> 本文件是 AI 编码助手（CodeBuddy 等）在本仓库工作的**首要约定文件**。
> 开始任何开发任务前先读完本文件；本文件与 `docs/` 冲突时，以 `docs/` 中的设计文档为准并回来修订本文件。

---

## 1. 项目简介

**Hy-SurveyAgent**：基于 Hy3 的学术 Survey 生成 Agent Application（犀牛鸟开源实战任务）。

目标：输入一个研究主题与一组论文，自动完成「主题理解 → 文献组织 → 论文阅读 → Survey 规划 → Survey 生成 → 引用核验」，输出结构化、引用可追溯的 Survey，供自定义评测体系消费。

```text
Research Topic
   ↓ Task Analyzer → Literature Manager → Paper Reader（并行）
   ↓ Knowledge Organizer → Outline Planner → Survey Writer → Citation Verifier
Final Survey + Claims + Citations + Evidence Map → Evaluation
```

第一版追求：**可运行、可复现、可解释、可验证、可批量评测**。

---

## 2. 必读文档

| 文档 | 内容 |
|---|---|
| `docs/Hy-SurveyAgent 项目设计文档.md` | 项目全局：场景定义、Phase 0–11、Evaluation 维度、验证实验、里程碑 |
| `docs/Hy-SurveyAgent Application 开发文档.md` | Application 权威设计：Agent 职责、数据契约、目录结构、验收标准 |
| `AGENTS.md`（本文件） | 工程与协作约定 |
| `.codebuddy/skills/hy-surveyagent-app/SKILL.md` | 开发 Application 时应优先加载的 skill |

**Application 侧任务**（新增/修改 Agent、Adapter、Prompt、Pipeline）先加载 skill `hy-surveyagent-app`，再读对应 reference。

---

## 3. 技术栈

| 项 | 约定 |
|---|---|
| 语言 | Python **≥ 3.11**（`.python-version` 固定） |
| 包管理 | **uv**（唯一），禁止 pip / poetry / conda |
| 版本管理 | Git |
| 并发 | `asyncio`（论文阅读并行） |
| 数据模型 | `dataclass`（或 pydantic），全流程类型注解 |
| 配置 | `API_key.conf`（INI，密钥） + `configs/config.yaml`（YAML，运行参数） |
| Lint | `ruff`（format + check）、`mypy` |

---

## 4. 常用命令（uv）

```bash
uv sync                       # 安装/同步依赖（依据 uv.lock）
uv add <pkg>                  # 新增运行时依赖
uv add --dev pytest ruff mypy # 新增开发依赖
uv run python -m app.main     # 运行 Pipeline
uv run pytest                 # 测试
uv run ruff check . && uv run ruff format .
uv lock --upgrade-package <pkg>
uv python pin 3.11            # 固定 Python 版本
```

- `pyproject.toml` 与 `uv.lock` **同时入库**（保证可复现）。
- 所有文档与脚本使用 `uv run`，不要写 `pip install` 或裸 `python app/main.py`。

---

## 5. 配置与密钥（强制）

### 5.1 密钥

1. 仓库只提交模板 `API_key.conf.example`。
2. 首次使用执行：

   ```bash
   cp API_key.conf.example API_key.conf     # 去掉 .example 后缀
   # 编辑 API_key.conf，填入真实 Key
   ```

3. `API_key.conf` 已被 `.gitignore` 忽略，**禁止提交**。
4. 代码只能通过 `app/config.py`（`configparser`）读取该文件；CI 允许用环境变量 `HY3_API_KEY` 覆盖。
5. **禁止**在任何 `.py` / `.yaml` / `.md` / 日志 / 报错信息 / 测试夹具中出现 Key 字面量。
6. 加载失败时报错并提示 `cp API_key.conf.example API_key.conf`，禁止回退到硬编码默认值。

### 5.2 运行参数

```bash
cp configs/config.example.yaml configs/config.yaml
```

- 该文件只放模型名、temperature、并发度、超时重试、路径等非敏感参数，**禁止放密钥**。
- 运行参数需写入 `runs/<task_id>/meta.json`，用于结果复现。

### 5.3 自检

提交前运行：

```bash
uv run python .codebuddy/skills/hy-surveyagent-app/scripts/check_repo.py .
```

出现 `FAIL` 项（密钥被跟踪、疑似硬编码 Key、SDK 未收敛）必须先修复。

---

## 6. 目录结构

```text
Hy-SurveyAgent/
├── app/                      # Application 主体
│   ├── core/                 # state.py / types.py / pipeline.py
│   ├── agents/               # task_analyzer / paper_reader / organizer / planner / writer / citation_verifier
│   ├── retrieval/            # retriever.py / benchmark_loader.py
│   ├── model/                # provider.py（抽象）+ hy3_adapter.py（唯一 SDK 调用点）
│   ├── prompts/              # 六个 .md Prompt 模板
│   ├── io/                   # loader.py / exporter.py
│   └── main.py
├── configs/                  # config.example.yaml（+ 本地 config.yaml，未入库）
├── evaluator/                # 评测体系（独立模块，不在 Application 职责内）
├── benchmark/                # 数据底座：source / references / quizzes / normal / hard / negative / adversarial
├── experiments/              # discrimination / consistency / human_agreement / adversarial
├── runs/                     # 单次运行中间产物（未入库）
├── results/                  # 评测结果（未入库）
├── scripts/                  # run_agent / run_eval / run_validation / prepare_benchmark
├── tests/
├── docs/
├── .codebuddy/skills/hy-surveyagent-app/   # 项目级 skill
├── API_key.conf.example
├── pyproject.toml
├── AGENTS.md
└── README.md
```

---

## 7. 模块职责（Application）

| 模块 | 输入 | 输出 | 禁止 |
|---|---|---|---|
| Task Analyzer | Topic / Questions / Constraints | `TaskSpec` | 在此写作 Survey 内容 |
| Literature Manager | `TaskSpec` | `PaperSet` | Benchmark 模式下联网检索覆盖固定论文集 |
| Paper Reader | 单篇 Paper | `PaperAnalysis` | 一次性把全部论文塞进同一 Prompt |
| Knowledge Organizer | `TaskSpec` + `PaperAnalysis[]` | `KnowledgeBase` | 第一版引入图数据库 |
| Outline Planner | `TaskSpec` + `KnowledgeBase` | `Outline` | 产出无 Purpose / 无论文关联的 Section |
| Survey Writer | `TaskSpec` + `Outline` + 本节证据 | Draft + Claims + CitationMap | 发明不存在的论文、引用、实验数字 |
| Citation Verifier | Draft + `PaperSet` | `Verification` | 只做 `[1]` 格式检查（必须做 Grounding） |

详细 Schema 见 `.codebuddy/skills/hy-surveyagent-app/references/data-contracts.md`。

---

## 8. 编码规范

### 必须

- 全流程类型注解；跨模块数据用 `dataclass`/pydantic 模型，**禁止裸 `dict` 传递**。
- 单一职责：一个 Agent 文件只做一件事；文件 IO 交给 `app/io/`。
- 每个 Stage 具备 `Input Validation → Timeout → Retry → Fallback → Error Logging`。
- 论文阅读用 `asyncio.gather` + `asyncio.Semaphore` 限流；单篇失败标记 `unavailable` 后继续。
- 标识符、文件名用英文；注释与文档用中文。
- 新增 Stage 时同步补：Prompt 文件、数据模型、单元测试、落盘产物。

### 禁止

- 禁止「一个巨大 Prompt 直接生成 Survey」。
- 禁止把 API Key、模型端点硬编码进代码。
- 禁止把 Prompt 写在 Python 代码里（必须放 `app/prompts/*.md`）。
- 禁止在 `app/model/` 之外 import Hy3 / 任何厂商 SDK。
- 禁止每个 Agent 携带完整上下文（按阶段传最小必要 Context）。
- 禁止因单篇论文失败中断整个任务。
- 禁止提交 `API_key.conf`、`configs/config.yaml`、`runs/`、`results/`、`.venv/`。

---

## 9. LLM 调用规范

```python
class LLMProvider:
    def generate(self, messages: list[dict], model: str,
                 temperature: float, max_tokens: int) -> LLMResponse: ...
```

- Hy3 SDK 的 import **只允许出现在 `app/model/hy3_adapter.py`**。
- 所有 Agent 只依赖 `LLMProvider`，不感知具体模型。
- Adapter 内统一处理：客户端初始化、超时、指数退避重试、`token_usage` 统计、错误归一化。
- 目的：替换 Baseline 模型或 Mock Provider 时，Pipeline 零改动。

---

## 10. Prompt 规范

- 位置：`app/prompts/{task_analyzer,paper_reader,organizer,planner,writer,citation_verifier}.md`。
- 每个 Prompt 必含六段：`Role / Input Schema / Output Schema / Rules / Few-shot Examples / Failure Constraints`。
- 强制 JSON 输出；字段缺失返回 `""` 或 `[]`，**禁止编造**。
- Prompt 文件头记录 `version`，修改后递增；`runs/<task_id>/meta.json` 记录各 Prompt 版本与 hash。
- 禁止模糊指令（「尽可能全面」「写得更好」），必须转成可操作条款。
- 模板：`.codebuddy/skills/hy-surveyagent-app/assets/templates/prompt_template.md`。

---

## 11. 运行产物

```text
runs/<task_id>/
├── meta.json         # git commit、python 版本、prompt 版本、运行参数
├── task.json  papers.json  analyses.json  knowledge.json  outline.json
├── draft.md   claims.json   verification.json   final.md   result.json
└── logs/stages.jsonl
```

- 每条 stage 日志字段：`task_id / stage / input_ref / output_ref / latency_ms / token_usage / error / timestamp`。
- 日志只记录输入输出**引用路径**，禁止写入 Key、Prompt 密钥段、论文全文。
- 用 `uv run python .codebuddy/skills/hy-surveyagent-app/scripts/new_run.py --topic "..."` 初始化目录。
- ID 稳定：`P001`（论文）、`C001`（Survey Claim）、`[1]`（正文引用），Stage 之间不得重新编号。

---

## 12. 测试

```bash
uv run pytest
```

| 层级 | 覆盖 |
|---|---|
| Unit | Task Analyzer、Paper Parser、Citation Parser、Claim Extractor、Schema 校验 |
| Integration | `Topic → Agent → Survey → Verification`（用 Mock Provider） |
| Evaluation | Known Good / Known Bad 是否被正确排序（Application 侧保证输出契约稳定） |
| Benchmark | 固定 Topic + Source Papers 反复运行，记录 latency / cost / output |

禁止在测试中调用真实 Hy3 API。

---

## 13. Git 规范

- 分支：`main`（稳定）、`feat/<scope>`、`fix/<scope>`、`exp/<scope>`。
- 提交信息：`<type>(<scope>): <subject>`，例：`feat(reader): add structured paper analysis`。
- 提交前：`uv run ruff check .` → `uv run pytest` → `python .codebuddy/skills/hy-surveyagent-app/scripts/check_repo.py .` → 确认 `git status` 无敏感/产物文件。
- 若密钥曾误提交：先轮换 Key，再处理历史记录。

---

## 14. 开发路线

| Step | 内容 | 跑通目标 |
|---|---|---|
| 1 | Hy3 Adapter + Paper Loader + Simple Writer | `Topic + Papers → Survey` |
| 2 | + Paper Reader | `Topic → Paper Analysis → Survey` |
| 3 | + Knowledge Organizer + Outline Planner | 形成真正的 Agent Workflow |
| 4 | + Citation Verifier | Generate + Verify |
| 5 | 接入 Evaluation | Application → Evaluation |
| 6 | Benchmark Batch Runner | 批量运行 + 统一评测 |

MVP 不做：Long-term Memory、Multi-user、复杂 Web UI、持久化向量库、多模型自动路由、复杂自主循环。

---

## 15. AI 助手协作约定

**Do**

- 动手前先确认涉及哪个 Stage，并读取对应 reference（数据契约 / Prompt 规范 / 工程实践）。
- 新增字段时先改 `app/core/types.py` 与数据契约文档，再改调用方。
- 修改 Prompt 后递增 `version`，并在 PR/提交信息中说明改动点。
- 完成任务后运行 `check_repo.py` 自检。

**Don't**

- 不要用单一巨大 Prompt 替换多阶段 Pipeline。
- 不要把 API Key 写进任何文件或日志。
- 不要在未定义 Schema 的情况下直接开始写 Agent。
- 不要为了「跑通」跳过 Citation 核验或编造引用。
- 不要一次性生成全部 Agent，按 Step 1–6 增量推进。
