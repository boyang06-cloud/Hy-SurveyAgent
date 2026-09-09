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
- 已知偏差：Task Analyzer 阶段未实现（MVP 以 TaskInput 直通，`SurveyState.task_spec` 为占位），属 V1 范围。
- 后续方向：Evaluation 打分与 benchmark 数据底座属 evaluator 侧；Baseline 实现（SimplePromptGenerator 等）。

## 项目级 Skills（2026-09-09）

- `.codebuddy/skills/hy-surveyagent-app/` —— Application（Pipeline / Agent / Prompt / Adapter）。
- `.codebuddy/skills/hy-surveyagent-eval-harness/` —— 搭建 `evaluator/`：D1–D8 评分器、七类分解式 Judge、
  加权聚合 + Critical Failure Gate、报告；依据 `eval_harness/eval_protocol.md`。
- `.codebuddy/skills/hy-surveyagent-eval-dataset/` —— 搭建 `scripts/build_eval_dataset/`：
  基于 InternScience/SurveyBench 构造 HySurveyBench（ingest → 规范化 → metadata → Gold Papers →
  fulltext → KIU → Quiz → validate）；依据 `eval_dataset/eval_data_construct.md`。
- 铁律：**构造与评测分离**，评测运行时只读冻结的 `datasets/<version>/`。
- 评测侧自检：`python .codebuddy/skills/hy-surveyagent-eval-harness/scripts/check_eval_repo.py .`
  （密钥扫描复用 app skill 的占位值白名单，只扫 .py/.yaml/.yml/.toml）。

## 本地 Web 工作台（2026-09-09）

- 前端由 gpt6astra 编写，我做了 review + 修复 + 清理 + 拆分提交（6 个 commit，未 push）。
- 结构：`app/web/`（server / service / schemas / __main__ / static）、`app/io/workspace.py`、
  `tests/test_web.py`、`docs/Web 工作台.md`、`design-system/hy-surveyagent/MASTER.md`；入口 `uv run python -m app.web`。
- 关键约定：Web 只做交互层，复用 `run_pipeline` / `Hy3Adapter` / `RunWriter`，不改 Agent 与 Prompt；
  产物下载走 `ARTIFACTS` 白名单并拒绝符号链接；运行中轮询轻量接口 `/api/runs/{id}/status`，
  完整 detail 只在状态变化时拉取。
- 坑：Starlette `BaseHTTPMiddleware.call_next` 用的是原始 request 的 `wrapped_receive`（读 `request._body`），
  构造新 `Request(scope, receive)` 传进去无效；限制请求体要用公开的 `await request.body()`。
