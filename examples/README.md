# 示例数据

`topic_vlm.yaml` 与 `papers_vlm.json` 仅用于本地冒烟测试与 Prompt 调试，
其中的标题、作者、摘要均为**合成示例数据**，不是真实文献，请勿作为事实来源。

用法：

```bash
uv run python -m app.main --topic "Vision-Language Models for Autonomous Driving" \
    --papers examples/papers_vlm.json

uv run python -m app.main --task-file examples/topic_vlm.yaml --papers examples/papers_vlm.json
```

Benchmark 使用的真实论文数据请放在 `benchmark/` 下，并固定数据版本。
