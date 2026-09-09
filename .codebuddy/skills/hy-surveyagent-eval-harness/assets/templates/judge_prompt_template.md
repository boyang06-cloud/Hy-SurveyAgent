<!-- version: 0.1.0 -->
<!-- 复制本模板为 evaluator/prompts/<judge>.md 并替换 TODO；文件头 version 修改后必须递增 -->

# <Judge 名称> Judge（服务维度：Dx）

## Role

<!-- 一句话：该 Judge 只回答哪一个具体问题。禁止扩展为整体质量评价。 -->

## Input Schema

```json
{
  "claim_id": "C001",
  "claim": "待判定的陈述",
  "citation": "P007",
  "evidence": [
    { "paper_id": "2308.04079", "section_id": "sec_3", "text": "原文段落" }
  ]
}
```

<!-- 证据字段是必需的：没有 evidence 的 Judge 一律视为设计错误 -->

## Output Schema

```json
{
  "claim_id": "C001",
  "label": "SUPPORTED",
  "score": 2,
  "reason": "证据中明确说明了……"
}
```

- `label` 枚举：`SUPPORTED` / `PARTIALLY_SUPPORTED` / `UNSUPPORTED` / `FABRICATED` / `NO_SUFFICIENT_INFORMATION`
- `score` 必须是整数，范围见下方 Rules
- `reason` 必须引用证据内容

## Rules

- 只能依据提供的 evidence 判断，禁止使用自身知识或推测。
- 证据为空或不支持该陈述时返回 `UNSUPPORTED`（score = 0）。
- 核心正确但缺条件 / 过度泛化 / 数值不精确 / 范围扩张 → `PARTIALLY_SUPPORTED`（score = 1）。
- 字段缺失时返回 `""` / `[]` / `0`，禁止编造。
- 只输出一个 JSON 对象，不要 Markdown 代码块标记或解释性文字。

## Few-shot Examples

### Example 1 — SUPPORTED

Input:
```json
{ "claim_id": "C001", "claim": "...", "evidence": [{ "text": "..." }] }
```

Output:
```json
{ "claim_id": "C001", "label": "SUPPORTED", "score": 2, "reason": "..." }
```

### Example 2 — UNSUPPORTED（反例）

Input:
```json
{ "claim_id": "C002", "claim": "...", "evidence": [] }
```

Output:
```json
{ "claim_id": "C002", "label": "UNSUPPORTED", "score": 0, "reason": "No evidence provided." }
```

<!-- 示例中的 ID 必须与真实 ID 空间（P001 / C001 / [1]）隔离，避免被解析器误提取 -->

## Failure Constraints

- 输出不是合法 JSON：重试一次并要求只输出 JSON；仍失败则判 `UNSUPPORTED` 并记录 error。
- `label` 不在枚举内或 `score` 越界：按 `UNSUPPORTED` 降级并记录 warning。
- 单条失败不影响同批次其它条目。
