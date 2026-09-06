"""Application 数据模型。

字段定义与命名约定见
``.codebuddy/skills/hy-surveyagent-app/references/data-contracts.md``。
ID 在整条链路中保持稳定：P001（论文）、C001（Survey Claim）、[1]（正文引用编号）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _as_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [_as_str(item) for item in value if _as_str(item)]
    return [_as_str(value)]


def _obj_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_support(value: Any) -> bool | None:
    """归一化 support：布尔 / 常见字符串表述 / 0-1 数字；无法识别视为证据不足。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "supported", "yes", "1"):
        return True
    if text in ("false", "unsupported", "no", "0"):
        return False
    return None


def _as_confidence(value: Any) -> float:
    """归一化 confidence 到 [0, 1]；缺失或非法值返回 0。"""
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _as_year(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip()[:4])
    except (TypeError, ValueError):
        return None


@dataclass
class Paper:
    """Source Paper 的归一化表示。"""

    paper_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    content: str = ""
    source: str = ""
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str | None = None) -> Paper:
        return cls(
            paper_id=_as_str(data.get("paper_id") or fallback_id),
            title=_as_str(data.get("title")),
            authors=_as_list(data.get("authors")),
            year=_as_year(data.get("year")),
            abstract=_as_str(data.get("abstract")),
            content=_as_str(data.get("content")),
            source=_as_str(data.get("source") or data.get("venue") or data.get("url")),
        )

    def label(self) -> str:
        """用于 References 与 Prompt 的可读标题。"""
        return f"{self.title} ({self.year})" if self.year else self.title


@dataclass
class PaperSet:
    """论文集合。Benchmark 模式下由固定 Source Paper Set 构造。"""

    papers: list[Paper] = field(default_factory=list)
    duplicates_removed: int = 0
    filtered_out: int = 0

    def __len__(self) -> int:
        return len(self.papers)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.papers)

    def ids(self) -> set[str]:
        return {paper.paper_id for paper in self.papers}

    def get(self, paper_id: str) -> Paper | None:
        for paper in self.papers:
            if paper.paper_id == paper_id:
                return paper
        return None


@dataclass
class PaperClaim:
    """论文内部抽取的一条论断，ID 形如 `P001-C1`。

    `evidence` 保留论文中的原始依据，供 Step 4 的 Citation Verifier 比对。
    """

    claim_id: str = ""
    text: str = ""
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaperAnalysis:
    """Paper Reader 输出：单篇论文的统一结构化表示（Step 2）。

    字段与取值见 data-contracts 第 4 节。抽取内容必须来自论文正文，
    缺失时留空，禁止由模型补全。
    """

    STATUS_OK = "ok"
    STATUS_UNAVAILABLE = "unavailable"

    paper_id: str = ""
    problem: str = ""
    motivation: str = ""
    method: str = ""
    architecture: str = ""
    dataset: list[str] = field(default_factory=list)
    experiments: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    key_idea: str = ""
    advantages: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    claims: list[PaperClaim] = field(default_factory=list)
    status: str = STATUS_OK
    error: str = ""

    @property
    def available(self) -> bool:
        return self.status == self.STATUS_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "problem": self.problem,
            "motivation": self.motivation,
            "method": self.method,
            "architecture": self.architecture,
            "dataset": list(self.dataset),
            "experiments": list(self.experiments),
            "results": list(self.results),
            "key_idea": self.key_idea,
            "advantages": list(self.advantages),
            "limitations": list(self.limitations),
            "claims": [claim.to_dict() for claim in self.claims],
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def unavailable(cls, paper_id: str, error: str = "") -> PaperAnalysis:
        """构造读取失败的分析结果：单篇失败不得中断整体流程。"""
        return cls(paper_id=paper_id, status=cls.STATUS_UNAVAILABLE, error=error)

    @classmethod
    def from_dict(cls, data: dict[str, Any], paper_id: str = "") -> PaperAnalysis:
        resolved = _as_str(data.get("paper_id") or paper_id)
        claims: list[PaperClaim] = []
        for item in _obj_list(data.get("claims")):
            text = _as_str(item.get("text"))
            if not text:
                continue
            claims.append(
                PaperClaim(
                    claim_id=f"{resolved}-C{len(claims) + 1}",
                    text=text,
                    evidence=_as_str(item.get("evidence")),
                )
            )
        return cls(
            paper_id=resolved,
            problem=_as_str(data.get("problem")),
            motivation=_as_str(data.get("motivation")),
            method=_as_str(data.get("method")),
            architecture=_as_str(data.get("architecture")),
            dataset=_as_list(data.get("dataset")),
            experiments=_as_list(data.get("experiments")),
            results=_as_list(data.get("results")),
            key_idea=_as_str(data.get("key_idea")),
            advantages=_as_list(data.get("advantages")),
            limitations=_as_list(data.get("limitations")),
            claims=claims,
        )


VALID_RELATIONS = ("extends", "compares", "solves", "uses_dataset", "evaluates_on")


