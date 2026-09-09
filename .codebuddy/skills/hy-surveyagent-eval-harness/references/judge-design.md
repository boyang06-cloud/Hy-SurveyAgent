# Judge 设计

## 1. 七类分解式 Judge

| Judge | 服务维度 | 粒度 | 输入 | 输出 |
|---|---|---|---|---|
| Factual Judge | D1 | claim | claim + top-k 证据段落 | label / score(0,1,2) / reason |
| Citation Judge | D2 | claim-citation pair + 元数据 | claim + citation + paper metadata | support(0,1,2) / valid / fabricated |
| Coverage Judge | D3 | KIU | KIU description + survey 段落 | score(0,1,2) + evidence_span |
| Synthesis Judge | D4 | document | 整篇 survey | taxonomy / comparison / evolution / insight |
| Outline Judge | D5 | document | outline 或 headings | hierarchy / logic / function / relevance |
| Quiz Answer Judge | D6 | quiz | question + reference answer + 生成答案 + 引用段落 | accuracy / completeness / relevance |
| Terminology Judge | D7 | chapter | chapter 文本 | severe / moderate / minor 计数 |

禁止新增"整体质量 Judge"替代上述任一 Judge。

## 2. 统一输出 Schema

所有 Judge 强制 JSON 输出，字段缺失时返回 `""` / `[]` / `0`，禁止编造。

```json
{
  "claim_id": "C012",
  "claim": "3DGS represents scenes using anisotropic 3D Gaussians.",
  "citation": "P007",
  "evidence": "…原文段落…",
  "label": "PARTIALLY_SUPPORTED",
  "score": 1,
  "reason": "The paper supports X but not Y."
}
```

约束：

- `label` 取值固定枚举（`SUPPORTED` / `PARTIALLY_SUPPORTED` / `UNSUPPORTED` / `FABRICATED` / `NO_SUFFICIENT_INFORMATION`）。
- `score` 必须是整数且落在 rubric 允许范围内；越界时按 `UNSUPPORTED` 处理并记录 warning。
- `reason` 必须引用证据内容，禁止只写 "The claim is correct."。

## 3. Evidence-gating（核心）

- 证据检索为空 → Factual Judge 直接判 0，不进入 LLM。
- Quiz Answer 无 supporting evidence → 该题 0 分。
- Judge Prompt 中必须显式写：

```text
You must judge ONLY based on the provided evidence.
If the evidence does not support the claim, return UNSUPPORTED.
Do NOT use your own knowledge.
```

- 禁止 Prompt 中出现 "based on your knowledge" 之类放行条款。

## 4. 稳定性

- `temperature = 0`，所有 Judge 统一由 `evaluator/config.py` 的 `JudgeConfig` 提供，禁止在代码里写死其它温度。
- 核心维度 D1 / D2 / D4 / D6 建议双 Judge：

```text
|Judge_A − Judge_B| > threshold  →  调用 Judge C  →  median(A, B, C)
```

默认 `threshold`：0–2 分制取 1；0–4 分制取 1；0–100 分制取 10。

- 记录每次 Judge 的 `model` / `prompt_version` / `temperature` / `token_usage` / `latency_ms`，便于复现与成本分析。

## 5. Judge 缓存

同一 `(prompt_version, model, temperature, 输入 hash)` 的结果缓存到 `results/eval/<run_id>/judge_cache/`（或独立 cache 目录）：

- 重跑与 A/B 对比时可节省大量调用；
- 缓存键必须包含 prompt 版本与模型名，改 Prompt 后自动失效；
- 缓存只用于**评测读取**，不得用于绕过评测（禁止预填答案）。

## 6. 失败处理

每个 Judge 调用具备 `输入校验 → 超时 → 指数退避重试 → 降级 → 错误日志`：

- JSON 解析失败：用 `LLMProvider.generate_json` 的 repair 重试一次，仍失败则判 `UNSUPPORTED` 并记 `error`。
- 批量 Judge 中单条失败只影响该条，不中断维度。
- 某维度失败率超过 30% 时，在报告中标记该维度 `low_confidence`。

## 7. Prompt 文件规范

位置：`evaluator/prompts/{factual,citation,coverage,synthesis,outline,quiz_answer,terminology}.md`

每个 Prompt 必含六段：`Role / Input Schema / Output Schema / Rules / Few-shot Examples / Failure Constraints`，文件头记录 `version`，修改后递增。
模板见 `assets/templates/judge_prompt_template.md`。

Prompt 中的 few-shot 示例不得包含会被误解析为真实 ID 的占位（如示例里的 `P001` 需与真实 ID 空间隔离，或在解析时按 structure 而非正则提取 ID）。

## 8. 测试

- 每个 Judge 至少三类 unit test：① 合法 JSON 解析；② 枚举/范围校验与降级；③ 证据为空时的 gating 行为。
- 用 `ScriptedProvider` / `FakeClient` 注入固定回答，**禁止在测试中调用真实 Hy3 API**。
- 公式类逻辑（D1/D2/D3/D7 的算术）必须与 LLM 解耦，可纯函数单测。
