# 评测侧工程实践

## 1. 环境与命令

沿用仓库 `AGENTS.md` 的约定：**uv 是唯一包管理器**，Python ≥ 3.11。

```bash
uv sync
uv run python -m evaluator --dataset <ds> --run <run>
uv run pytest
uv run ruff check . && uv run ruff format .
uv run mypy evaluator
```

禁止 `pip install`、禁止裸 `python evaluator/...`。

## 2. 配置与密钥

- 密钥只存 `API_key.conf`（由 `API_key.conf.example` 复制而来，已 gitignore），通过 `app.config` 读取；环境变量 `HY3_API_KEY` 仅用于 CI 覆盖。
- 评测运行参数（权重、模型名、temperature、阈值、并发、缓存目录、输出路径）放 `configs/eval.yaml` 或 `evaluator/config.py` 默认值，**禁止把权重硬编码散落在各 Judge 里**。
- 每次运行把生效配置写入 `results/eval/<run_id>/config.json`。

## 3. 与 LLM 的交互

- 复用 `app.model.provider.LLMProvider`（`generate` / `generate_json`），禁止在 Evaluator 内新建 SDK 客户端。
- Judge 调用统一走 `evaluator/judges/base.py` 的 `BaseJudge`：负责 prompt 加载、messages 组装、temperature 注入、JSON 解析、schema 校验、重试、缓存、token/latency 统计。
- 单个维度内可并行（`asyncio.gather` + `Semaphore` 限流），但不得因并发改变 Judge 输入顺序导致结果不可复现——缓存键与落盘顺序必须稳定。

## 4. Provenance

每次评测必须能回答"这个分数是怎么来的"：

```json
{
  "run_id": "e-20260909-120000",
  "git_commit": "a852472",
  "dataset_version": "hysurveybench_v1.0",
  "model": "hy3-...",
  "temperature": 0,
  "prompts": {"factual": {"version": "0.1.0", "sha256": "..."}},
  "weights": {"D1": 0.18, "...": 0.0}
}
```

改 Prompt 或权重后必须递增版本；对比实验必须引用同一 dataset 版本。

## 5. 只读 Dataset

- 评测运行期间对 `datasets/<version>/` 只做读操作；需要新增/修订数据走 `hy-surveyagent-eval-dataset` skill，产出新版本目录而不是原地改。
- 代码扫描中不得出现对 dataset 路径的写打开（`check_eval_repo.py` 会检查）。

## 6. 测试策略

| 层级 | 覆盖 |
|---|---|
| Unit | claim 抽取、citation 解析、各维度公式（纯函数）、Judge 输出解析与降级、Gate 计算 |
| Integration | 用 `ScriptedProvider` 跑通 `单个 topic × 全维度` |
| Regression | 固定 dataset + 固定 Judge 回答，断言分数不变（防公式被误改） |
| Calibration | Human vs LLM 的 Kappa / Spearman 计算脚本 |

禁止在测试中调用真实 Hy3 API；`pytest` 必须可在无 Key 环境下通过。

## 7. 成本与性能

- 记录每维度 `calls / prompt_tokens / completion_tokens / latency_ms` 到 `cost.json`。
- 大批量评测前先用 `--limit-topics 1` 估算成本。
- 长 survey 优先做 section retrieval 而不是整篇重复送入。

## 8. 禁止清单

1. 禁止单一整体打分 Prompt（`Rate this survey from 1 to 10`）。
2. 禁止 Judge 在无证据时依据参数知识给分。
3. 禁止在评测流程中生成/修改 Gold Papers、Rubric、Quiz。
4. 禁止跳过 Critical Failure Gate 只报加权平均。
5. 禁止把权重写死在各维度模块。
6. 禁止提交 `API_key.conf`、`configs/eval.yaml`（本地）、`results/`、judge 缓存。
7. 禁止为了分数好看而调整权重或阈值；调参必须在报告中说明理由与版本。

## 9. 自检

```bash
uv run python .codebuddy/skills/hy-surveyagent-eval-harness/scripts/check_eval_repo.py .
```

检查项：疑似硬编码 Key / `API_key.conf` 被跟踪 / `results/` 被跟踪 / Prompt 文件缺失或缺少六段 / Judge temperature 非 0 / Evaluator 直接 import `app.agents` / dataset 路径被写打开 / 出现整体打分式 Prompt。
出现 FAIL 必须先修复。
