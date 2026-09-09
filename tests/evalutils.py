"""评测侧测试共用工具：路由式 MockProvider、迷你数据集与运行产物构造器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.model.provider import LLMProvider, LLMResponse, Message


class RoutingProvider(LLMProvider):
    """按 Prompt 标识关键字路由响应的 MockProvider（禁止调用真实 Hy3）。"""

    def __init__(self, routes: list[tuple[str, dict[str, Any]]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def generate(
        self,
        messages: list[Message],
        model: str,
        temperature: float,
        max_tokens: int,
        *,
        top_p: float = 1.0,
    ) -> LLMResponse:
        content = str(messages[0]["content"])
        self.calls.append(content)
        for _index, (keyword, response) in enumerate(self.routes):
            if keyword not in content:
                continue
            # list 表示按调用顺序依次消费的响应队列；dict 表示固定响应
            item = response.pop(0) if isinstance(response, list) else response
            return LLMResponse(
                text=json.dumps(item, ensure_ascii=False),
                model=model,
                token_usage={"prompt": 10, "completion": 5},
                latency_ms=1,
            )
        raise AssertionError(f"RoutingProvider 未匹配任何路由：{content[:120]}...")


DEFAULT_ROUTES: list[tuple[str, dict[str, Any]]] = [
    (
        "Atomic Claim Extraction",
        {
            "claims": [
                {
                    "text": "3DGS represents scenes using anisotropic Gaussians",
                    "citations": ["[1]"],
                    "citation_worthy": True,
                },
                {
                    "text": "The tile-based rasterizer improves rendering efficiency",
                    "citations": ["[2]"],
                    "citation_worthy": True,
                },
            ],
        },
    ),
    (
        "Factual Accuracy Judge",
        {
            "claim_id": "",
            "label": "SUPPORTED",
            "score": 2,
            "reason": "Evidence states it directly.",
        },
    ),
    (
        "Citation Correctness Judge",
        {"claim_id": "", "citation": "", "support": 2, "reason": "Direct support in section 3."},
    ),
    (
        "Information Coverage Judge",
        {
            "units": [
                {
                    "id": "u_def",
                    "score": 2,
                    "evidence_span": "3DGS represents scenes using anisotropic Gaussians",
                },
                {
                    "id": "u_render",
                    "score": 2,
                    "evidence_span": "The tile-based rasterizer improves rendering efficiency",
                },
            ],
            "irrelevant_paragraphs": 0,
            "total_paragraphs": 2,
        },
    ),
    (
        "Cross-paper Synthesis Judge",
        {"taxonomy": 4, "comparison": 4, "evolution": 4, "insight": 4, "reason": "ok"},
    ),
    (
        "Outline & Structure Judge",
        {
            "hierarchy": 4,
            "logical_progression": 4,
            "section_function": 4,
            "outline_relevance": 4,
            "reason": "ok",
        },
    ),
    (
        "Survey-only Quiz Answerer",
        {
            "answer": "3DGS represents scenes using anisotropic Gaussians.",
            "used_sections": ["sec_00"],
        },
    ),
    (
        "Quiz Answer Judge",
        {
            "question_id": "",
            "accuracy": 4,
            "completeness": 4,
            "relevance": 2,
            "reason": "Matches reference.",
        },
    ),
    ("Terminology & Rigor Judge", {"severe": 0, "moderate": 0, "minor": 0, "issues": []}),
    ("Readability Judge", {"score": 4, "reason": "Clear and compact."}),
]

SURVEY_MARKDOWN = """# Introduction

3DGS represents scenes using anisotropic Gaussians [1].

## Methods

The tile-based rasterizer improves rendering efficiency [2].

## Conclusion

