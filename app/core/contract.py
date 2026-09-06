"""Evaluation 输出契约（Step 5）。

Application 与 Evaluation 只通过本模块定义的结构交互（换 Evaluator 不改 Agent）：
    1. `build_result_payload` —— 六字段最终输出（task / papers / survey / claims /
       citations / evidence_map），对应 docs 第 30 节与 data-contracts 第 10 节；
    2. `build_eval_payload` —— 与最终输出同源的机器可读合并结果（另附，避免重复维护）；
    3. `validate_result_payload` —— 结构化契约校验，保证输出契约稳定。
字段命名以 ``.codebuddy/skills/hy-surveyagent-app/references/data-contracts.md`` 为准：
Verification 结果中的 `citation`（论文标识）在 evidence_map 中统一命名为 `paper_id`。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.types import SurveyState, TaskInput

#: 六字段最终输出的必需键（data-contracts 第 10 节）
RESULT_KEYS = ("task", "papers", "survey", "claims", "citations", "evidence_map")

SUPPORT_VALUES = (True, False, None)


class ContractError(RuntimeError):
    """最终输出违反 Evaluation 接口契约。"""


def paper_payload(paper: Any) -> dict[str, Any]:
    """论文的对外表示（Evaluation 接口中的 papers 元素）。"""
    return {
        "paper_id": paper.paper_id,
        "title": paper.title,
        "year": paper.year,
        "source": paper.source,
    }


def build_evidence_map(verification: dict[str, Any]) -> list[dict[str, Any]]:
    """把 Verification 结果映射为 evidence_map：`citation` → `paper_id`，仅保留契约字段。"""
    entries: list[dict[str, Any]] = []
    for result in verification.get("results", []):
        if not isinstance(result, dict):
            continue
        entries.append(
            {
                "claim_id": str(result.get("claim_id", "")),
                "paper_id": str(result.get("citation") or result.get("paper_id") or ""),
                "evidence": str(result.get("evidence", "")),
                "support": result.get("support"),
            }
        )
    return entries


def build_result_payload(task: TaskInput, state: SurveyState) -> dict[str, Any]:
    """构造六字段最终输出（Evaluation 接口契约）。"""
    return {
        "task": {
            "topic": task.topic,
            "research_questions": list(task.research_questions),
        },
        "papers": [paper_payload(paper) for paper in state.papers],
        "survey": state.final_survey,
        "claims": [claim.to_dict() for claim in state.claims],
        "citations": [citation.to_dict() for citation in state.citation_map],
        "evidence_map": build_evidence_map(state.verification),
    }


def build_eval_payload(state: SurveyState) -> dict[str, Any]:
    """构造机器可读合并结果（与最终输出同源，供 Evaluation 批量消费）。"""
    return {
        "survey_markdown": state.final_survey,
        "citations": [citation.to_dict() for citation in state.citation_map],
        "source_papers": [paper_payload(paper) for paper in state.papers],
        "outline": state.outline.to_dict(),
        "claims": [claim.to_dict() for claim in state.claims],
        "verification": dict(state.verification),
    }


def validate_result_payload(payload: dict[str, Any]) -> list[str]:
    """校验最终输出契约；返回违规列表，空列表表示合法。

    只做结构不变量校验（键、类型、ID 引用一致性），不评判内容质量：
        - 六字段必需键齐全；
        - papers / claims / citations 的 ID 唯一且非空；
        - claims.citations 与 citations.paper_id 都必须指向 papers 中真实存在的论文；
        - evidence_map 的 claim_id / paper_id 必须可追溯到 claims 与 papers。
    """
    errors: list[str] = []
    missing = [key for key in RESULT_KEYS if key not in payload]
    if missing:
        return [f"缺少必需字段：{missing}"]

    if not isinstance(payload["survey"], str):
        errors.append("survey 必须是字符串")

    paper_ids = _unique_ids(payload["papers"], "paper_id", "papers", errors)
    claim_ids = _unique_ids(payload["claims"], "claim_id", "claims", errors)

    cited_paper_ids: set[str] = set()
    for index, citation in enumerate(payload["citations"]):
        if not isinstance(citation, dict):
            errors.append(f"citations[{index}] 必须是对象")
            continue
        citation_id = str(citation.get("citation_id", ""))
        paper_id = str(citation.get("paper_id", ""))
        if not citation_id:
            errors.append(f"citations[{index}] 缺少 citation_id")
        if not paper_id:
            errors.append(f"citations[{index}] 缺少 paper_id")
        elif paper_ids is not None and paper_id not in paper_ids:
            errors.append(f"citations[{index}] 引用了未知论文：{paper_id}")
        cited_paper_ids.add(paper_id)
    citation_ids = [
        str(item.get("citation_id")) for item in payload["citations"] if isinstance(item, dict)
    ]
    if len(citation_ids) != len(set(citation_ids)):
        errors.append("citations 存在重复的 citation_id")

    for index, claim in enumerate(payload["claims"]):
        if not isinstance(claim, dict):
            errors.append(f"claims[{index}] 必须是对象")
            continue
        claim_id = str(claim.get("claim_id", "") or "")
        for ref in claim.get("citations", []) or []:
            if paper_ids is not None and str(ref) not in paper_ids:
                errors.append(f"claim {claim_id or index} 引用了未知论文：{ref}")

    for index, entry in enumerate(payload["evidence_map"]):
        if not isinstance(entry, dict):
            errors.append(f"evidence_map[{index}] 必须是对象")
            continue
        if entry.get("support") not in SUPPORT_VALUES:
            errors.append(f"evidence_map[{index}] support 必须是 true/false/null")
        claim_id = str(entry.get("claim_id", ""))
        paper_id = str(entry.get("paper_id", ""))
        if claim_ids is not None and claim_id and claim_id not in claim_ids:
            errors.append(f"evidence_map[{index}] 指向未知 Claim：{claim_id}")
        if paper_ids is not None and paper_id and paper_id not in paper_ids:
            errors.append(f"evidence_map[{index}] 指向未知论文：{paper_id}")

    return errors


def _unique_ids(items: Any, key: str, label: str, errors: list[str]) -> set[str] | None:
    """提取非空唯一 ID 集合；发现缺失或重复时记录错误。"""
    if not isinstance(items, list):
        errors.append(f"{label} 必须是数组")
        return None
    ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] 必须是对象")
            continue
        value = str(item.get(key, "") or "")
        if not value:
            errors.append(f"{label}[{index}] 缺少 {key}")
        elif value in ids:
            errors.append(f"{label} 存在重复的 {key}：{value}")
        ids.add(value)
    return ids
