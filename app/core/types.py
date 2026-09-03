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
    paper_analyses: list[dict[str, Any]] = field(default_factory=list)  # Step 2: PaperReader
    knowledge_base: dict[str, Any] = field(default_factory=dict)  # Step 3: Organizer
    outline: dict[str, Any] = field(default_factory=dict)  # Step 3: Planner
    draft: str = ""
    claims: list[Claim] = field(default_factory=list)
    citation_map: list[Citation] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)  # Step 4: Verifier
    final_survey: str = ""
