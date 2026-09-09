#!/usr/bin/env python3
"""生成 scripts/build_eval_dataset/ 骨架：build.py + 各 step 占位 + config + utils。

用法：
    python init_builder.py [--root <repo-root>] [--force]

约定：
    - 已存在的文件默认跳过，`--force` 时覆盖；
    - 只创建文件，不下载数据、不调用 LLM；
    - Step 1/2/9 依赖 skill 的 scripts/ 中的确定性实现，可通过 `--link-helpers` 复制进 utils/。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PREFIX = "scripts/build_eval_dataset"

FILES: dict[str, str] = {
    f"{PREFIX}/__init__.py": "",
    f"{PREFIX}/build.py": '''"""HySurveyBench 构造入口。

用法：
    python build.py ingest | normalize | metadata | select-papers |
                    fetch-fulltext | build-rubrics | build-quizzes | validate | all
"""

from __future__ import annotations

import argparse

STEPS = (
    "ingest",
    "normalize",
    "metadata",
    "select-papers",
    "fetch-fulltext",
    "build-rubrics",
    "build-quizzes",
    "validate",
    "all",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构造 HySurveyBench 评测数据集。")
    parser.add_argument("step", choices=STEPS, help="要执行的阶段")
    parser.add_argument("--config", default="build_config.yaml", help="构造配置")
    parser.add_argument("--topic", default="", help="只处理指定 topic")
    parser.add_argument("--force", action="store_true", help="忽略已有中间产物，强制重跑")
    args = parser.parse_args(argv)

    # TODO: 加载 config，按 step 分发；每个 step 先检查中间产物，存在且有效则跳过（resume）
    print(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    f"{PREFIX}/config.py": '''"""构造配置：路径、阈值、模型、规模控制（不含密钥）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BuildConfig:
    """数据集构造配置。"""

    surveybench_dir: str = "data/SurveyBench"        # 原始 SurveyBench 仓库
    build_dir: str = "build"                          # 中间产物根目录
    cache_dir: str = "cache/paper_metadata"           # metadata 抓取缓存
    output_dir: str = "datasets/hysurveybench_v0.1"   # 产出目录（版本化）

    # 规模控制
    gold_papers_per_topic: int = 50
    gold_papers_min: int = 30
    gold_papers_max: int = 80
    kiu_per_topic: int = 15
    quizzes_per_topic: int = 20

    # 难度分布建议（easy / medium / hard）
    difficulty_ratio: tuple[float, float, float] = (0.25, 0.50, 0.25)

    # LLM 步骤（仅四处允许使用 LLM）
    llm_model: str = ""
    llm_temperature: float = 0.0
    prompt_versions: dict[str, str] = field(
        default_factory=lambda: {
            "relevance": "relevance-v1",
            "rubric": "rubric-v1",
            "quiz": "quiz-v1",
            "quiz_validate": "quiz-validate-v1",
        }
    )

    # 网络抓取
    metadata_sources: tuple[str, ...] = ("arxiv", "semantic_scholar")
    concurrency: int = 4
    timeout_seconds: int = 30
    max_retries: int = 3

    # 默认忽略 generated_surveys_ref（不作为 Gold Data）
    use_generated_refs: bool = False
''',
    f"{PREFIX}/ingest_surveybench.py": '''"""Step 1：读取 topics.txt / ref_bench / human_written_ref。

确定性步骤：**禁止调用 LLM**。
必须容忍缺失与 0 字节文件（如 RAG 的 human reference）。
"""

from __future__ import annotations

import json
from pathlib import Path

from config import BuildConfig


