---
name: hy-surveyagent-app
description: 用于开发 Hy-SurveyAgent Application —— 一个基于 Hy3 的多阶段学术 Survey 生成 Agent。当需要新增或修改 Task Analyzer、Literature Manager、Paper Reader、Knowledge Organizer、Outline Planner、Survey Writer、Citation Verifier 任一阶段，编写 Hy3 Adapter 与 Prompt 模板，定义结构化数据契约，搭建 Pipeline 与 runs 运行日志，或排查 Survey 生成链路问题时，应使用本 skill。它强制执行"模块化多阶段 Agent Workflow"，禁止用单一巨大 Prompt 直接生成 Survey。
---

# Hy-SurveyAgent Application 开发

## 目标

构建能够自主完成 `研究主题理解 → 文献组织 → 论文阅读 → Survey 规划 → Survey 生成 → 引用核验` 的 Agent Application。

第一版追求：**可运行、可复现、可解释、可验证、可批量评测**。

## 核心原则（不可违反）

1. **多阶段而非大一统**：拆成职责单一的 Module，禁止一个巨大 Prompt 直接产出 Survey。
2. **结构化中间结果**：每个 Stage 产出可序列化、可检查、可单独测试的结构化对象。
3. **最小必要 Context**：按阶段传递该阶段所需的最小信息，禁止把全部论文塞进每个 Agent。
4. **LLM 调用收敛到 Adapter**：只有 `app/model/hy3_adapter.py` 可以调用 Hy3 SDK；Agent 只依赖 `LLMProvider` 抽象。
5. **Prompt 外置**：Prompt 存放于 `app/prompts/*.md`，禁止写死在 Python 代码中。
6. **不发明引用**：Survey Writer 只能使用 Source Papers 中真实存在的论文与证据。
7. **引用核验 ≠ 引用格式化**：Citation Verifier 校验 Claim 是否被 Source Paper 证据支持（Grounding），而非仅检查 `[1]` 是否存在。
8. **密钥不入库**：Hy3 API Key 只存于 `API_key.conf`（由 `API_key.conf.example` 复制而来），禁止硬编码或提交到仓库。
9. **Benchmark 输入固定**：Benchmark 模式下使用固定 Source Paper Set，禁止让实时检索结果影响数据一致性。

## 何时使用

在以下场景加载本 skill：

- 搭建或重构 Survey Pipeline、各 Agent 模块、数据模型、CLI 入口
- 实现 Hy3 Adapter、编写或修改 Prompt 模板
- 增加 Benchmark 批量运行、运行日志与中间产物落盘
- 排查 Survey 生成质量或链路失败问题（先定位到具体 Stage）

涉及 Evaluation Rubric、验证实验、Benchmark 数据集构造时，本 skill 只提供 **Application 侧输出契约**（`references/data-contracts.md` 中的最终输出），不覆盖评测方法设计。

## 快速开始

1. 阅读 `docs/Hy-SurveyAgent Application 开发文档.md`（Application 侧权威设计）与 `docs/Hy-SurveyAgent 项目设计文档.md`（项目全局背景）。
2. 复制 `API_key.conf.example` 为 `API_key.conf`（去掉 `.example` 后缀）并填入真实 Key；确认 `API_key.conf` 已被 git 忽略。
3. 用 uv 建立环境：`uv sync`（命令速查见 `references/engineering-practices.md`）。
4. 按 `references/architecture.md` 的 Step 1–6 顺序增量开发，**不要一次性写完所有 Agent**。
5. 每完成一个 Stage，运行 `python .codebuddy/skills/hy-surveyagent-app/scripts/check_repo.py .` 校验工程约定。

## 开发工作流

### 新增或修改单个 Stage

1. 在 `references/data-contracts.md` 确认该 Stage 的输入/输出 Schema；未定义则先补齐 Schema 再写代码。
2. 在 `app/prompts/<stage>.md` 按 `references/prompt-spec.md` 的六段式结构编写 Prompt。
3. 在 `app/agents/<stage>.py` 实现单一职责函数，只接收最小必要 Context。
4. 强制 JSON 输出 + 解析校验 + 失败重试/回退（见 `references/engineering-practices.md`）。
5. 将该 Stage 产物落盘到 `runs/<task_id>/` 并写 stage 日志。
6. 补 unit test（解析、Schema、边界）与 integration test（Topic → Survey）。

### 排查生成链路问题

自底向上定位：检查 `runs/<task_id>/` 中哪个中间产物最先异常（`analyses.json` → `knowledge.json` → `outline.json` → `draft.md` → `verification.json`），修对应 Stage，禁止直接改 Prompt 全文重跑碰运气。

## 资源索引

- `references/architecture.md` —— Pipeline、各 Agent 职责与禁止事项、Context 传递、并行化、失败处理、推荐目录、开发顺序与每步验收、MVP/V1 边界。
- `references/data-contracts.md` —— 全部结构化 Schema、`SurveyState`、`runs/` 产物清单、ID 命名约定、Evaluation 接口。
- `references/prompt-spec.md` —— Prompt 文件清单、六段式模板、强制 JSON 输出规则、各 Prompt 输入输出速查。
- `references/engineering-practices.md` —— uv 用法、配置与密钥、Hy3 Adapter 规范、日志/重试/并行、测试策略、Git 规范。
- `assets/templates/` —— `API_key.conf.example`、`config.example.yaml`、`prompt_template.md`、`pipeline_skeleton.py`。
- `scripts/check_repo.py` —— 校验仓库约定（密钥泄漏、目录结构、Prompt 齐全、Adapter 收敛）。
- `scripts/new_run.py` —— 创建一次运行的 `runs/<task_id>/` 目录与产物占位文件。

## 完成定义

- 输入 Topic + Source Papers 后可无人介入跑通全流程，输出 Survey 与 References。
- 每条 Citation 可追溯到 Source Paper，并存在对应 Claim 与 Evidence 记录。
- `runs/<task_id>/` 下各阶段产物完整，日志记录 `latency` / `token_usage` / `error`。
- `python scripts/check_repo.py .` 无 FAIL 项。