@dataclass
class PaperGroup:
    """按主题 / 方法 / 问题 / 数据集聚合的论文分组。"""

    name: str
    papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "papers": list(self.papers)}


@dataclass
class PaperRelation:
    """论文间关系（如 P001 extends P002）。"""

    source: str
    relation: str
    target: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "relation": self.relation, "target": self.target}


@dataclass
class KnowledgeBase:
    """Knowledge Organizer 输出：跨论文的研究领域知识结构（Step 3）。

    第一版用 Python 对象 / JSON 表示，不引入图数据库。
    """

    topics: list[str] = field(default_factory=list)
    methods: list[PaperGroup] = field(default_factory=list)
    problems: list[PaperGroup] = field(default_factory=list)
    datasets: list[PaperGroup] = field(default_factory=list)
    papers: list[str] = field(default_factory=list)
    relations: list[PaperRelation] = field(default_factory=list)
    dropped: int = 0

    @property
    def is_empty(self) -> bool:
        """没有任何分组、关系或主题时视为空知识结构。"""
        return not (self.topics or self.methods or self.problems or self.datasets or self.relations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topics": list(self.topics),
            "methods": [group.to_dict() for group in self.methods],
            "problems": [group.to_dict() for group in self.problems],
            "datasets": [group.to_dict() for group in self.datasets],
            "papers": list(self.papers),
            "relations": [relation.to_dict() for relation in self.relations],
            "dropped": self.dropped,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        known_ids: set[str],
        default_papers: list[str] | None = None,
    ) -> KnowledgeBase:
        """归一化：丢弃空名分组与指向未知论文的条目，同名分组只保留第一条。"""
        dropped = 0
        topics = [item for item in _as_list(data.get("topics")) if item]

        def _groups(key: str) -> tuple[list[PaperGroup], int]:
            groups: list[PaperGroup] = []
            seen: set[str] = set()
            count = 0
            for item in _obj_list(data.get(key)):
                name = _as_str(item.get("name"))
                papers = [pid for pid in _as_list(item.get("papers")) if pid in known_ids]
                if not name or not papers:
                    count += 1
                    continue
                key_lower = name.lower()
                if key_lower in seen:
                    count += 1
                    continue
                seen.add(key_lower)
                groups.append(PaperGroup(name=name, papers=papers))
            return groups, count

        methods, n = _groups("methods")
        dropped += n
        problems, n = _groups("problems")
        dropped += n
        datasets, n = _groups("datasets")
        dropped += n

        relations: list[PaperRelation] = []
        for item in _obj_list(data.get("relations")):
            source = _as_str(item.get("source"))
            target = _as_str(item.get("target"))
            relation = _as_str(item.get("relation")).lower()
            if (
                source == target
                or source not in known_ids
                or target not in known_ids
                or relation not in VALID_RELATIONS
            ):
                dropped += 1
                continue
            relations.append(PaperRelation(source=source, relation=relation, target=target))

        papers = [pid for pid in _as_list(data.get("papers")) if pid in known_ids]
        return cls(
            topics=topics,
            methods=methods,
            problems=problems,
            datasets=datasets,
            papers=papers or list(default_papers or []),
            relations=relations,
            dropped=dropped,
        )


@dataclass
class OutlineSection:
    """Survey 的一个章节规划：Purpose + Relevant Papers + Key Claims。"""

    title: str
    purpose: str = ""
    papers: list[str] = field(default_factory=list)
    key_claims: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "purpose": self.purpose,
            "papers": list(self.papers),
            "key_claims": list(self.key_claims),
        }


@dataclass
class Outline:
    """Outline Planner 输出（Step 3）。

    每个 Section 必须同时具备 purpose 与 papers，否则视为非法并丢弃；
    key_claims 只保留指向真实论文级 Claim 的引用。
    """

    sections: list[OutlineSection] = field(default_factory=list)
    dropped: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sections": [section.to_dict() for section in self.sections],
            "dropped": self.dropped,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        known_ids: set[str],
        known_claims: set[str] | None = None,
    ) -> Outline:
        allowed_claims = known_claims or set()
        sections: list[OutlineSection] = []
        seen_titles: set[str] = set()
        dropped = 0
        for item in _obj_list(data.get("sections")):
            title = _as_str(item.get("title"))
            purpose = _as_str(item.get("purpose"))
            papers = [pid for pid in _as_list(item.get("papers")) if pid in known_ids]
            if not title or not purpose or not papers:
                dropped += 1
                continue
            key_lower = title.lower()
            if key_lower in seen_titles:
                dropped += 1
                continue
            seen_titles.add(key_lower)
            key_claims = [
                claim for claim in _as_list(item.get("key_claims")) if claim in allowed_claims
            ]
            sections.append(
                OutlineSection(title=title, purpose=purpose, papers=papers, key_claims=key_claims)
            )
        return cls(sections=sections, dropped=dropped)


