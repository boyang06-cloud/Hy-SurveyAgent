# MEMORY.md

## 项目：Hy-SurveyAgent（/yb/hy3）

- 基于 Hy3 的多阶段学术 Survey Agent；用户要求按 `docs/Hy-SurveyAgent Application 开发文档.md` 的 Step 1–6 增量开发，每步高质量完成并分多次 commit。
- 技术栈约定：**uv** 是唯一包管理器（`uv run` 执行一切）；Python 3.11；`pyproject.toml` + `uv.lock` 入库；密钥只存 `API_key.conf`（由 `API_key.conf.example` 复制而来，已 gitignore，禁止硬编码）；非敏感参数在 `configs/config.yaml`。
- 项目级 skill 位于 `.codebuddy/skills/hy-surveyagent-app/`，`AGENTS.md` 是仓库首要约定文件；工程规范见 skill 的 `references/`。
- 测试用 `ScriptedProvider`/`FakeClient`，**禁止在测试中调用真实 Hy3**；冒烟用 `/tmp` 下的假 OpenAI 兼容 HTTP 服务端（端口 8765），用后删除。
- 环境备注：系统 python 为 3.8，实际使用 uv 管理的 3.11；uv 可执行文件经 `PATH="/root/.workbuddy/binaries/python/versions/3.14.3/bin:$PATH"` 暴露。
- Hy3 是腾讯混元开源模型（2026-07），提供 OpenAI 兼容的 Chat Completions 接口（`POST {base_url}/chat/completions`），Adapter 只在 `app/model/hy3_adapter.py`。

## 开发进度（2026-09-06）

- Step 1–5 全部完成并各自分多次 commit：Pipeline 为 7 个 Stage
  （literature_manager → paper_reader → knowledge_organizer → outline_planner → survey_writer → citation_verifier → finalize）。
- Step 4（Citation Verifier）：Verification/VerificationResult 数据模型（support ∈ {True/False/None}，summary 按 Claim 聚合）、
  `citation_verifier.py` Agent（分批调用、单批失败降级 unverifiable、`_fill_unassessed` 补漏、去重）、
  六段式 Prompt（v0.1.0）、`pipeline.enable_citation_verification` 开关；evidence_map 进入 result.json。
- Step 5（Evaluation 契约）：`app/core/contract.py` 集中定义六字段最终输出 + `eval_payload.json`
  机器可读合并结果 + `validate_result_payload` 结构校验（失败抛 ContractError）；evidence_map 中
  `citation` → `paper_id` 对齐契约；`app/core/generator.py` 提供 `SurveyGenerator` ABC +
  `HySurveyAgentGenerator`（architecture 第 12 节统一生成器接口）。
- 动态测试基建：`/tmp/fake_hy3.py` 假 OpenAI 兼容服务端（端口 8765）按 Prompt 标识分发，支持故障注入；
  用后删除。dispatch 取第一条 user 消息；解析 ID 需排除 Prompt 的 Schema 表格与 few-shot 示例。
- 已修复 bug：Reader 曾信任模型回显 paper_id（few-shot P001 污染）；Verification.from_dict 曾不去重 (claim, citation)。
- 测试 104 个全过（ruff/mypy/check_repo 干净）；动态测试覆盖 dry-run、正常端到端、单篇失败降级、契约输出。
- 工程教训：pytest 经 `| tail` 会吞退出码，提交前检查要直接用 pytest 退出码；git add 清单需逐文件核对。
- 下一步：Step 6 Benchmark Batch Runner。
- 待办：`docs/Hy-SurveyAgent Application 开发文档.md` 与 `AGENTS.md` 有用户侧 markdown 格式化改动未提交，需用户确认后再处理。
