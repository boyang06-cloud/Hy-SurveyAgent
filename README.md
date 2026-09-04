# Hy-SurveyAgent

基于 **Hy3** 的学术 Survey 生成 Agent Application：输入一个研究主题与一组论文，自动完成
「主题理解 → 文献组织 → 论文阅读 → Survey 规划 → Survey 生成 → 引用核验」，输出结构化、引用可追溯的 Survey。

项目当前进度：**Step 2**（Hy3 Adapter + Literature Manager + Paper Reader + Simple Writer），
已跑通 `Topic + Papers → Paper Analysis → Survey`。后续阶段见 `AGENTS.md` 第 14 节开发路线。

## Pipeline

```text
Research Topic + Source Papers
        ↓
  Task Analyzer            （后续 Step）
        ↓
  Literature Manager       ← Step 2 已实现（Benchmark 固定集检索，不联网）
        ↓
  Paper Reader（并行）      ← Step 2 已实现
        ↓
  Knowledge Organizer      （Step 3）
        ↓
  Outline Planner          （Step 3）
        ↓
  Survey Writer            ← Step 1/2 已实现（基于 Paper Analysis）
        ↓
  Citation Verifier        （Step 4）
        ↓
  Final Survey + Claims + Citations + Evidence Map
```

## 环境要求

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)（本项目唯一的包管理器）

## 安装

```bash
uv sync
```

## 配置

密钥与运行参数是分离的，仓库只提交 `.example` 模板。

```bash
cp API_key.conf.example API_key.conf     # 去掉 .example 后缀后填入真实 Key
cp configs/config.example.yaml configs/config.yaml
```

- `API_key.conf`：只放密钥与服务端点，**已被 .gitignore 忽略，禁止提交**。
- `configs/config.yaml`：模型名、temperature、并发度、超时重试、路径等非敏感参数。
- CI 环境可用环境变量 `HY3_API_KEY` 覆盖 `API_key.conf` 中的值。

Hy3 提供 OpenAI 兼容的 Chat Completions 接口，Adapter 位于 `app/model/hy3_adapter.py`，
是全项目唯一允许调用 Hy3 的位置。

## 快速开始

```bash
# 使用示例主题与论文
uv run python -m app.main --topic "Vision-Language Models for Autonomous Driving" \
    --papers examples/papers_vlm.json

# 使用任务文件（YAML / JSON）
uv run python -m app.main --task-file examples/topic_vlm.yaml --papers examples/papers_vlm.json

# 只渲染 Prompt、不调用模型（离线检查 Prompt 与输入）
uv run python -m app.main --topic "..." --papers examples/papers_vlm.json --dry-run
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--topic` | 研究主题（与 `--task-file` 二选一） |
| `--task-file` | YAML/JSON 任务文件，可带 `research_questions`、`time_range` |
| `--papers` | 论文集 JSON（数组或 `{"papers": [...]}`）/ JSONL |
| `--config` | 运行配置路径，默认 `configs/config.yaml` |
| `--run-id` | 指定运行 ID，默认自动生成 |
| `--limit` | 只取前 N 篇论文（调试用） |
| `--dry-run` | 不调用模型，仅渲染并落盘 Prompt |

## 输出

每次运行写入 `runs/<run_id>/`：

```text
runs/<run_id>/
├── meta.json          # run_id、topic、git commit、python 版本、prompt 版本与 hash、运行参数
├── task.json          # 任务输入
├── papers.json        # 归一化后的 Source Papers
├── analyses.json      # 每篇论文的结构化分析（Paper Reader，失败论文标记 unavailable）
├── claims.json        # Claim 列表与引用映射
├── verification.json  # Step 4 之前为空结构
├── draft.md / final.md
├── result.json        # 对外的结构化结果（Evaluation 接口契约）
└── logs/stages.jsonl  # 每个 Stage 的 latency / token_usage / error
```

`result.json` 结构：

```json
{
  "task": {"topic": "...", "research_questions": []},
  "papers": [{"paper_id": "P001", "title": "...", "year": 2025}],
  "survey": "...markdown 正文...",
  "claims": [{"claim_id": "C001", "text": "...", "citations": ["P001"]}],
  "citations": [{"citation_id": "[1]", "paper_id": "P001", "title": "...", "source": "..."}],
  "evidence_map": []
}
```

## 测试

```bash
uv run pytest          # 全部测试（使用 MockProvider，不调用真实 API）
uv run ruff check .
uv run ruff format .
uv run mypy app
```

提交前请执行仓库自检：

```bash
uv run python .codebuddy/skills/hy-surveyagent-app/scripts/check_repo.py .
```

## 目录结构

```text
app/
├── core/       state / types / pipeline
├── agents/     writer（Step 1）
├── model/      provider（抽象）+ hy3_adapter（唯一 SDK 调用点）
├── prompts/    writer.md
├── io/         loader / exporter
└── main.py     CLI 入口
```

详细工程约定见 [`AGENTS.md`](AGENTS.md)，设计文档见 [`docs/`](docs)。
