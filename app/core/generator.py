"""统一生成器接口（Step 5，architecture 第 12 节）。

为 Baseline 对比实验与 Evaluation 提供同一输出结构：
    SimplePromptGenerator / SequentialGenerator 后续按需实现；
    当前提供多阶段 Pipeline 实现 `HySurveyAgentGenerator`。
三者输出同一 `SurveyOutput`，交给统一 Evaluator，更换实现无需改动评测侧。
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import AppConfig
from app.core.contract import validate_result_payload
from app.core.pipeline import run_pipeline
from app.core.types import PaperSet, TaskInput
from app.io.exporter import RunWriter
from app.model.provider import LLMProvider


@dataclass
class SurveyOutput:
    """Evaluation 接口的类型化封装：与 result.json 的六字段一一对应。"""

    task: dict[str, Any]
    papers: list[dict[str, Any]]
    survey: str
    claims: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    evidence_map: list[dict[str, Any]]
    task_id: str = ""
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "papers": self.papers,
            "survey": self.survey,
            "claims": self.claims,
            "citations": self.citations,
            "evidence_map": self.evidence_map,
        }


class SurveyGenerator(ABC):
    """统一生成器接口：输入 Topic + Source Papers，输出 SurveyOutput。"""

    @abstractmethod
    def generate(self, topic: str, papers: PaperSet) -> SurveyOutput:
        raise NotImplementedError


class HySurveyAgentGenerator(SurveyGenerator):
    """多阶段 Agent Pipeline 的生成器实现。"""

    def __init__(self, llm: LLMProvider, config: AppConfig, run_id: str | None = None) -> None:
        self.llm = llm
        self.config = config
        self.run_id = run_id

    def generate(self, topic: str, papers: PaperSet) -> SurveyOutput:
        topic = topic.strip()
        if not topic:
            raise ValueError("研究主题为空。")
        if not papers.papers:
            raise ValueError("论文集合为空。")

        task = TaskInput(topic=topic)
        run = RunWriter.create(
            self.config.root, self.config.paths.runs_dir, self.run_id, topic=topic
        )
        payload = asyncio.run(run_pipeline(self.llm, task, papers, run, config=self.config))
        output = SurveyOutput(
            task=payload["task"],
            papers=payload["papers"],
            survey=payload["survey"],
            claims=payload["claims"],
            citations=payload["citations"],
            evidence_map=payload["evidence_map"],
            task_id=run.task_id,
            violations=validate_result_payload(payload),
        )
        return output
