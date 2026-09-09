"""Quiz 评分：Accuracy / Completeness / Relevance + evidence-gating。"""

from __future__ import annotations

from dataclasses import dataclass

from evaluator.judges.quiz_answer import QuizAnswerJudge
from evaluator.quizzes.answerer import QuizAnswer


@dataclass
class QuizScore:
    question_id: str
    accuracy: int
    completeness: int
    relevance: int
    total: int  # 0–10
    gated: bool = False
    unanswered: bool = False

    @property
    def normalized(self) -> float:
        """归一化到 [0,100]。"""
        return self.total / 10.0 * 100.0


def score_answer(
    judge: QuizAnswerJudge,
    *,
    question_id: str,
    question: str,
    reference_answer: str,
    answer: QuizAnswer,
    cited_sections: list[str] | None = None,
    evidence_gating: bool = True,
    dual: bool = False,
    threshold: float = 1.0,
) -> QuizScore:
    """按协议评分；evidence-gating：无引用段落支撑时该题直接 0 分。"""
    if answer.unanswered:
        return QuizScore(question_id, 0, 0, 0, 0, unanswered=True)
    if evidence_gating and not answer.used_sections:
        return QuizScore(question_id, 0, 0, 0, 0, gated=True)
    output, _provenance = judge.run_consensus(
        {
            "question_id": question_id,
            "question": question,
            "reference_answer": reference_answer,
            "answer": answer.answer,
            "cited_sections": cited_sections,
        },
        dual=dual,
        threshold=threshold,
    )
    accuracy = int(output.get("accuracy", 0))
    completeness = int(output.get("completeness", 0))
    relevance = int(output.get("relevance", 0))
    total = min(10, accuracy + completeness + relevance)
    return QuizScore(question_id, accuracy, completeness, relevance, total)
