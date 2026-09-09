"""Prompt 加载与渲染。

统一入口，禁止各 Agent 自行 open() 模板文件。
模板顶部用 ``> version: x.y.z`` 记录版本，运行日志会记录版本与内容 hash 用于复现。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
VERSION_PATTERN = re.compile(r"^>\s*version:\s*(\S+)", re.MULTILINE)


class PromptError(RuntimeError):
    """Prompt 缺失、渲染变量不足或模板语法错误。"""


class PromptLoader:
    """加载 app/prompts/*.md 并渲染 ``{{ var }}`` 占位符。"""

    def __init__(self, prompt_dir: Path | str) -> None:
        self.prompt_dir = Path(prompt_dir)
        self._cache: dict[str, str] = {}

    def path(self, name: str) -> Path:
        return self.prompt_dir / f"{name}.md"

    def load(self, name: str) -> str:
        if name not in self._cache:
            path = self.path(name)
            if not path.is_file():
                raise PromptError(f"Prompt 模板不存在：{path}")
            self._cache[name] = path.read_text(encoding="utf-8")
        return self._cache[name]

    def render(self, name: str, **variables: object) -> str:
        template = self.load(name)
        rendered = template
        for key, value in variables.items():
            pattern = re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}")
            rendered = pattern.sub(_replacement(_stringify(value)), rendered)
        remaining = PLACEHOLDER_PATTERN.findall(rendered)
        if remaining:
            raise PromptError(f"Prompt {name} 存在未渲染的占位符：{sorted(set(remaining))}")
        return rendered

    def version(self, name: str) -> str:
        match = VERSION_PATTERN.search(self.load(name))
        return match.group(1) if match else "unknown"

    def digest(self, name: str) -> str:
        return hashlib.sha256(self.load(name).encode("utf-8")).hexdigest()[:12]

    def describe(self, names: list[str]) -> dict[str, dict[str, str]]:
        """返回各 Prompt 的版本与 hash，写入 meta.json 用于结果复现。"""
        return {
            name: {"version": self.version(name), "sha256": self.digest(name)} for name in names
        }


def _replacement(text: str) -> Callable[[re.Match[str]], str]:
    """生成 re.sub 的替换函数，避免替换串中的反斜杠被转义解析。"""

    def _replace(_match: re.Match[str]) -> str:
        return text

    return _replace


def _stringify(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return "\n".join(f"- {item}" for item in value) if value else "（无）"
    if value is None:
        return "（无）"
    return str(value)
