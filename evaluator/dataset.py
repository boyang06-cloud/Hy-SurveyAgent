"""冻结数据集的只读加载器。

数据格式遵循 ``eval_dataset/eval_data_construct.md`` 第 45 节的目录约定：
manifest.json / topics/ / papers/metadata/ / papers/fulltext/ /
rubrics/ / quizzes/ / human_surveys/。

评测阶段对数据集目录只做读操作（禁止写打开）；
新增或修订数据必须走 eval-dataset skill 产出新版本目录。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evaluator.textutil import split_passages


class DatasetError(RuntimeError):
    """数据集结构不合法或缺失必需文件。"""


@dataclass
class PaperMetadata:
    paper_id: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    arxiv_id: str = ""


@dataclass
class PaperSection:
    section_id: str
    title: str = ""
    text: str = ""


@dataclass
class PaperFulltext:
    paper_id: str
    sections: list[PaperSection] = field(default_factory=list)

    def passages(self, max_chars: int) -> list[tuple[str, str, str]]:
        """返回 (section_id, section_title, passage) 列表。"""
        result: list[tuple[str, str, str]] = []
        for section in self.sections:
            for passage in split_passages(section.text, max_chars):
                result.append((section.section_id, section.title, passage))
        return result


@dataclass
class RubricUnit:
    id: str
    name: str = ""
    description: str = ""
    importance: int = 1
    source_papers: list[str] = field(default_factory=list)


@dataclass
class QuizQuestion:
    id: str
    question: str
    reference_answer: str = ""
    category: str = "topic_specific"  # general | topic_specific
    difficulty: str = "medium"
    qtype: str = ""
    source_papers: list[str] = field(default_factory=list)


@dataclass
class TopicCase:
    """单个 benchmark topic 的完整冻结数据。"""

    id: str
    topic: str = ""
    query: str = ""
    benchmark_pool: list[str] = field(default_factory=list)
    human_reference_set: list[str] = field(default_factory=list)
    gold_papers: list[str] = field(default_factory=list)
    units: list[RubricUnit] = field(default_factory=list)
    quizzes: list[QuizQuestion] = field(default_factory=list)
    human_survey_available: bool = False


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise DatasetError(f"数据集缺少文件：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"数据集文件不是合法 JSON：{path}（{exc}）") from exc


class Dataset:
    """只读数据集句柄；topic / paper 文件按需懒加载并缓存。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        manifest = _read_json(root / "manifest.json")
        if not isinstance(manifest, dict):
            raise DatasetError("manifest.json 必须是 JSON 对象。")
        self.manifest: dict[str, Any] = manifest
        self.name = str(manifest.get("dataset_name") or root.name)
        self.version = str(manifest.get("version") or "unknown")
        topic_ids = manifest.get("topics") or []
        if not isinstance(topic_ids, list) or not topic_ids:
            raise DatasetError("manifest.json 缺少非空 topics 列表。")
        self.topic_ids: list[str] = [str(item) for item in topic_ids]
        self._topics: dict[str, TopicCase] = {}
        self._metadata: dict[str, PaperMetadata | None] = {}
        self._fulltext: dict[str, PaperFulltext | None] = {}
        self._paper_universe: set[str] | None = None

    # --- topic ----------------------------------------------------------- #

    def topic(self, topic_id: str) -> TopicCase:
        if topic_id not in self._topics:
            self._topics[topic_id] = self._load_topic(topic_id)
        return self._topics[topic_id]

    def _load_topic(self, topic_id: str) -> TopicCase:
        raw = _read_json(self.root / "topics" / f"{topic_id}.json")
        if not isinstance(raw, dict):
            raise DatasetError(f"topic 文件必须是 JSON 对象：{topic_id}")
        case = TopicCase(
            id=topic_id,
            topic=str(raw.get("topic") or ""),
            query=str(raw.get("query") or ""),
            benchmark_pool=[str(v) for v in raw.get("benchmark_pool") or []],
            human_reference_set=[str(v) for v in raw.get("human_reference_set") or []],
            gold_papers=[str(v) for v in raw.get("gold_papers") or []],
            human_survey_available=(self.root / "human_surveys" / f"{topic_id}.md").is_file(),
        )
        case.units = self._load_units(topic_id, raw)
        case.quizzes = self._load_quizzes(topic_id, raw)
        return case

    def _load_units(self, topic_id: str, topic_raw: dict[str, Any]) -> list[RubricUnit]:
        raw_units: Any = topic_raw.get("key_information_units")
        unit_ids: list[str] | None = None
        if (
            isinstance(raw_units, list)
            and raw_units
            and all(isinstance(item, str) for item in raw_units)
        ):
            # eval_data_construct.md 第 11 节：topic 的 key_information_units 是 unit id 列表
            unit_ids = [str(item) for item in raw_units]
            raw_units = None
        if raw_units is None:
            rubric_file = topic_raw.get("rubric_file") or f"../rubrics/{topic_id}.json"
            rubric_path = (self.root / "topics" / rubric_file).resolve()
            if not rubric_path.is_file():
                return []
            rubric = _read_json(rubric_path)
            raw_units = rubric.get("units") if isinstance(rubric, dict) else None
        if not isinstance(raw_units, list):
            return []
        units: list[RubricUnit] = []
        for item in raw_units:
            if not isinstance(item, dict):
                continue
            unit_id = str(item.get("id") or "")
            if not unit_id:
                continue
            if unit_ids is not None and unit_id not in unit_ids:
                continue
            units.append(
                RubricUnit(
                    id=unit_id,
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    importance=int(item.get("importance") or 1),
                    source_papers=[str(v) for v in item.get("source_papers") or []],
                )
            )
        if unit_ids is not None:
            order = {unit_id: index for index, unit_id in enumerate(unit_ids)}
            units.sort(key=lambda unit: order.get(unit.id, len(order)))
        return units

    def _load_quizzes(self, topic_id: str, topic_raw: dict[str, Any]) -> list[QuizQuestion]:
        quiz_file = topic_raw.get("quiz_file") or f"../quizzes/{topic_id}.json"
        quiz_path = (self.root / "topics" / quiz_file).resolve()
        if not quiz_path.is_file():
            return []
        quiz = _read_json(quiz_path)
        if not isinstance(quiz, dict):
            return []
        entries: list[tuple[str, dict[str, Any]]] = []
        for category in ("general", "topic_specific"):
            items = quiz.get(category)
            if isinstance(items, list):
                entries.extend((category, item) for item in items if isinstance(item, dict))
        if not entries and isinstance(quiz.get("questions"), list):
            entries.extend(
                (str(item.get("category") or "topic_specific"), item)
                for item in quiz["questions"]
                if isinstance(item, dict)
            )
        questions: list[QuizQuestion] = []
        for category, item in entries:
            question_id = str(item.get("id") or "")
            text = str(item.get("question") or "")
            if not question_id or not text:
                continue
            questions.append(
                QuizQuestion(
                    id=question_id,
                    question=text,
                    reference_answer=str(item.get("reference_answer") or ""),
                    category=category,
                    difficulty=str(item.get("difficulty") or "medium"),
                    qtype=str(item.get("type") or ""),
                    source_papers=[str(v) for v in item.get("source_papers") or []],
                )
            )
        return questions

    # --- papers ---------------------------------------------------------- #

    def metadata(self, paper_id: str) -> PaperMetadata | None:
        if paper_id not in self._metadata:
            path = self.root / "papers" / "metadata" / f"{paper_id}.json"
            if not path.is_file():
                self._metadata[paper_id] = None
            else:
                raw = _read_json(path)
                self._metadata[paper_id] = (
                    PaperMetadata(
                        paper_id=str(raw.get("paper_id") or paper_id),
                        title=str(raw.get("title") or ""),
                        authors=[str(v) for v in raw.get("authors") or []],
                        year=int(raw["year"]) if raw.get("year") else None,
                        abstract=str(raw.get("abstract") or ""),
                        arxiv_id=str(raw.get("arxiv_id") or paper_id),
                    )
                    if isinstance(raw, dict)
                    else None
                )
        return self._metadata[paper_id]

    def fulltext(self, paper_id: str) -> PaperFulltext | None:
        if paper_id not in self._fulltext:
            path = self.root / "papers" / "fulltext" / f"{paper_id}.json"
            if not path.is_file():
                self._fulltext[paper_id] = None
            else:
                raw = _read_json(path)
                sections = (
                    [
                        PaperSection(
                            section_id=str(section.get("section_id") or f"sec_{index}"),
                            title=str(section.get("title") or ""),
                            text=str(section.get("text") or ""),
                        )
                        for index, section in enumerate(raw.get("sections") or [])
                        if isinstance(section, dict)
                    ]
                    if isinstance(raw, dict)
                    else []
                )
                self._fulltext[paper_id] = PaperFulltext(paper_id=paper_id, sections=sections)
        return self._fulltext[paper_id]

    def known_paper_ids(self) -> set[str]:
        """数据集中已知的全部论文 ID（gold / pool / human reference / metadata 文件）。"""
        if self._paper_universe is None:
            universe: set[str] = set()
            for topic_id in self.topic_ids:
                case = self.topic(topic_id)
                universe.update(case.gold_papers, case.benchmark_pool, case.human_reference_set)
            for path in (self.root / "papers" / "metadata").glob("*.json"):
                universe.add(path.stem)
            self._paper_universe = universe
        return self._paper_universe

    def match_topic(self, topic_text: str) -> TopicCase | None:
        """按主题文本（忽略大小写与首尾空白）匹配 topic。"""
        wanted = topic_text.strip().lower()
        if not wanted:
            return None
        for topic_id in self.topic_ids:
            case = self.topic(topic_id)
            if case.topic.strip().lower() == wanted:
                return case
        return None


def load_dataset(path: str | Path) -> Dataset:
    """加载冻结数据集目录（只读）。"""
    root = Path(path)
    if not root.is_dir():
        raise DatasetError(f"数据集目录不存在：{root}")
    return Dataset(root)
