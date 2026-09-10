"""单条样本跑完 D1–D8；单维度失败只影响自身维度。

职责边界：只消费冻结 dataset 与六字段 result.json，
不 import ``app.agents``、不感知 Pipeline 内部。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.model.provider import LLMProvider
from evaluator.aggregate import apply_gate, weighted_score
from evaluator.config import DIMENSIONS, EvalConfig
from evaluator.contract import DimensionResult, EvalReport
from evaluator.dataset import Dataset, TopicCase
from evaluator.evidence.claims import AtomicClaim, build_citation_lookup, extract_claims
from evaluator.evidence.retriever import LexicalRetriever
from evaluator.judges.citation import CitationJudge
from evaluator.judges.coverage import CoverageJudge
from evaluator.judges.factual import FactualJudge
from evaluator.judges.outline import OutlineJudge
from evaluator.judges.quiz_answer import QuizAnswerJudge
from evaluator.judges.readability import ReadabilityJudge
from evaluator.judges.synthesis import SynthesisJudge
from evaluator.judges.terminology import TerminologyJudge
from evaluator.metrics import (
    apply_irrelevant_penalty,
    citation_metrics,
    coverage_score,
    d8_composite,
    factual_score,
    format_score,
    literature_relevance_score,
    mean,
    quiz_dimension_score,
    sub_dimension_score,
    terminology_score,
)
from evaluator.quizzes.answerer import QuizAnswerer, SurveySection
from evaluator.quizzes.scorer import score_answer
from evaluator.rules.format import check_format
from evaluator.rules.metadata import check_literature
from evaluator.textutil import split_chapters, truncate

MAX_SURVEY_CHARS = 30000  # document-level Judge 的输入上限（超长截断）


class EvalRunnerError(RuntimeError):
    """评测输入不合法。"""


@dataclass
class TopicInput:
    """一条评测样本：dataset topic + Application 输出。"""

    case: TopicCase
    payload: dict[str, Any]


def load_run_payload(run_dir: str | Path) -> dict[str, Any]:
    """读取 ``runs/<task_id>/result.json``（六字段输出契约）。"""
    path = Path(run_dir) / "result.json"
    if not path.is_file():
        raise EvalRunnerError(f"运行目录缺少 result.json：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = ("task", "papers", "survey", "claims", "citations", "evidence_map")
    missing = [key for key in required if key not in payload]
    if missing:
        raise EvalRunnerError(f"result.json 缺少必需字段：{missing}")
    return payload


def _normalize_title(title: str) -> str:
    return " ".join(title.strip().lower().split())


class EvalRunner:
    """按维度分发评测；每个维度独立捕获异常。"""

    def __init__(self, dataset: Dataset, config: EvalConfig, llm: LLMProvider, run_id: str) -> None:
        self.dataset = dataset
        self.config = config
        self.run_id = run_id
        model = config.judge.model
        if not model:
            raise EvalRunnerError("judge.model 未配置。")
        cache_dir = config.resolve(config.judge.cache_dir) if config.judge.cache_enabled else None
        self.claim_extractor = _make_extractor(llm, model, config, cache_dir)
        self.judges: dict[str, Any] = {
            "factual": FactualJudge(
                llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir
            ),
            "citation": CitationJudge(
                llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir
            ),
            "coverage": CoverageJudge(
                llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir
            ),
            "synthesis": SynthesisJudge(
                llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir
            ),
            "outline": OutlineJudge(
                llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir
            ),
            "quiz_answer": QuizAnswerJudge(
                llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir
            ),
            "terminology": TerminologyJudge(
                llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir
            ),
            "readability": ReadabilityJudge(
                llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir
            ),
            "quiz_answerer": _make_answerer(llm, model, config, cache_dir),
        }
        self._role_dimensions = {
            "D1": (self.claim_extractor, self.judges["factual"]),
            "D2": (self.judges["citation"],),
            "D3": (self.judges["coverage"],),
            "D4": (self.judges["synthesis"],),
            "D5": (self.judges["outline"],),
            "D6": (self.judges["quiz_answerer"], self.judges["quiz_answer"]),
            "D7": (self.judges["terminology"],),
            "D8": (self.judges["readability"],),
        }

    # --- 对外入口 ---------------------------------------------------------- #

    def run(self, cases: list[TopicInput]) -> EvalReport:
        if not cases:
            raise EvalRunnerError("没有可评测样本。")
        mode = (
            "human_reference"
            if all(case.human_survey_available for case in (item.case for item in cases))
            else "reference_free"
        )
        report = EvalReport(
            run_id=self.run_id,
            method=self.config.method,
            dataset_version=self.dataset.version,
            mode=mode,
            topics=[item.case.id for item in cases],
        )
        topic_results: list[dict[str, Any]] = []
        for item in cases:
            topic_results.append(self._evaluate_topic(item))
        self._merge_topics(report, topic_results)
        report.per_topic = topic_results
        report.cost = self.cost()
        if any(
            result["gate_metrics"].get(key) is None
            for result in topic_results
            for key in ("fabricated_citation_rate", "citation_recall")
        ):
            report.notes.append("部分 gate 指标缺失（D1/D2 未运行或失败），Gate 仅按可用指标应用。")
        return report

    def cost(self) -> dict[str, Any]:
        """按维度汇总 LLM 调用数 / token / latency。"""
        cost: dict[str, Any] = {}
        for dimension, roles in self._role_dimensions.items():
            merged = {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms": 0,
                "errors": 0,
                "cache_hits": 0,
            }
            for role in roles:
                for key, value in role.stats.items():
                    merged[key] = merged.get(key, 0) + value
            if merged["calls"] or merged["cache_hits"]:
                cost[dimension] = merged
        return cost

    def prompt_provenance(self) -> dict[str, dict[str, str]]:
        return {
            self.claim_extractor.prompt.name: self.claim_extractor.prompt.provenance(),
            **{name: judge.prompt.provenance() for name, judge in self.judges.items()},
        }

    # --- 单 topic 全维度 ---------------------------------------------------- #

    def _evaluate_topic(self, item: TopicInput) -> dict[str, Any]:
        case, payload = item.case, item.payload
        survey = str(payload.get("survey") or "")
        citation_lookup = build_citation_lookup(list(payload.get("citations") or []))
        corpus = self._build_corpus(case)
        alias = self._build_alias(payload, case)
        # Claim 抽取一次，D1 / D2 共享
        claims, claim_errors = extract_claims(self.claim_extractor, survey, citation_lookup)

        handlers = {
            "D1": lambda: self._run_d1(case, survey, claims, claim_errors, alias, corpus),
            "D2": lambda: self._run_d2(payload, claims, alias, corpus),
            "D3": lambda: self._run_d3(case, survey),
            "D4": lambda: self._run_d4(case, survey),
            "D5": lambda: self._run_d5(case, survey),
            "D6": lambda: self._run_d6(case, survey),
            "D7": lambda: self._run_d7(survey),
            "D8": lambda: self._run_d8(case, payload, survey),
        }
        results: dict[str, DimensionResult] = {}
        for dimension in DIMENSIONS:
            if dimension not in self.config.dimensions:
                continue
            try:
                results[dimension] = handlers[dimension]()
            except Exception as exc:  # noqa: BLE001 - 单维度失败不影响其它维度
                results[dimension] = DimensionResult(dimension=dimension, error=str(exc))

        d1_result = results.get("D1")
        d2_result = results.get("D2")
        return {
            "topic_id": case.id,
            "topic": case.topic,
            "dimensions": {key: value.to_dict() for key, value in results.items()},
            "gate_metrics": {
                "fabricated_citation_rate": (
                    d2_result.details.get("fabricated_citation_rate") if d2_result else None
                ),
                "citation_recall": d2_result.details.get("recall") if d2_result else None,
                "severe_contradictions": (
                    d1_result.details.get("severe_contradictions") if d1_result else None
                ),
            },
        }

    # --- 各维度实现 --------------------------------------------------------- #

    def _run_d1(
        self,
        case: TopicCase,
        survey: str,
        claims: list[AtomicClaim],
        errors: list[str],
        alias: dict[str, str],
        corpus: LexicalRetriever,
    ) -> DimensionResult:
        judge = self.judges["factual"]
        dual = self._dual("D1")
        claim_results: list[dict[str, Any]] = []
        scores: list[int] = []
        severe = 0
        for claim in claims:
            passages = self._claim_evidence(claim, alias, corpus)
            result: dict[str, Any]
            if not passages:
                result = {
                    "claim_id": claim.claim_id,
                    "label": "NO_SUFFICIENT_INFORMATION",
                    "score": 0,
                    "reason": "Gold Paper 语料中检索不到证据（evidence-gating）。",
                }
            else:
                output, provenance = judge.run_consensus(
                    {
                        "claim_id": claim.claim_id,
                        "claim": claim.text,
                        "citations": claim.citation_ids,
                        "evidence": [
                            {
                                "paper_id": p.paper_id,
                                "section_id": p.section_id,
                                "text": truncate(p.text, 800),
                            }
                            for p in passages
                        ],
                    },
                    dual=dual,
                    threshold=self.config.judge.agree_threshold,
                )
                result = {**output, "provenance": provenance}
            claim_score = int(result.get("score", 0))
            scores.append(claim_score)
            if result.get("label") in ("UNSUPPORTED", "FABRICATED"):
                severe += 1
            claim_results.append(result)

        score = factual_score(scores)
        return DimensionResult(
            dimension="D1",
            score=score,
            low_confidence=bool(errors) and len(errors) > max(1, len(split_chapters(survey)) * 0.3),
            details={
                "n_claims": len(claims),
                "supported": sum(1 for s in scores if s == 2),
                "partial": sum(1 for s in scores if s == 1),
                "unsupported": sum(1 for s in scores if s == 0),
                "severe_contradictions": severe,
                "claim_errors": errors[:10],
                "claims": [r for r in claim_results][:200],
            },
        )

    def _run_d2(
        self,
        payload: dict[str, Any],
        claims: list[AtomicClaim],
        alias: dict[str, str],
        corpus: LexicalRetriever,
    ) -> DimensionResult:
        known = self.dataset.known_paper_ids()
        cited_ids: list[str] = []
        for citation in payload.get("citations") or []:
            if isinstance(citation, dict):
                paper_id = str(citation.get("paper_id") or "")
                if paper_id and paper_id not in cited_ids:
                    cited_ids.append(paper_id)
        for claim in claims:
            for paper_id in claim.citation_ids:
                if paper_id not in cited_ids:
                    cited_ids.append(paper_id)
        fabricated = [paper_id for paper_id in cited_ids if paper_id not in known]
        metadata_mismatches: list[dict[str, str]] = []
        for citation in payload.get("citations") or []:
            if not isinstance(citation, dict):
                continue
            paper_id = str(citation.get("paper_id") or "")
            metadata = self.dataset.metadata(paper_id)
            title = str(citation.get("title") or "").strip()
            if metadata and title and _normalize_title(title) != _normalize_title(metadata.title):
                metadata_mismatches.append({"paper_id": paper_id, "reason": "title mismatch"})
                if paper_id not in fabricated:
                    fabricated.append(paper_id)

        judge = self.judges["citation"]
        dual = self._dual("D2")
        supports: list[int] = []
        pair_results: list[dict[str, Any]] = []
        for claim in claims:
            for paper_id in dict.fromkeys(claim.citation_ids):
                if paper_id in fabricated:
                    supports.append(0)
                    pair_results.append(
                        {
                            "claim_id": claim.claim_id,
                            "citation": paper_id,
                            "support": 0,
                            "reason": "Fabricated citation.",
                        }
                    )
                    continue
                corpus_ids = [alias.get(paper_id, paper_id)]
                passages = corpus.retrieve(
                    claim.text, paper_ids=corpus_ids, top_k=self.config.evidence.top_k
                )
                if not passages:
                    supports.append(0)
                    pair_results.append(
                        {
                            "claim_id": claim.claim_id,
                            "citation": paper_id,
                            "support": 0,
                            "reason": "该论文无可检索证据（evidence-gating）。",
                        }
                    )
                    continue
                metadata = self.dataset.metadata(paper_id)
                output, provenance = judge.run_consensus(
                    {
                        "claim_id": claim.claim_id,
                        "claim": claim.text,
                        "citation": paper_id,
                        "paper": {"title": metadata.title if metadata else ""},
                        "evidence": [
                            {
                                "paper_id": p.paper_id,
                                "section_id": p.section_id,
                                "text": truncate(p.text, 800),
                            }
                            for p in passages
                        ],
                    },
                    dual=dual,
                    threshold=self.config.judge.agree_threshold,
                )
                supports.append(int(output.get("support", 0)))
                pair_results.append({**output, "provenance": provenance})

        worthy = [claim for claim in claims if claim.citation_worthy]
        valid_known = set(known)
        cited_worthy = sum(
            1 for claim in worthy if any(pid in valid_known for pid in claim.citation_ids)
        )
        metrics = citation_metrics(
            supports=supports,
            citation_worthy=len(worthy),
            cited_worthy=cited_worthy,
            fabricated=len(fabricated),
            total_citations=len(cited_ids),
        )
        f1 = metrics["f1"]
        return DimensionResult(
            dimension="D2",
            score=round(f1 * 100, 2) if f1 is not None else None,
            details={
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "fabricated_citation_rate": metrics["fabricated_citation_rate"],
                "fabricated": fabricated,
                "metadata_mismatches": metadata_mismatches,
                "n_pairs": len(supports),
                "n_citation_worthy": len(worthy),
                "pairs": pair_results[:200],
            },
        )

    def _run_d3(self, case: TopicCase, survey: str) -> DimensionResult:
        if not case.units:
            return DimensionResult(dimension="D3", error="dataset 未提供 Key Information Units。")
        judge = self.judges["coverage"]
        units_payload = [
            {
                "id": unit.id,
                "name": unit.name,
                "description": unit.description,
                "importance": unit.importance,
            }
            for unit in case.units
        ]
        unit_best: dict[str, int] = {}
        irrelevant = 0
        total_paragraphs = 0
        for chapter in split_chapters(survey):
            output = judge.run(
                {
                    "topic": case.topic,
                    "units": units_payload,
                    "chapter_title": chapter.title,
                    "chapter_text": truncate(chapter.text, MAX_SURVEY_CHARS),
                }
            )
            for unit in output.get("units", []):
                unit_id = str(unit.get("id") or "")
                score = int(unit.get("score", 0))
                if not unit_id:
                    continue
                unit_best[unit_id] = max(unit_best.get(unit_id, 0), score)
            irrelevant += int(output.get("irrelevant_paragraphs", 0))
            total_paragraphs += int(output.get("total_paragraphs", 0)) or len(chapter.paragraphs())

        units_score = {unit.id: (unit.importance, unit_best.get(unit.id, 0)) for unit in case.units}
        d3_score = coverage_score(units_score)
        penalty_note: str | None = None
        if d3_score is not None:
            rate = irrelevant / total_paragraphs if total_paragraphs else 0.0
            d3_score, penalty_note = apply_irrelevant_penalty(d3_score, rate)
        return DimensionResult(
            dimension="D3",
            score=None if d3_score is None else round(d3_score, 2),
            details={
                "units": {unit.id: unit_best.get(unit.id, 0) for unit in case.units},
                "irrelevant_rate": (irrelevant / total_paragraphs) if total_paragraphs else 0.0,
                "irrelevant_paragraphs": irrelevant,
                "total_paragraphs": total_paragraphs,
                **({"penalty": penalty_note} if penalty_note else {}),
            },
        )

    def _run_d4(self, case: TopicCase, survey: str) -> DimensionResult:
        output, provenance = self.judges["synthesis"].run_consensus(
            {"topic": case.topic, "survey": truncate(survey, MAX_SURVEY_CHARS)},
            dual=self._dual("D4"),
            threshold=self.config.judge.agree_threshold,
        )
        subs = [
            int(output.get(key, 0)) for key in ("taxonomy", "comparison", "evolution", "insight")
        ]
        return DimensionResult(
            dimension="D4",
            score=sub_dimension_score(subs),
            details={
                "sub_dimensions": dict(
                    zip(("taxonomy", "comparison", "evolution", "insight"), subs, strict=True)
                ),
                "reason": output.get("reason", ""),
                "provenance": provenance,
            },
        )

    def _run_d5(self, case: TopicCase, survey: str) -> DimensionResult:
        from evaluator.textutil import headings

        items = headings(survey)
        if not items:
            return DimensionResult(
                dimension="D5", score=0.0, details={"error": "Survey 无任何标题层级。"}
            )
        output, provenance = self.judges["outline"].run_consensus(
            {
                "topic": case.topic,
                "outline": [{"level": level, "title": title} for level, title in items],
            },
            dual=self._dual("D5"),
            threshold=self.config.judge.agree_threshold,
        )
        subs = [
            int(output.get(key, 0))
            for key in ("hierarchy", "logical_progression", "section_function", "outline_relevance")
        ]
        return DimensionResult(
            dimension="D5",
            score=sub_dimension_score(subs),
            details={
                "sub_dimensions": dict(
                    zip(
                        (
                            "hierarchy",
                            "logical_progression",
                            "section_function",
                            "outline_relevance",
                        ),
                        subs,
                        strict=True,
                    )
                ),
                "n_sections": len(items),
                "reason": output.get("reason", ""),
                "provenance": provenance,
            },
        )

    def _run_d6(self, case: TopicCase, survey: str) -> DimensionResult:
        if not case.quizzes:
            return DimensionResult(dimension="D6", error="dataset 未提供 Quiz。")
        sections = [
            SurveySection(
                section_id=f"sec_{index:02d}",
                title=chapter.title,
                text=truncate(chapter.text, MAX_SURVEY_CHARS),
            )
            for index, chapter in enumerate(split_chapters(survey))
        ] or [
            SurveySection(
                section_id="sec_00", title="Document", text=truncate(survey, MAX_SURVEY_CHARS)
            )
        ]
        answerer = self.judges["quiz_answerer"]
        answerer.bind_survey(sections)
        judge = self.judges["quiz_answer"]
        dual = self._dual("D6")

        per_question: list[dict[str, Any]] = []
        layers: dict[str, list[float]] = {"easy": [], "medium": [], "hard": [], "topic": []}
        for quiz in case.quizzes:
            answer = answerer.answer(quiz.id, quiz.question, top_k=self.config.quiz.section_top_k)
            score = score_answer(
                judge,
                question_id=quiz.id,
                question=quiz.question,
                reference_answer=quiz.reference_answer,
                answer=answer,
                cited_sections=answer.used_sections,
                evidence_gating=self.config.quiz.evidence_gating,
                dual=dual,
                threshold=self.config.judge.agree_threshold,
            )
            if quiz.category == "general":
                layer = quiz.difficulty.lower()
                if layer in layers:
                    layers[layer].append(float(score.total))
            else:
                layers["topic"].append(float(score.total))
            per_question.append(
                {
                    "id": quiz.id,
                    "category": quiz.category,
                    "difficulty": quiz.difficulty,
                    "answer": truncate(answer.answer, 500),
                    "used_sections": answer.used_sections,
                    "unanswered": answer.unanswered,
                    "accuracy": score.accuracy,
                    "completeness": score.completeness,
                    "relevance": score.relevance,
                    "total": score.total,
                    "gated": score.gated,
                }
            )

        general_only = [
            float(entry["total"]) for entry in per_question if entry["category"] == "general"
        ]
        topic_only = [
            float(entry["total"]) for entry in per_question if entry["category"] == "topic_specific"
        ]
        d6_score = quiz_dimension_score(
            general_only,
            topic_only,
            general_weight=self.config.quiz.general_weight,
            topic_weight=self.config.quiz.topic_weight,
        )
        return DimensionResult(
            dimension="D6",
            score=None if d6_score is None else round(d6_score, 2),
            details={
                "n_questions": len(per_question),
                "unanswered": sum(1 for q in per_question if q["unanswered"]),
                "gated": sum(1 for q in per_question if q["gated"]),
                "layers": {
                    key: (round(sum(values) / len(values) * 10, 2) if values else None)
                    for key, values in layers.items()
                },
                "questions": per_question,
            },
        )

    def _run_d7(self, survey: str) -> DimensionResult:
        chapters = split_chapters(survey)
        if not chapters:
            return DimensionResult(dimension="D7", error="Survey 无正文内容。")
        judge = self.judges["terminology"]
        severe = moderate = minor = 0
        words = 0
        issues: list[dict[str, str]] = []
        low_confidence = False
        for chapter in chapters:
            output = judge.run(
                {
                    "chapter_title": chapter.title,
                    "chapter_text": truncate(chapter.text, MAX_SURVEY_CHARS),
                }
            )
            severe += int(output.get("severe", 0))
            moderate += int(output.get("moderate", 0))
            minor += int(output.get("minor", 0))
            words += chapter.words
            issues.extend(output.get("issues", [])[:20])
            if output.get("warning"):
                low_confidence = True
        return DimensionResult(
            dimension="D7",
            score=terminology_score(severe, moderate, minor, words),
            low_confidence=low_confidence,
            details={
                "severe": severe,
                "moderate": moderate,
                "minor": minor,
                "words": words,
                "issues": issues[:100],
            },
        )

    def _run_d8(self, case: TopicCase, payload: dict[str, Any], survey: str) -> DimensionResult:
        citations = [c for c in payload.get("citations") or [] if isinstance(c, dict)]
        stats = check_literature(
            citations,
            survey,
            gold_papers=set(case.gold_papers),
            pool_papers=set(case.benchmark_pool) | set(case.human_reference_set),
        )
        literature = literature_relevance_score(list(stats.relevance.values()))

        output, provenance = self.judges["readability"].run_consensus(
            {"survey": truncate(survey, MAX_SURVEY_CHARS)},
            dual=self._dual("D8"),
            threshold=self.config.judge.agree_threshold,
        )
        readability = float(output.get("score", 0)) / 4.0 * 100.0

        citation_ids = [str(c.get("citation_id") or "") for c in citations]
        fmt = check_format(survey, citation_ids)
        format_result = format_score(int(fmt["passed"]), int(fmt["total"]))

        composite = d8_composite(literature, readability, format_result)
        return DimensionResult(
            dimension="D8",
            score=None if composite is None else round(composite, 2),
            details={
                "literature_relevance": literature,
                "readability": readability,
                "format": format_result,
                "format_issues": fmt["issues"],
                "duplicates": stats.duplicates,
                "concentration": round(stats.concentration, 4),
                "notes": stats.notes,
                "provenance": provenance,
            },
        )

    # --- 辅助 --------------------------------------------------------------- #

    def _dual(self, dimension: str) -> bool:
        return self.config.judge.dual_judge and dimension in self.config.judge.dual_judge_dimensions

    def _build_corpus(self, case: TopicCase) -> LexicalRetriever:
        fulltexts = [
            fulltext
            for paper_id in case.gold_papers
            if (fulltext := self.dataset.fulltext(paper_id)) is not None
        ]
        return LexicalRetriever.from_fulltexts(
            fulltexts, max_passage_chars=self.config.evidence.max_passage_chars
        )

    def _build_alias(self, payload: dict[str, Any], case: TopicCase) -> dict[str, str]:
        """运行产物论文 ID → 数据集论文 ID（优先直接命中，其次标题匹配）。"""
        alias: dict[str, str] = {}
        titles: dict[str, str] = {}
        for paper_id in case.gold_papers:
            metadata = self.dataset.metadata(paper_id)
            if metadata and metadata.title:
                titles[_normalize_title(metadata.title)] = paper_id
        for paper in payload.get("papers") or []:
            if not isinstance(paper, dict):
                continue
            paper_id = str(paper.get("paper_id") or "")
            title = str(paper.get("title") or "")
            if not paper_id:
                continue
            if paper_id in titles.values() or self.dataset.metadata(paper_id) is not None:
                alias[paper_id] = paper_id
            elif title and _normalize_title(title) in titles:
                alias[paper_id] = titles[_normalize_title(title)]
        return alias

    def _claim_evidence(
        self,
        claim: AtomicClaim,
        alias: dict[str, str],
        corpus: LexicalRetriever,
    ):
        paper_ids = [alias.get(pid, pid) for pid in claim.citation_ids if alias.get(pid, pid)]
        if paper_ids:
            passages = corpus.retrieve(
                claim.text, paper_ids=paper_ids, top_k=self.config.evidence.top_k
            )
            if passages:
                return passages
        return corpus.retrieve(claim.text, top_k=self.config.evidence.top_k)

    # --- 跨 topic 聚合 ------------------------------------------------------ #

    def _merge_topics(self, report: EvalReport, topic_results: list[dict[str, Any]]) -> None:
        for dimension in DIMENSIONS:
            if dimension not in self.config.dimensions:
                continue
            scores = [
                result["dimensions"][dimension]["score"]
                for result in topic_results
                if result["dimensions"].get(dimension, {}).get("score") is not None
            ]
            errors = [
                result["dimensions"][dimension].get("error", "")
                for result in topic_results
                if result["dimensions"].get(dimension, {}).get("error")
            ]
            average = mean([float(s) for s in scores]) if scores else None
            report.dimensions[dimension] = DimensionResult(
                dimension=dimension,
                score=None if average is None else round(average, 2),
                details={
                    "per_topic": {
                        result["topic_id"]: result["dimensions"].get(dimension, {}).get("score")
                        for result in topic_results
                    }
                },
                error="; ".join(errors)[:500],
            )

        fabricated_total = sum(
            1
            for result in topic_results
            if result["gate_metrics"].get("fabricated_citation_rate") is not None
        )
        report.gate = {
            "fabricated_citation_rate": (
                mean(
                    [
                        float(result["gate_metrics"]["fabricated_citation_rate"])
                        for result in topic_results
                        if result["gate_metrics"].get("fabricated_citation_rate") is not None
                    ]
                )
                if fabricated_total
                else None
            ),
            "citation_recall": self._mean_gate(topic_results, "citation_recall"),
            "severe_contradictions": self._sum_gate(topic_results, "severe_contradictions"),
        }
        aggregate_scores = report.scores()
        try:
            raw, missing = weighted_score(aggregate_scores, self.config.weights)
            final, reasons = apply_gate(raw, report.gate)
        except Exception as exc:  # noqa: BLE001 - 聚合失败保留维度分数
            report.notes.append(f"聚合失败：{exc}")
            report.missing_dimensions = [
                key for key, value in aggregate_scores.items() if value is None
            ]
            return
        report.raw_score = round(raw, 2)
        report.final_score = round(final, 2)
        report.gate_reasons = reasons
        report.missing_dimensions = missing
        if missing:
            report.notes.append(f"缺失维度已按剩余权重归一化：{missing}")

    @staticmethod
    def _mean_gate(topic_results: list[dict[str, Any]], key: str) -> float | None:
        values = [
            float(result["gate_metrics"][key])
            for result in topic_results
            if result["gate_metrics"].get(key) is not None
        ]
        return mean(values) if values else None

    @staticmethod
    def _sum_gate(topic_results: list[dict[str, Any]], key: str) -> int | None:
        values = [
            int(result["gate_metrics"][key])
            for result in topic_results
            if result["gate_metrics"].get(key) is not None
        ]
        return sum(values) if values else None


def _make_extractor(llm: LLMProvider, model: str, config: EvalConfig, cache_dir: Path | None):
    from evaluator.evidence.claims import ClaimExtractor

    return ClaimExtractor(llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir)


def _make_answerer(llm: LLMProvider, model: str, config: EvalConfig, cache_dir: Path | None):
    return QuizAnswerer(llm, model, max_tokens=config.judge.max_tokens, cache_dir=cache_dir)