Gaussian splatting enables real-time rendering applications [1].
"""


def build_dataset(root: Path, *, with_human_survey: bool = True) -> Path:
    """构造迷你数据集（单 topic、两篇 gold paper、2 KIU、2 quiz）。"""
    ds = root / "datasets" / "hysurveybench_test"
    (ds / "topics").mkdir(parents=True)
    (ds / "papers" / "metadata").mkdir(parents=True)
    (ds / "papers" / "fulltext").mkdir(parents=True)
    (ds / "rubrics").mkdir(parents=True)
    (ds / "quizzes").mkdir(parents=True)
    (ds / "human_surveys").mkdir(parents=True)

    (ds / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "HySurveyBench-test",
                "version": "0.1-test",
                "source": "unit-test",
                "num_topics": 1,
                "topics": ["test_topic"],
            }
        ),
        encoding="utf-8",
    )
    (ds / "topics" / "test_topic.json").write_text(
        json.dumps(
            {
                "id": "test_topic",
                "topic": "Test Topic",
                "query": "Write a survey on the test topic.",
                "benchmark_pool": ["2201.00001", "2201.00002", "2201.00003"],
                "human_reference_set": ["2201.00001"],
                "gold_papers": ["2201.00001", "2201.00002"],
                "key_information_units": ["u_def", "u_render"],
                "quiz_file": "../quizzes/test_topic.json",
                "rubric_file": "../rubrics/test_topic.json",
            }
        ),
        encoding="utf-8",
    )
    for paper_id, title in (
        ("2201.00001", "Gaussian Splatting Method"),
        ("2201.00002", "Tile-based Rasterizer"),
    ):
        (ds / "papers" / "metadata" / f"{paper_id}.json").write_text(
            json.dumps(
                {
                    "paper_id": paper_id,
                    "arxiv_id": paper_id,
                    "title": title,
                    "authors": ["Author A"],
                    "abstract": "An abstract about the method.",
                    "year": 2022,
                }
            ),
            encoding="utf-8",
        )
        (ds / "papers" / "fulltext" / f"{paper_id}.json").write_text(
            json.dumps(
                {
                    "paper_id": paper_id,
                    "sections": [
                        {
                            "section_id": "sec_1",
                            "title": "Method",
                            "text": (
                                "3DGS represents scenes using anisotropic Gaussians. "
                                "The tile-based rasterizer improves rendering efficiency. "
                                "Experiments show real-time rendering at high frame rates."
                            ),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
    (ds / "rubrics" / "test_topic.json").write_text(
        json.dumps(
            {
                "topic": "Test Topic",
                "units": [
                    {
                        "id": "u_def",
                        "name": "Definition",
                        "description": "What 3DGS is",
                        "importance": 2,
                        "source_papers": ["2201.00001"],
                    },
                    {
                        "id": "u_render",
                        "name": "Rendering",
                        "description": "Rasterizer efficiency",
                        "importance": 1,
                        "source_papers": ["2201.00002"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (ds / "quizzes" / "test_topic.json").write_text(
        json.dumps(
            {
                "topic": "Test Topic",
                "general": [
                    {
                        "id": "gq1",
                        "type": "concept",
                        "difficulty": "easy",
                        "question": "How does 3DGS represent scenes?",
                        "reference_answer": "Using anisotropic Gaussians.",
                        "source_papers": ["2201.00001"],
                    }
                ],
                "topic_specific": [
                    {
                        "id": "tq1",
                        "type": "method_comparison",
                        "difficulty": "medium",
                        "question": "Why does the rasterizer improve efficiency?",
                        "reference_answer": "Tile-based processing.",
                        "source_papers": ["2201.00002"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    if with_human_survey:
        (ds / "human_surveys" / "test_topic.md").write_text(
            "# Test Topic Survey\n\nReference text.\n", encoding="utf-8"
        )
    return ds


def build_run_dir(root: Path, *, fabricated: bool = False) -> Path:
    """构造六字段运行产物目录。"""
    run_dir = root / "runs" / "task-001"
    run_dir.mkdir(parents=True)
    citations = [
        {
            "citation_id": "1",
            "paper_id": "2201.00001",
            "title": "Gaussian Splatting Method",
            "source": "arXiv",
        },
        {
            "citation_id": "2",
            "paper_id": "2201.00002",
            "title": "Tile-based Rasterizer",
            "source": "arXiv",
        },
    ]
    if fabricated:
        citations.append(
            {"citation_id": "3", "paper_id": "9999.99999", "title": "Ghost Paper", "source": ""}
        )
    payload = {
        "task": {"topic": "Test Topic", "research_questions": []},
        "papers": [
            {
                "paper_id": "2201.00001",
                "title": "Gaussian Splatting Method",
                "year": 2022,
                "source": "arXiv",
            },
            {
                "paper_id": "2201.00002",
                "title": "Tile-based Rasterizer",
                "year": 2022,
                "source": "arXiv",
            },
        ],
        "survey": SURVEY_MARKDOWN,
        "claims": [],
        "citations": citations,
        "evidence_map": [],
    }
    (run_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return run_dir