@dataclass
class TaskInput:
    """任务输入。Benchmark 模式下论文集合由 --papers 指定，不依赖实时检索。"""

    topic: str = ""
    research_questions: list[str] = field(default_factory=list)
    paper_ids: list[str] = field(default_factory=list)
    time_range: dict[str, int] | None = None
    output_style: str = "academic_survey"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Claim:
    """Survey 中的一条论断，必须绑定真实存在的论文。"""

    claim_id: str
    text: str
    citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Citation:
    """正文引用编号与论文的映射。"""

    citation_id: str
    paper_id: str
    title: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    """单条 Claim 对单个被引论文的核验结果（Step 4）。

    `support` 取值：True（证据支持）/ False（证据矛盾）/ None（证据不足，无法判定）。
    """

    claim_id: str
    citation: str
    support: bool | None = None
    evidence: str = ""
    confidence: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "citation": self.citation,
            "support": self.support,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "error": self.error,
        }


@dataclass
class Verification:
    """Citation Verifier 输出：Claim → Citation → Paper → Evidence 的核验链路。

    每条 Claim 至少产生一条结果（无引用的 Claim 记一条 `citation=""` 的
    unverifiable 结果），保证 `summary.total_claims` 覆盖全部待核验 Claim。
    """

    results: list[VerificationResult] = field(default_factory=list)
    dropped: int = 0
    error: str = ""

    def summary(self) -> dict[str, int]:
        """按 Claim 聚合 supported / unsupported / unverifiable 三类计数。"""
        by_claim: dict[str, list[VerificationResult]] = {}
        for result in self.results:
            by_claim.setdefault(result.claim_id, []).append(result)
        supported = sum(
            1 for entries in by_claim.values() if all(r.support is True for r in entries)
        )
        unsupported = sum(
            1 for entries in by_claim.values() if any(r.support is False for r in entries)
        )
        return {
            "total_claims": len(by_claim),
            "supported": supported,
            "unsupported": unsupported,
            "unverifiable": len(by_claim) - supported - unsupported,
        }

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "results": [result.to_dict() for result in self.results],
            "summary": self.summary(),
        }
        if self.error:
            payload["error"] = self.error
        return payload

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        known_claims: set[str],
        resolve_citation: Any,
    ) -> Verification:
        """归一化模型输出：丢弃未知 Claim 与无法解析的引用并计数。

        `resolve_citation(value)` 把模型给出的引用（论文 ID 或正文编号 `[n]`）
        解析为 `paper_id`，解析失败返回空字符串（结果保留但标记 error）。
        """
        dropped = 0
        results: list[VerificationResult] = []
        for item in _obj_list(data.get("results")):
            claim_id = _as_str(item.get("claim_id"))
            if claim_id not in known_claims:
                dropped += 1
                continue
            citation = resolve_citation(item.get("citation"))
            if not citation and _as_str(item.get("citation")):
                dropped += 1
                continue
            evidence = _as_str(item.get("evidence"))
            results.append(
                VerificationResult(
                    claim_id=claim_id,
                    citation=citation,
                    support=_as_support(item.get("support")),
                    evidence=evidence,
                    confidence=_as_confidence(item.get("confidence")),
                )
            )
        return cls(results=results, dropped=dropped)

    @classmethod
    def unverified(cls, claims: list[Claim], error: str = "", reason: str = "") -> Verification:
        """构造全部 Claim 均不可核验的降级结果（核验被禁用或整体失败时使用）。"""
        results = [
            VerificationResult(
                claim_id=claim.claim_id,
                citation=claim.citations[0] if claim.citations else "",
                support=None,
                error=reason or "未执行核验",
            )
            for claim in claims
        ]
        return cls(results=results, error=error)


@dataclass
class WriterOutput:
    """Survey Writer 的产物。"""

    survey_markdown: str = ""
    claims: list[Claim] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    unknown_citations: list[str] = field(default_factory=list)  # 正文中无法映射的编号，交给核验阶段

    def to_dict(self) -> dict[str, Any]:
        return {
            "survey_markdown": self.survey_markdown,
            "claims": [claim.to_dict() for claim in self.claims],
            "citations": [citation.to_dict() for citation in self.citations],
            "unknown_citations": list(self.unknown_citations),
        }


@dataclass
class SurveyState:
    """跨 Stage 传递的统一执行状态。Step 2 起逐步填充后续字段。"""

    task: TaskInput | None = None
    task_spec: dict[str, Any] = field(default_factory=dict)  # Step 2: TaskSpec
    papers: list[Paper] = field(default_factory=list)
    paper_analyses: list[PaperAnalysis] = field(default_factory=list)  # Step 2: PaperReader
    knowledge_base: KnowledgeBase = field(default_factory=KnowledgeBase)  # Step 3: Organizer
    outline: Outline = field(default_factory=Outline)  # Step 3: Planner
    draft: str = ""
    claims: list[Claim] = field(default_factory=list)
    citation_map: list[Citation] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)  # Step 4: Verifier
    final_survey: str = ""
