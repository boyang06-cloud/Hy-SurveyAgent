# MEMORY.md

## 项目：Hy-SurveyAgent（/yb/hy3）

- 基于 Hy3 的多阶段学术 Survey Agent；用户要求按 `docs/Hy-SurveyAgent Application 开发文档.md` 的 Step 1–6 增量开发，每步高质量完成并分多次 commit。
- 技术栈约定：**uv** 是唯一包管理器（`uv run` 执行一切）；Python 3.11；`pyproject.toml` + `uv.lock` 入库；密钥只存 `API_key.conf`（由 `API_key.conf.example` 复制而来，已 gitignore，禁止硬编码）；非敏感参数在 `configs/config.yaml`。
- 项目级 skill 位于 `.codebuddy/skills/hy-surveyagent-app/`，`AGENTS.md` 是仓库首要约定文件；工程规范见 skill 的 `references/`。
- 测试用 `ScriptedProvider`/`FakeClient`，**禁止在测试中调用真实 Hy3**；冒烟用 `/tmp` 下的假 OpenAI 兼容 HTTP 服务端（端口 8765），用后删除。
- 环境备注：系统 python 为 3.8，实际使用 uv 管理的 3.11；uv 可执行文件经 `PATH="/root/.workbuddy/binaries/python/versions/3.14.3/bin:$PATH"` 暴露。
- Hy3 是腾讯混元开源模型（2026-07），提供 OpenAI 兼容的 Chat Completions 接口（`POST {base_url}/chat/completions`），Adapter 只在 `app/model/hy3_adapter.py`。

## 开发进度（2026-09-04）

- Step 1（Adapter + Loader + Simple Writer）、Step 2（Literature Manager + Paper Reader 并行）、
  Step 3（Knowledge Organizer + Outline Planner + 按 Outline 分节写作）已完成并各自分多次 commit。
- Pipeline 6 个 Stage：literature_manager → paper_reader → knowledge_organizer → outline_planner → survey_writer → finalize；产物落盘 `runs/<task_id>/`，`logs/stages.jsonl` 记录 latency/token/error。
- Writer 引用机制：模型输出 `[[P001]]` 标记 → 代码按全文首现顺序重排为 `[1]/[2]` 并重建 References；无法绑定的 Claim 丢弃、未知编号记入 `unknown_citations`。
- 单篇论文读取失败 → `status=unavailable` 继续跑；全部失败或 Organizer/Planner 无合法产物 → Stage 失败中止。
- 下一步：Step 4 Citation Verifier（Claim → Citation → Paper → Evidence，输出 support/evidence/confidence）。
- 待办：`docs/Hy-SurveyAgent Application 开发文档.md` 与 `AGENTS.md` 有用户侧 markdown 格式化改动未提交，需用户确认后再处理。
