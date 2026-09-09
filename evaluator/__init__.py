"""Hy-SurveyAgent Evaluation Harness（独立于 Application 的评测模块）。

只消费 Application 的六字段最终输出（``runs/<task_id>/result.json``）与冻结的
``datasets/<version>/``，实现 ``eval_harness/eval_protocol.md`` v2.0 的
D1–D8 评分、加权聚合与 Critical Failure Gate。禁止 import ``app.agents``。
"""

__version__ = "0.1.0"
