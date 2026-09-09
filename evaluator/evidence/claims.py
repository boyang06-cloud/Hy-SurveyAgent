"""Atomic Claim 抽取与 claim↔citation 对齐（D1 / D2 的地基）。

流程：Survey → chapter 切分 → chapter 级 LLM 抽取 → 引用标记解析。
只抽取可验证的 factual / scientific claims，忽略意见性表述。
"""

from __future__ import annotations

from typing import Any

from evaluator.judges.base import BaseJudge
from evaluator.textutil import Chapter, split_chapters

#: 支持的引用标记形态："[1]" / "1" / "[P001]" / "P001"
_MARKERS = ("[{id}]", "{id}", "[[{id}]]")


def build_citation_lookup(citations: list[dict[str, Any]]) -> dict[str, str]:
    """把 result.json 的 citations（citation_id → paper_id）展开成标记查找表。"""
    lookup: dict[str, str] = {}
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        citation_id = str(citation.get("citation_id") or "")
        paper_id = str(citation.get("paper_id") or "")
        if not citation_id or not paper_id:
            continue
        for form in _MARKERS:
            lookup[form.format(id=citation_id)] = paper_id
        if citation_id == paper_id:
            continue
    return lookup


class ClaimExtractor(BaseJudge):
    prompt_name = "claim_extraction"

    def validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        claims_raw = parsed.get("claims")
        claims: list[dict[str, Any]] = []
        if isinstance(claims_raw, list):
            for item in claims_raw:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                citations = item.get("citations")
                if not isinstance(citations, list):
                    citations = []
                claims.append(
                    {
                        "text": text,
                        "citations": [str(v) for v in citations],
                        "citation_worthy": bool(item.get("citation_worthy")),
                    }
                )
        return {"claims": claims}

    def fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"claims": [], "error": "Claim 抽取失败，该章节按无 claim 处理。"}

    def score_of(self, output: dict[str, Any]) -> float:
        return float(len(output.get("claims") or []))


class AtomicClaim:
    """归一化后的 atomic claim（citation 已解析为论文 ID）。"""

    def __init__(
        self,
        claim_id: str,
        text: str,
        citation_ids: list[str],
        citation_worthy: bool,
        section: str,
    ) -> None:
        self.claim_id = claim_id
        self.text = text
        self.citation_ids = citation_ids
        self.citation_worthy = citation_worthy
        self.section = section

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "citations": self.citation_ids,
            "citation_worthy": self.citation_worthy,
            "section": self.section,
        }


def resolve_markers(markers: list[str], lookup: dict[str, str]) -> list[str]:
    """把模型回传的引用标记解析为论文 ID；无法解析的标记丢弃。"""
    resolved: list[str] = []
    for marker in markers:
        token = str(marker).strip()
        if not token:
            continue
        paper_id = lookup.get(token)
        if paper_id is None and token.startswith("[") and token.endswith("]"):
            paper_id = lookup.get(token[1:-1])
        if paper_id is not None and paper_id not in resolved:
            resolved.append(paper_id)
    return resolved


def extract_claims(
    extractor: ClaimExtractor,
    survey_markdown: str,
    citation_lookup: dict[str, str],
) -> tuple[list[AtomicClaim], list[str]]:
    """从 Survey 抽取 atomic claims；返回 (claims, 章节级错误列表)。"""
    claims: list[AtomicClaim] = []
    errors: list[str] = []
    chapters: list[Chapter] = split_chapters(survey_markdown)
    counter = 0
    for chapter in chapters:
        output = extractor.run({"chapter_title": chapter.title, "chapter_text": chapter.text})
        if output.get("error"):
            errors.append(f"[{chapter.title}] {output['error']}")
        for raw in output.get("claims", []):
            counter += 1
            claims.append(
                AtomicClaim(
                    claim_id=f"C{counter:03d}",
                    text=str(raw.get("text") or ""),
                    citation_ids=resolve_markers(list(raw.get("citations") or []), citation_lookup),
                    citation_worthy=bool(raw.get("citation_worthy")),
                    section=chapter.title,
                )
            )
    return claims, errors
