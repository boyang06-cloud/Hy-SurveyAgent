"""文本切分与统计工具（纯函数，无 LLM 依赖）。

供 chapter-level 评测（D1 / D3 / D7）、Outline 解析（D5）与
Quiz Section Retrieval（D6）共用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class Chapter:
    """Survey 的一个章节（按 Markdown heading 切分）。"""

    title: str
    text: str

    @property
    def words(self) -> int:
        return count_words(self.text)

    def paragraphs(self) -> list[str]:
        return split_paragraphs(self.text)


def count_words(text: str) -> int:
    """词数统计：以空白切分（中文场景退化为字符数级近似，保持确定性）。"""
    return len(text.split())


def split_chapters(markdown: str) -> list[Chapter]:
    """按 Markdown heading 切分章节；首个 heading 之前的非空文本记为 preamble。"""
    matches = list(_HEADING_RE.finditer(markdown))
    if not matches:
        text = markdown.strip()
        return [Chapter("Document", text)] if text else []

    chapters: list[Chapter] = []
    preamble = markdown[: matches[0].start()].strip()
    if preamble:
        chapters.append(Chapter("(preamble)", preamble))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[match.end() : end].strip()
        if body:
            chapters.append(Chapter(match.group(2).strip(), body))
    return chapters


def headings(markdown: str) -> list[tuple[int, str]]:
    """提取 (level, title) 标题列表，保持文档顺序。"""
    return [
        (len(match.group(1)), match.group(2).strip()) for match in _HEADING_RE.finditer(markdown)
    ]


def split_paragraphs(text: str) -> list[str]:
    """按空行切分段落，丢弃空白段落。"""
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def split_passages(text: str, max_chars: int) -> list[str]:
    """把长文本切成不超过 ``max_chars`` 的检索段落。

    先按段落合并；超长单段再硬切。保证段落的顺序与确定性。
    """
    if max_chars <= 0:
        return [text] if text.strip() else []
    passages: list[str] = []
    buffer = ""
    for paragraph in split_paragraphs(text):
        if len(paragraph) > max_chars:
            if buffer:
                passages.append(buffer)
                buffer = ""
            for start in range(0, len(paragraph), max_chars):
                passages.append(paragraph[start : start + max_chars])
            continue
        candidate = f"{buffer}\n{paragraph}" if buffer else paragraph
        if len(candidate) > max_chars:
            passages.append(buffer)
            buffer = paragraph
        else:
            buffer = candidate
    if buffer:
        passages.append(buffer)
    return passages


def truncate(text: str, limit: int) -> str:
    """确定性截断，超限追加省略标记。"""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ...[truncated]"
