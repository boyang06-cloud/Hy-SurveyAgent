# Web 研究工作台

工作台是现有 CLI / Pipeline 的本地交互入口，使用 FastAPI 与原生 HTML、CSS、JavaScript。
无需 Node 构建工具，依赖仍由 uv 和 uv.lock 管理。

## 启动

```bash
uv sync
uv run python -m app.web
```

浏览器打开 http://127.0.0.1:8000 。自定义端口或配置：

```bash
uv run python -m app.web --port 8080 --config configs/config.yaml
```

默认只监听 127.0.0.1。适用于单用户本地研究，不提供多用户认证或公网部署。

首次配置沿用 CLI：

```bash
cp configs/config.example.yaml configs/config.yaml
cp API_key.conf.example API_key.conf
```

随后在本地编辑配置文件。页面仅显示模型名称、并发度与凭据是否已配置，不返回密钥。
修改配置后重启工作台，使展示配置与后续执行保持一致。

## 使用流程

1. 输入主题，上传包含论文标题、摘要或正文的 JSON / JSONL / YAML 文件。
2. 可展开补充研究问题，每行一个，最多 20 个，每个不超过 2000 字。
3. 选择生成 Survey 或离线检查。生成模式调用模型，并强制执行引用核验。
4. 查看真实阶段日志产生的进度、正文、大纲、来源文献与核验结果。
5. 点击正文的引用编号，在右侧查看对应论文和原文证据。
6. 从运行产物页下载各阶段的 JSON / Markdown，供研究复核与评测消费。

JSON 支持论文数组或 `{"papers": [...]}`；JSONL 每行一个论文对象；YAML 使用对象数组。
论文使用现有 `Paper` 契约：`paper_id / title / authors / year / abstract / content / source`。
缺失 ID 由原 Loader 分配；标题去重；重复 ID 拒绝上传。
单次文件上限 10 MB（UTF-8），最多 200 篇。当前不直接解析 PDF，也不提供在线检索。

「试用合成示例文献」读取仓库已有 examples/papers_vlm.json，并自动选择离线检查。
这些论文不是真实文献。离线检查只渲染 Prompt，不生成正文或真实核验结论。

## 状态语义

- 正在运行：本服务有对应后台线程；日志显示已结束的 Stage，下一阶段显示执行中。
- 生成完成：Pipeline 正常返回，不代表所有论断获证据支持。
- 离线检查完成：未调用模型，不计算支持率或宣称核验通过。
- 运行失败：后台任务异常结束，可检查已有产物与本地 logs/stages.jsonl。
- 运行已中断：上次服务结束前未写入终态，当前服务没有对应执行线程。
- 产物不完整：CLI 历史目录没有完整 result.json，或 CLI 任务仍在运行。

工作台每次只执行一个任务；第二次提交返回 409，避免意外并发调用模型。
任务在后台执行，切换页面或刷新浏览器不会终止任务；停止服务会中断任务。
不提供断点恢复或取消功能，失败后修正输入/配置并创建新任务。

页面会读取配置的 runs 目录，兼容已有 CLI 运行记录。
表单草稿仅保留在当前页面会话内存中；刷新浏览器会清空未提交输入。
任务详情使用 `#run/<task_id>/<tab>` 深链接。

## 接口与工程边界

- `GET /api/settings`：非敏感配置摘要。
- `GET /api/runs`：真实运行列表。
- `POST /api/runs`：提交 `RunRequest`，立即返回 202 与任务 ID。
- `GET /api/runs/{id}`：状态、阶段日志摘要、允许展示的产物、净化后的正文 HTML。
- `GET /api/runs/{id}/status`：轮询用的轻量状态，只含状态与阶段日志，不返回产物全文。
- `GET /api/runs/{id}/files/{name}`：白名单产物下载。
- `GET /api/example`：合成示例文件。

Web 请求模型位于 app/web/schemas.py，不改变 app/core/types.py 中的 Stage 数据模型。
请求字段：`topic`、`research_questions`、`filename`、`content`、`mode`；不接受文件系统路径、
模型地址、密钥或任意运行命令。Web 服务直接复用 run_pipeline、RunWriter、load_config、
Hy3Adapter，不复制 Agent 逻辑，不修改 Prompt。

生成目录沿用原契约，额外保存 web_status.json（运行状态、模式，失败时附异常类型）。meta.json 记录实际配置、
Prompt 版本和 hash、web_mode。下载白名单不包含密钥、meta、原始日志或渲染 Prompt。
完整 Stage 产物仍在本地保存，包括离线渲染的 Prompt。

运行中的任务，页面每 2.5 秒轮询 `/api/runs/{id}/status`；仅在状态或阶段日志变化时拉取完整详情，
避免反复传输产物全文。阶段未写入内容的空产物（如离线检查的 draft.md）不展示为可下载结果。
后台任务失败时只把异常类型写入 web_status.json 并记录到本地日志，不回显原始异常。

Web 入口限制本地主机、同源请求、请求大小与下载白名单；拒绝符号链接下载。
Markdown 禁用原始 HTML、远程图片和危险链接协议；前端用户文本进行 HTML 转义。
通过 CSP 限制脚本、连接和嵌入；无外部 CDN 或字体请求。
HTTP 输入错误不回显请求体，运行错误不向浏览器返回原始异常。

## 验证

```bash
uv run pytest tests/test_web.py
uv run pytest
uv run ruff check .
uv run mypy app/web app/io/workspace.py
uv run python .codebuddy/skills/hy-surveyagent-app/scripts/check_repo.py .
```

API 测试覆盖真实 dry-run、Mock Provider 完整生成与证据关联、非法上传、重复 ID、
配置缺失、跨源访问、路径白名单与符号链接、Markdown 注入、忙碌冲突、失败终态及重启中断。
视觉规范见 design-system/hy-surveyagent/MASTER.md。
