"""Quiz Answer Judge（D6）：答案的 Accuracy / Completeness / Relevance 评分。"""

from __future__ import annotations

from typing import Any

from evaluator.judges.base import BaseJudge, clamp_int, require_str


class QuizAnswerJudge(BaseJudge):
    prompt_name = "quiz_answer"

    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        return {
            "question_id": str(parsed.get("question_id") or ""),
            "accuracy": clamp_int(parsed.get("accuracy"), 4),
            "completeness": clamp_int(parsed.get("completeness"), 4),
            "relevance": clamp_int(parsed.get("relevance"), 2),
            "reason": require_str(parsed.get("reason")),
        }

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "question_id": str(payload.get("question_id") or ""),
            "accuracy": 0,
            "completeness": 0,
            "relevance": 0,
            "reason": "Judge 调用失败，按 0 分降级。",
        }

    def score_of(self, output: dict[str, Any]) -> float:
        return float(
            int(output.get("accuracy", 0))
            + int(output.get("completeness", 0))
            + int(output.get("relevance", 0))
        )
