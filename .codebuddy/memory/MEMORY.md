# MEMORY.md

## 项目：Hy-SurveyAgent（/yb/hy3）

- 基于 Hy3 的多阶段学术 Survey Agent；用户要求按 `docs/Hy-SurveyAgent Application 开发文档.md` 的 Step 1–6 增量开发，每步高质量完成并分多次 commit。
- 技术栈约定：**uv** 是唯一包管理器（`uv run` 执行一切）；Python 3.11；`pyproject.toml` + `uv.lock` 入库；密钥只存 `API_key.conf`（由 `API_key.conf.example` 复制而来，已 gitignore，禁止硬编码）；非敏感参数在 `configs/config.yaml`。
- 项目级 skill 位于 `.codebuddy/skills/hy-surveyagent-app/`，`AGENTS.md` 是仓库首要约定文件；工程规范见 skill 的 `references/`。
- 测试用 `ScriptedProvider`/`FakeClient`，**禁止在测试中调用真实 Hy3**；冒烟用 `/tmp` 下的假 OpenAI 兼容 HTTP 服务端（端口 8765），用后删除。
- 环境备注：系统 python 为 3.8，实际使用 uv 管理的 3.11；uv 可执行文件经 `PATH="/root/.workbuddy/binaries/python/versions/3.14.3/bin:$PATH"` 暴露。
- Hy3 是腾讯混元开源模型（2026-07），提供 OpenAI 兼容的 Chat Completions 接口（`POST {base_url}/chat/completions`），Adapter 只在 `app/model/hy3_adapter.py`。

## 开发进度（2026-09-06）

- **Application 侧 Step 1–6 全部完成**，各自分多次 commit（均未 push）。
  Pipeline 7 个 Stage：literature_manager → paper_reader → knowledge_organizer → outline_planner
  → survey_writer → citation_verifier → finalize。
- Step 4（Citation Verifier）：Verification 数据模型、Agent（分批/降级/补漏/去重）、Prompt v0.1.0、
  `pipeline.enable_citation_verification` 开关。
- Step 5（Evaluation 契约）：`app/core/contract.py`（六字段最终输出 + `eval_payload.json` 合并结果 +
  `validate_result_payload` 校验，违规抛 ContractError）；evidence_map `citation`→`paper_id`；
  `app/core/generator.py`：`SurveyGenerator` ABC + `HySurveyAgentGenerator`（统一生成器接口）。
- Step 6（Benchmark Batch Runner）：`app/benchmark/`（manifest 加载 + `BenchmarkRunner` + CLI
  `python -m app.benchmark`）；批量执行记录 latency/token（cost 代理）/产物计数/契约校验，
  单任务失败隔离，汇总落 `results/benchmark/<batch_id>/summary.json`；示例清单
  `examples/benchmark_manifest.jsonl`。坑：CLI 测试必须给 `--config` 传绝对路径配置隔离产物。
- 动态测试基建：`/tmp/fake_hy3.py` 假 OpenAI 兼容服务端（端口 8765）按 Prompt 标识分发，支持故障注入；用后删除。
  dispatch 取第一条 user 消息；解析 ID 需排除 Prompt 的 Schema 表格与 few-shot 示例。
- 已修复 bug：Reader 曾信任模型回显 paper_id（few-shot P001 污染）；Verification.from_dict 曾不去重 (claim, citation)。
- 测试 116 个全过（ruff/mypy/check_repo 干净）。
- 工程教训：pytest 经 `| tail` 会吞退出码；git add 清单逐文件核对；CLI 测试注意 load_config 的 root。
- 后续方向：Evaluation 打分与 benchmark 数据底座属 evaluator 侧；Baseline 实现（SimplePromptGenerator 等）。
- 待办：`docs/Hy-SurveyAgent Application 开发文档.md` 与 `AGENTS.md` 有用户侧 markdown 格式化改动未提交，需用户确认后再处理。
