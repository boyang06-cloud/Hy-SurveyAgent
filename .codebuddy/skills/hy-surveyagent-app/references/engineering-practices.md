# 工程实践

## 1. 环境：uv 包管理

本项目**只用 uv**管理依赖与虚拟环境，不使用 pip / poetry / conda。

| 目的 | 命令 |
|---|---|
| 初始化项目 | `uv init`（已有 `pyproject.toml` 时跳过） |
| 创建虚拟环境 | `uv venv --python 3.11` |
| 安装全部依赖 | `uv sync`（依据 `uv.lock`，可复现） |
| 新增运行时依赖 | `uv add <pkg>` |
| 新增开发依赖 | `uv add --dev pytest ruff mypy` |
| 移除依赖 | `uv remove <pkg>` |
| 运行命令 | `uv run python -m app.main`、`uv run pytest` |
| 锁定 / 升级 | `uv lock`、`uv lock --upgrade-package <pkg>` |
| 固定 Python 版本 | `uv python pin 3.11` |
| 安装指定 Python | `uv python install 3.11` |

约定：

- Python 版本 **≥ 3.11**（项目需要完整的 `asyncio` 与类型注解支持）；用 `.python-version` 固定。
- `pyproject.toml` 与 `uv.lock` **同时入库**（Application 是应用而非库，锁文件入库保证可复现）。
- `uv run` 是唯一推荐的执行方式，禁止在文档中写 `pip install` / `python app/main.py` 这类绕过环境管理器的命令。
- 依赖分组：`main`（运行时）、`dev`（测试与 lint）。

## 2. 配置与密钥

### 2.1 密钥文件（本项目约定）

- 仓库仅提交模板：`API_key.conf.example`（根目录）。
- 开发者首次使用：

  ```bash
  cp API_key.conf.example API_key.conf     # 去掉 .example 后缀
  # 编辑 API_key.conf 填入真实 Key
  ```

- `API_key.conf` **必须**被 `.gitignore` 忽略，禁止提交、禁止出现在示例、日志、测试夹具与报错信息中。
- 代码只读取 `API_key.conf`（INI 格式，`configparser` 解析）；CI 场景允许用环境变量 `HY3_API_KEY` 覆盖，但代码中不得出现任何 Key 字面量。
- 加载失败时抛出明确错误并提示 `cp API_key.conf.example API_key.conf`，禁止回退到硬编码默认值。

示例模板见 `assets/templates/API_key.conf.example`。

### 2.2 运行配置（非密钥）

- `configs/config.example.yaml`：模型名、temperature、max_tokens、并发度、超时、重试次数、路径（`runs/`、`results/`、`benchmark/`）。
- 复制为 `configs/config.yaml` 后按需修改；该文件中**不得出现任何密钥**。
- 运行参数（模型名、temperature、并发度、Prompt 版本）必须写入 `runs/<task_id>/meta.json`，满足可复现性验收。

模板见 `assets/templates/config.example.yaml`。

## 3. Hy3 Adapter 规范

```python
class LLMProvider:
    def generate(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse: ...
```

- Hy3 SDK 的 import **只允许出现在 `app/model/hy3_adapter.py`**。
- 所有 Agent 只依赖 `LLMProvider`，不得感知具体模型与厂商。
- Adapter 内统一处理：客户端初始化（读取 `API_key.conf`）、`timeout`、指数退避 `retry`、`token_usage` 统计、错误归一化。
- 返回对象至少包含 `text`、`token_usage`、`model`、`latency_ms`，供 stage 日志使用。
- 目的：替换为 Baseline 模型或 Mock Provider 时，Pipeline 无需任何改动。

## 4. 日志

- 每个 Stage 写一条 JSONL 到 `runs/<task_id>/logs/stages.jsonl`。
- 字段：`task_id`、`stage`、`input_ref`、`output_ref`、`latency_ms`、`token_usage`、`error`、`timestamp`。
- 记录输入/输出 **引用路径**而非大段原文，避免日志文件膨胀与密钥泄漏。
- 日志中禁止打印 API Key、完整 Prompt 密钥段和论文全文。

## 5. 重试与回退

每个 Stage 统一具备：

```text
Input Validation → Timeout → Retry → Fallback → Error Logging
```

- 超时与重试次数来自配置（默认 3 次，指数退避）。
- 结构化解析失败：重试一次并附带错误信息要求只输出 JSON；仍失败则记 `error` 并走 Fallback。
- Paper Reader 单篇失败 → 标记 `status: "unavailable"` → 继续，**禁止因单篇失败导致任务崩溃**。
- 关键 Stage（Organizer / Planner）无合法产物时才允许整体中止，并给出明确错误原因。

## 6. 并行

- 论文阅读使用 `asyncio.gather` + `asyncio.Semaphore(max_concurrency)`。
- 并发度写入配置并记录到 `meta.json`，保证 Benchmark 结果可比。

## 7. 测试

| 层级 | 覆盖对象 |
|---|---|
| Unit | Task Analyzer、Paper Parser、Citation Parser、Claim Extractor、Score Aggregator、Schema 校验 |
| Integration | `Topic → Agent → Survey → Verification` 端到端（可用 Mock Provider 替代真实 Hy3） |
| Evaluation | Known Good / Known Bad 样本是否被正确排序（Application 侧只需保证输出契约稳定） |
| Benchmark | 固定 Topic + Source Papers 反复运行，记录 latency / cost / output |

- 测试命令：`uv run pytest`。
- 禁止在测试中调用真实 Hy3 API（用 Mock Provider），避免费用与不稳定性。

## 8. 代码风格

- 类型注解全覆盖；数据模型用 `@dataclass`（或 pydantic），禁止裸 `dict` 跨模块传递。
- 模块、函数、变量名用英文；注释与文档用中文。
- `ruff` 做 lint/format，`mypy` 做静态检查（配置写在 `pyproject.toml`）。
- 单一职责：一个 Agent 文件只做一件事，禁止在 Agent 里直接写文件 IO（交给 `app/io/`）。
- 常量禁止散落：路径、模型参数、重试策略统一走配置。

## 9. Git 规范

- 分支：`main`（稳定）、`feat/<scope>`、`fix/<scope>`、`exp/<scope>`（实验）。
- 提交信息：`<type>(<scope>): <subject>`，如 `feat(reader): add structured paper analysis`。
- 提交前必做：
  1. `uv run ruff check . && uv run pytest`
  2. `python .codebuddy/skills/hy-surveyagent-app/scripts/check_repo.py .`
  3. 确认 `git status` 中没有 `API_key.conf`、`runs/`、`results/`、`.venv/`
- 禁止提交：密钥、运行结果、大体积论文原文、虚拟环境。
- 若密钥曾误提交：立即轮换 Key，再处理历史记录（不要只在后续提交中删除文件）。

## 10. 常用命令速查

```bash
uv sync                          # 安装依赖
uv run python -m app.main --topic "..." --papers benchmark/source/xxx.json
uv run python scripts/new_run.py --task-id t-2026-09-03-001
uv run pytest
uv run ruff check . && uv run ruff format .
uv add <pkg> / uv add --dev <pkg>
```
