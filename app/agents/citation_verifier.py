"""Citation Verifier（Step 4）：核验 Survey Claim 是否被 Source Paper 证据支持。

设计要点：
    1. 核验链路 `Claim → Citation → Paper → Evidence → 比较`，只注入被引论文的
       定位证据（最小必要 Context），不做引用格式检查。
    2. 按 `max_claims_per_call` 分批调用；单批失败只把该批 Claim 标记为
       unverifiable，绝不中断整体流程（核验是非关键 Stage，允许降级）。
    3. Claim → 论文引用同时接受 `P001`（论文 ID）与 `[1]`（正文编号）两种形式。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.config import ModelConfig
from app.core.types import (
    Citation,
    Claim,
    PaperAnalysis,
    PaperSet,
    Verification,
    VerificationResult,
)
from app.io.render import render_verification_context
from app.model.provider import LLMProvider, Message
from app.prompts.loader import PromptLoader

SYSTEM_INSTRUCTION = (
    "你是严格遵守结构化输出约束的助手。"
    "只输出符合用户给定 Output Schema 的 JSON 对象，不要输出解释性文字或 Markdown 代码块标记。"
)


@dataclass
class VerifierConfig:
    """Citation Verifier 运行参数。"""

    prompt_name: str = "citation_verifier"
    max_claims_per_call: int = 10
    max_claims_per_paper: int = 5
    max_chars_per_evidence: int = 200


class CitationVerifier:
    """把 Writer 产出的 Claim 与 Source Paper 证据比对，产出 Verification。"""

    def __init__(
        self,
        llm: LLMProvider,
        prompts: PromptLoader,
        model: ModelConfig,
        config: VerifierConfig | None = None,
    ) -> None:
        self.llm = llm
        self.prompts = prompts
        self.model = model
        self.config = config or VerifierConfig()

    def build_messages(
        self,
        claims: list[Claim],
        citation_map: list[Citation],
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> list[Message]:
        """为一批 Claim 渲染核验 Prompt：Claim + 被引论文的定位证据。"""
        rendered = self.prompts.render(
            self.config.prompt_name,
            claims_context=render_verification_context(
                claims,
                citation_map,
                analyses,
                papers,
                max_claims_per_paper=self.config.max_claims_per_paper,
                max_chars_per_evidence=self.config.max_chars_per_evidence,
            ),
        )
        return [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": rendered},
        ]

    def verify(
        self,
        claims: list[Claim],
        citation_map: list[Citation],
        analyses: list[PaperAnalysis],
        papers: PaperSet,
    ) -> Verification:
        """分批核验全部 Claim；单批失败降级为 unverifiable，不向上抛出。"""
        if not claims:
            return Verification()

        resolve = build_citation_resolver(citation_map, papers.ids())
        size = max(1, self.config.max_claims_per_call)
        chunks = [claims[index : index + size] for index in range(0, len(claims), size)]

        results: list[VerificationResult] = []
        dropped = 0
        errors: list[str] = []
        for chunk in chunks:
            try:
                messages = self.build_messages(chunk, citation_map, analyses, papers)
                payload = self.llm.generate_json(
                    messages,
                    self.model.name,
                    self.model.temperature,
                    self.model.max_tokens,
                    top_p=self.model.top_p,
                )
                verification = Verification.from_dict(
                    payload,
                    known_claims={claim.claim_id for claim in chunk},
                    resolve_citation=resolve,
                )
            except Exception as exc:  # noqa: BLE001 - 单批失败必须可恢复
                errors.append(f"{type(exc).__name__}: {exc}")
                verification = _unverified_chunk(chunk)
            results.extend(verification.results)
            dropped += verification.dropped

        results = _fill_unassessed(claims, results, resolve)
        results = _order_results(claims, results)
        return Verification(results=results, dropped=dropped, error="; ".join(errors))


def build_citation_resolver(
    citation_map: list[Citation], known_ids: set[str]
) -> Callable[[object], str]:
    """构造引用解析器：`P001` 直接返回；`[1]` 经 citation_map 映射；其余返回空。"""
    citation_to_paper = {citation.citation_id: citation.paper_id for citation in citation_map}

    def resolve(value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        candidate = text[1:-1] if text.startswith("[") and text.endswith("]") else text
        candidate = candidate.strip()
        if candidate in known_ids:
            return candidate
        return citation_to_paper.get(text, citation_to_paper.get(candidate, ""))

    return resolve


def _unverified_chunk(chunk: list[Claim]) -> Verification:
    """把一批核验失败的 Claim 标记为 unverifiable。"""
    return Verification(
        results=[
            VerificationResult(
                claim_id=claim.claim_id,
                citation=claim.citations[0] if claim.citations else "",
                support=None,
                error="核验调用失败",
            )
            for claim in chunk
        ]
    )


def _fill_unassessed(
    claims: list[Claim],
    results: list[VerificationResult],
    resolve: Callable[[object], str],
) -> list[VerificationResult]:
    """模型漏掉的 Claim 补一条 unverifiable 结果，保证 summary 覆盖全部 Claim。"""
    covered: dict[str, set[str]] = {}
    for result in results:
        covered.setdefault(result.claim_id, set()).add(result.citation)
    filled = list(results)
    for claim in claims:
        cited = {resolve(ref) for ref in claim.citations} if claim.citations else set()
        cited.discard("")
        seen = covered.get(claim.claim_id, set())
        if not claim.citations:
            if claim.claim_id not in covered:
                filled.append(
                    VerificationResult(
                        claim_id=claim.claim_id, citation="", error="无引用，无法核验"
                    )
                )
            continue
        for paper_id in sorted(cited - seen):
            filled.append(
                VerificationResult(
                    claim_id=claim.claim_id,
                    citation=paper_id,
                    support=None,
                    error="模型未核验该引用",
                )
            )
    return filled


def _order_results(
    claims: list[Claim], results: list[VerificationResult]
) -> list[VerificationResult]:
    """按输入 Claim 顺序与其 citations 顺序稳定排序，便于人工核对与追溯。"""
    claim_index = {claim.claim_id: index for index, claim in enumerate(claims)}
    citation_index = {
        claim.claim_id: {ref: order for order, ref in enumerate(claim.citations)}
        for claim in claims
    }

    def key(result: VerificationResult) -> tuple[int, int]:
        return (
            claim_index.get(result.claim_id, len(claim_index)),
            citation_index.get(result.claim_id, {}).get(result.citation, len(claim_index)),
        )

    return sorted(results, key=key)
