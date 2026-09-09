"""词法证据检索：Claim → Gold Paper 语料 → top-k 段落。

确定性 BM25 式打分（IDF × 词频饱和），不依赖外部检索服务，
也绝不使用模型参数知识替代检索；检索结果为空时上层必须判 UNSUPPORTED。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from evaluator.dataset import PaperFulltext

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_SMOOTHING = 1.2  # 词频饱和参数


@dataclass
class EvidencePassage:
    paper_id: str
    section_id: str
    text: str
    score: float = 0.0


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def build_corpus(
    fulltexts: list[PaperFulltext],
    *,
    max_passage_chars: int = 1200,
) -> list[EvidencePassage]:
    """把论文全文展开成可检索的段落列表（保持文档顺序）。"""
    passages: list[EvidencePassage] = []
    for fulltext in fulltexts:
        for section_id, _title, passage in fulltext.passages(max_passage_chars):
            passages.append(
                EvidencePassage(paper_id=fulltext.paper_id, section_id=section_id, text=passage)
            )
    return passages


class LexicalRetriever:
    """确定性词法检索器。"""

    def __init__(self, passages: list[EvidencePassage]) -> None:
        self.passages = passages
        self._tokens = [tokenize(passage.text) for passage in passages]
        document_frequency: dict[str, int] = {}
        for tokens in self._tokens:
            for term in set(tokens):
                document_frequency[term] = document_frequency.get(term, 0) + 1
        total = max(1, len(passages))
        self._idf = {
            term: math.log(1.0 + total / count) for term, count in document_frequency.items()
        }

    @classmethod
    def from_fulltexts(
        cls,
        fulltexts: list[PaperFulltext],
        *,
        max_passage_chars: int = 1200,
    ) -> LexicalRetriever:
        return cls(build_corpus(fulltexts, max_passage_chars=max_passage_chars))

    def retrieve(
        self,
        query: str,
        *,
        paper_ids: list[str] | None = None,
        top_k: int = 5,
    ) -> list[EvidencePassage]:
        """返回按 (score 降序, 原始顺序) 排列的 top-k 段落；只返回 score>0 的结果。"""
        wanted = set(paper_ids) if paper_ids else None
        query_terms = set(tokenize(query))
        if not query_terms:
            return []
        scored: list[tuple[float, int, EvidencePassage]] = []
        for index, (passage, tokens) in enumerate(zip(self.passages, self._tokens, strict=True)):
            if wanted is not None and passage.paper_id not in wanted:
                continue
            frequency: dict[str, int] = {}
            for term in tokens:
                frequency[term] = frequency.get(term, 0) + 1
            score = 0.0
            for term in query_terms:
                count = frequency.get(term, 0)
                if count and term in self._idf:
                    score += self._idf[term] * (count / (count + _SMOOTHING))
            if score > 0:
                scored.append((score, index, passage))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            EvidencePassage(
                paper_id=item[2].paper_id,
                section_id=item[2].section_id,
                text=item[2].text,
                score=item[0],
            )
            for item in scored[:top_k]
        ]

    def __len__(self) -> int:
        return len(self.passages)