def ingest(cfg: BuildConfig) -> dict[str, dict[str, dict]]:
    """返回 {"<topic>": {"benchmark_refs": {...}, "human_refs": {...}}}。"""
    root = Path(cfg.surveybench_dir)
    topics = [
        line.strip()
        for line in (root / "topics.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result: dict[str, dict[str, dict]] = {}
    for topic in topics:
        result[topic] = {
            "benchmark_refs": _read_ref_file(root / "ref_bench" / f"{topic}_bench.json"),
            "human_refs": _read_human_ref(root, topic),
        }
    return result


def _read_ref_file(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_human_ref(root: Path, topic: str) -> dict:
    """人工综述引用文件名与 topic 不完全一致，需容错匹配；0 字节返回空。"""
    directory = root / "human_written_ref"
    if not directory.is_dir():
        return {}
    target = directory / f"A Survey on {topic}.json"
    if not target.is_file():
        candidates = sorted(directory.glob(f"*{topic}*.json"))
        target = candidates[0] if candidates else target
    return _read_ref_file(target)
''',
    f"{PREFIX}/normalize_refs.py": '''"""Step 2：arXiv ID 规范化 + 去重 + 异常检测。

优先复用 skill 的确定性实现：
    from utils.normalize_arxiv_ids import normalize_arxiv_id, normalize_topics
"""

from __future__ import annotations

import json
from pathlib import Path

from config import BuildConfig


def normalize(cfg: BuildConfig) -> None:
    """读取 01_ingested/topics.json，写出 02_normalized/topics.json 与报告。"""
    sys_path = Path(__file__).resolve().parent / "utils"
    raise SystemExit(
        f"TODO: 引入 {sys_path}/normalize_arxiv_ids.py 后调用 normalize_topics()；"
        f"配置={cfg.build_dir}"
    )
''',
    f"{PREFIX}/fetch_metadata.py": '''"""Step 3：补全 metadata + abstract（arXiv / Semantic Scholar），必须缓存。"""

from __future__ import annotations

import json
from pathlib import Path

from config import BuildConfig


def fetch_metadata(cfg: BuildConfig) -> None:
    """缓存到 cfg.cache_dir/{arxiv_id}.json；失败写入 report，不阻塞。"""
    raise SystemExit(f"TODO: 实现抓取与缓存；cache={cfg.cache_dir}")
''',
    f"{PREFIX}/select_gold_papers.py": '''"""Step 4：Gold Paper 筛选（LLM 允许点 1/4）。

四级判定：CORE(3) / RELEVANT(2) / BACKGROUND(1) / IRRELEVANT(0)
gold_papers = CORE + selected RELEVANT；BACKGROUND 保留但不计入 Coverage 分母。
规模控制在 cfg.gold_papers_min ~ cfg.gold_papers_max。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RelevanceLabel:
    paper_id: str
    relevance: str          # CORE / RELEVANT / BACKGROUND / IRRELEVANT
    relevance_score: int    # 3 / 2 / 1 / 0
    human_reference: bool
    reason: str
    cluster: str = ""       # 聚类标签，用于按簇采样


def select_gold_papers(labels: list[RelevanceLabel], cfg) -> list[str]:
    """先按 cluster 分桶，再每桶取代表论文，最后裁剪到目标规模。"""
    raise SystemExit("TODO: 实现按簇采样与规模裁剪")
''',
    f"{PREFIX}/fetch_papers.py": '''"""Step 5：仅 Gold Papers 取全文并切 section（两阶段方案的第二阶段）。

禁止第一天就下载全部候选池 PDF（6000+ → 约 500）。
"""

from __future__ import annotations


def fetch_fulltext(paper_ids: list[str], cfg) -> None:
    """输出 papers/fulltext/{paper_id}.json = {paper_id, sections:[{section_id,title,text}]}。

    全文获取失败时降级为 abstract-only，并在 report 标注，禁止静默丢弃。
    """
    raise SystemExit("TODO: 实现全文抓取与 section 切分")
''',
    f"{PREFIX}/build_rubrics.py": '''"""Step 6：KIU 生成 + 去重 + importance（LLM 允许点 2/4）。

每条 KIU 必须含 description / importance / source_papers，且至少一个 source_paper。
禁止输出 "Discuss important research." 这类空泛条目。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeyInformationUnit:
    id: str
    name: str
    description: str
    importance: int = 1
    source_papers: list[str] = field(default_factory=list)
    generated_by: dict[str, str] = field(default_factory=dict)  # provenance


def build_rubrics(topic: str, gold_paper_ids: list[str], cfg) -> list[KeyInformationUnit]:
    raise SystemExit("TODO: 实现候选生成 → 语义去重 → importance → evidence grounding")
''',
    f"{PREFIX}/build_quizzes.py": '''"""Step 7：General + Topic-specific Quiz（LLM 允许点 3/4）。

General Quiz 可模板化；Topic Quiz 必须 evidence-grounded：
    Gold Papers → 选证据段落 → 生成问题 → 生成参考答案
禁止凭参数知识凭空出题。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QuizQuestion:
    id: str
    type: str
    difficulty: str             # easy / medium / hard
    question: str
    reference_answer: str
    source_papers: list[str] = field(default_factory=list)
    evidence: list[dict[str, str]] = field(default_factory=list)
    generated_by: dict[str, str] = field(default_factory=dict)  # provenance


def build_quizzes(topic: str, gold_paper_ids: list[str], cfg) -> list[QuizQuestion]:
    raise SystemExit("TODO: 实现证据驱动出题与参考答案生成")
''',
    f"{PREFIX}/validate_quizzes.py": '''"""Step 8：Quiz 三层验证（LLM 允许点 4/4）。

1. Answerability：只给 question + gold evidence，Judge 能否稳定回答；
2. Evidence Requirement：靠常识即可回答的最多归为 Easy/General；
3. Ambiguity：两个 Judge 独立回答，明显分歧 → reject / 人工复核。
"""

from __future__ import annotations


def validate_quizzes(questions: list, cfg) -> tuple[list, list[dict]]:
    """返回 (通过的题目, reject 记录)。"""
    raise SystemExit("TODO: 实现三层验证与 reject 原因统计")
''',
    f"{PREFIX}/validate_dataset.py": '''"""Step 9：数据集结构校验（确定性，禁止 LLM）。

复用 skill 的确定性实现：
    python .codebuddy/skills/hy-surveyagent-eval-dataset/scripts/validate_dataset.py \\
        --dataset datasets/hysurveybench_v1.0 --json-out build/09_final/validation.json
"""

from __future__ import annotations


def validate(cfg) -> int:
    """返回退出码：0 通过，1 存在 ERROR。"""
    raise SystemExit("TODO: 调用 scripts/validate_dataset.py 并汇总到 build/09_final/")
''',
    f"{PREFIX}/utils/__init__.py": "",
    f"{PREFIX}/utils/paths.py": '''"""中间产物路径约定（支持 resume：存在且有效则跳过）。"""

from __future__ import annotations

from pathlib import Path

STAGES = (
    "01_ingested",
    "02_normalized",
    "03_metadata",
    "04_classified",
    "05_gold",
    "06_papers",
    "07_rubrics",
    "08_quizzes",
    "09_final",
)


def stage_dir(build_dir: str | Path, stage: str) -> Path:
    """返回并创建某个阶段的目录。"""
    path = Path(build_dir) / stage
    path.mkdir(parents=True, exist_ok=True)
    return path
''',
}


def write(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return f"skip  {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"write {path}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成评测数据集构造脚本骨架。")
    parser.add_argument("--root", default=".", help="仓库根目录")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    parser.add_argument(
        "--link-helpers",
        action="store_true",
        help="把 skill 的确定性脚本复制到 utils/（normalize_arxiv_ids.py / validate_dataset.py）",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    for rel, content in FILES.items():
        print(write(root / rel, content, args.force))

    config_src = SKILL_DIR / "assets" / "templates" / "build_config.example.yaml"
    if config_src.is_file():
        print(write(root / PREFIX / "build_config.example.yaml", config_src.read_text(encoding="utf-8"), args.force))

    if args.link_helpers:
        for name in ("normalize_arxiv_ids.py", "validate_dataset.py"):
            source = SKILL_DIR / "scripts" / name
            if source.is_file():
                print(write(root / PREFIX / "utils" / name, source.read_text(encoding="utf-8"), True))

    print("\n下一步：按 references/build-steps.md 的顺序逐个填充 step 实现。")
    print("提示：`cp API_key.conf.example API_key.conf` 并填 Key，仅 LLM step 需要。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
