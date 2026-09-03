"""测试夹具：合成论文数据、脚本化 MockProvider、临时 Prompt 目录。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from app.core.types import Paper, PaperSet
from app.model.provider import LLMProvider, LLMResponse

REPO_ROOT = Path(__file__).resolve().parents[1]

SAMPLE_RECORDS: list[dict[str, Any]] = [
    {
        "paper_id": "P001",
        "title": "Vision-Language Models for Driving",
        "authors": ["Author A", "Author B"],
        "year": 2024,
        "source": "ExampleConf 2024",
        "abstract": "Applies a vision-language model to driving scenes and reports results.",
    },
    {
        "paper_id": "P002",
        "title": "Language-Grounded Trajectory Prediction",
        "authors": ["Author C"],
        "year": 2025,
        "source": "ExampleJournal 2025",
        "abstract": "Predicts trajectories from route instructions via a multimodal transformer.",
    },
]


class ScriptedProvider(LLMProvider):
    """按脚本返回响应的 MockProvider，禁止在测试中调用真实 Hy3。"""

    def __init__(self, responses: list[LLMResponse | dict[str, Any] | str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        *,
        top_p: float = 1.0,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
            }
        )
        if not self.responses:
            raise AssertionError("ScriptedProvider 的响应已耗尽。")
        item = self.responses.pop(0)
        if isinstance(item, LLMResponse):
            return item
        text = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
        return LLMResponse(text=text, model=model, token_usage={"prompt": 10, "completion": 20})


@pytest.fixture
def scripted_provider():
    """返回 ScriptedProvider 工厂，避免测试直接依赖模块导入路径。"""

    def _factory(responses: list[LLMResponse | dict[str, Any] | str]) -> ScriptedProvider:
        return ScriptedProvider(responses)

    return _factory


@pytest.fixture
def sample_papers() -> PaperSet:
    return PaperSet(papers=[Paper.from_dict(record) for record in SAMPLE_RECORDS])


@pytest.fixture
def papers_file(tmp_path: Path, sample_papers: PaperSet) -> Path:
    target = tmp_path / "papers.json"
    target.write_text(
        json.dumps([paper.to_dict() for paper in sample_papers.papers], ensure_ascii=False),
        encoding="utf-8",
    )
    return target


@pytest.fixture
def prompt_dir(tmp_path: Path) -> Path:
    """把仓库中的 Prompt 模板复制到临时目录，供 Pipeline 测试使用。"""
    target = tmp_path / "prompts"
    target.mkdir(parents=True, exist_ok=True)
    for source in (REPO_ROOT / "app" / "prompts").glob("*.md"):
        shutil.copy(source, target / source.name)
    return target
