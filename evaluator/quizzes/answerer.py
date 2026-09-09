"""Quiz 作答：Section Retrieval → Survey-only 作答 → 引用段落。

作答协议（eval_protocol.md 第 10.5 节，强制）：
- 先按问题检索 Survey 小节，检索为空时直接 NO_SUFFICIENT_INFORMATION（不调 LLM）；
- Answerer 只能依据检索到的 Survey 内容回答，禁止使用外部知识；
- 输出必须引用使用的 section id，供 evidence-gating 校验。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evaluator.evidence.retriever import EvidencePassage, LexicalRetriever
from evaluator.judges.base import BaseJudge

NO_SUFFICIENT_INFORMATION = "NO_SUFFICIENT_INFORMATION"


@dataclass
class SurveySection:
    section_id: str
    title: str
    text: str


@dataclass
class QuizAnswer:
    question_id: str
    answer: str
    used_sections: list[str] = field(default_factory=list)

    @property
    def unanswered(self) -> bool:
        return self.answer.strip() == NO_SUFFICIENT_INFORMATION


class QuizAnswerer(BaseJudge):
    """Survey-only 作答者。"""

    prompt_name = "quiz_answerer"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.retriever: LexicalRetriever | None = None

    def bind_survey(self, sections: list[SurveySection]) -> None:
        """按 Survey 小节构建检索语料（每次评测绑定一次）。"""
        passages = [
            EvidencePassage(
                paper_id="survey",
                section_id=section.section_id,
                text=f"{section.title}\n{section.text}" if section.title else section.text,
            )
            for section in sections
        ]
        self.retriever = LexicalRetriever(passages)

    def answer(self, question_id: str, question: str, *, top_k: int = 4) -> QuizAnswer:
        if self.retriever is None:
            return QuizAnswer(question_id=question_id, answer=NO_SUFFICIENT_INFORMATION)
        hits = self.retriever.retrieve(question, top_k=top_k)
        if not hits:
            # evidence-gating：Survey 中检索不到相关内容时不得作答
            return QuizAnswer(question_id=question_id, answer=NO_SUFFICIENT_INFORMATION)
        sections = [{"section_id": hit.section_id, "text": hit.text} for hit in hits]
        output = self.run(
            {
                "question_id": question_id,
                "question": question,
                "survey_sections": sections,
            }
        )
        answer = str(output.get("answer") or "").strip() or NO_SUFFICIENT_INFORMATION
        used = [str(v) for v in output.get("used_sections") or [] if str(v).strip()]
        return QuizAnswer(question_id=question_id, answer=answer, used_sections=used)

    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        answer = parsed.get("answer")
        used = parsed.get("used_sections")
        return {
            "answer": answer if isinstance(answer, str) else "",
            "used_sections": (
                [str(v) for v in used if isinstance(v, str)] if isinstance(used, list) else []
            ),
        }

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"answer": NO_SUFFICIENT_INFORMATION, "used_sections": []}

    def score_of(self, output: dict[str, Any]) -> float:
        return 0.0 if str(output.get("answer") or "").strip() == NO_SUFFICIENT_INFORMATION else 1.0
