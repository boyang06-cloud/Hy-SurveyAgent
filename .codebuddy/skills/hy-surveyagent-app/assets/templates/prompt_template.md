# <Stage Name> Prompt

> version: 0.1.0
> 用途：<一句话说明该 Prompt 服务于哪个 Agent>
> 输入来源：`runs/<task_id>/<xxx>.json`
> 输出去向：`runs/<task_id>/<xxx>.json`

## Role

你是 <角色>，唯一职责是 <一句话职责>。
你不负责 <明确排除的职责，例如"撰写 Survey 正文"或"评价输出质量">。

## Input Schema

| 变量 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `{{ topic }}` | string | 是 | 研究主题 |
| `{{ research_questions }}` | list[string] | 否 | 研究问题，可为空 |
| `{{ context }}` | object/string | 是 | 本阶段最小必要 Context |

输入中未提供的字段视为缺失，缺失时按 Failure Constraints 处理。

## Output Schema

只输出一个 JSON 对象，不要输出任何解释性文字、Markdown 代码块标记或额外说明。

```json
{
  "field_a": "",
  "field_b": []
}
```

字段约定：
- `field_a`：<类型与含义>
- `field_b`：<类型与含义；枚举值：xxx / yyy>

## Rules

1. 必须 <硬性约束>。
2. 禁止 <禁止行为，例如"输出输入中不存在的论文、数据集或实验数字">。
3. 必须 <可操作的质量要求，禁止使用"较好 / 尽量 / 尽可能"等模糊表述>。
4. 所有文本字段使用 <语言> 输出。

## Few-shot Examples

### 正例

输入：

```json
{ "topic": "..." }
```

输出：

```json
{ "field_a": "...", "field_b": ["..."] }
```

### 反例

输入：

```json
{ "topic": "..." }
```

输出：

```json
{ "field_a": "模型推测出的内容", "field_b": [] }
```

违反原因：Rules 2，输出了输入中不存在的信息。

## Failure Constraints

- 信息不足时：返回空字符串 `""` 或空数组 `[]`，禁止推测或编造。
- 输入与主题无关时：返回符合 Output Schema 的空结构。
- 输入过长被截断时：只对可见部分做抽取，缺失字段留空，不得补全。
- 无法判定的字段：返回 `null`，并在允许的字段中说明原因。
