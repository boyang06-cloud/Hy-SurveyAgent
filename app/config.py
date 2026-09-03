"""配置加载。

密钥只从项目根目录的 ``API_key.conf``（INI）读取，运行参数从 ``configs/config.yaml`` 读取。
仓库只提交 ``.example`` 模板；``API_key.conf`` 与 ``configs/config.yaml`` 均被 .gitignore 忽略，
任何代码、日志、测试夹具中都不允许出现 Key 字面量。
"""

from __future__ import annotations

import configparser
import os
import warnings
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SECRET_FILE = "API_key.conf"
SECRET_TEMPLATE = "API_key.conf.example"
DEFAULT_CONFIG_FILE = "configs/config.yaml"

ENV_API_KEY = "HY3_API_KEY"
ENV_BASE_URL = "HY3_BASE_URL"

# 模板中的占位值；出现即视为"未配置"，绝不作为真实值使用
PLACEHOLDER_VALUES = ("", "YOUR_HY3_API_KEY", "CHANGEME", "TODO", "NONE", "NULL")
_PLACEHOLDER_SET = {value.upper() for value in PLACEHOLDER_VALUES}


class ConfigError(RuntimeError):
    """配置缺失、格式错误或仍为占位值。"""


def _is_placeholder(value: str | None) -> bool:
    return value is None or value.strip().upper() in _PLACEHOLDER_SET


@dataclass
class ModelConfig:
    """模型调用参数。"""

    name: str = "hy3-default"
    temperature: float = 0.2
    max_tokens: int = 8192
    top_p: float = 1.0


@dataclass
class RuntimeConfig:
    """并发、超时与重试策略。"""

    max_concurrency: int = 8
    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_backoff: float = 2.0  # 首次重试等待秒数，之后指数退避


@dataclass
class PathsConfig:
    """目录配置，相对路径基于项目根目录解析。"""

    runs_dir: str = "runs"
    results_dir: str = "results"
    benchmark_dir: str = "benchmark"
    prompts_dir: str = "app/prompts"


@dataclass
class PipelineConfig:
    """Pipeline 开关。"""

    benchmark_mode: bool = True
    enable_citation_verification: bool = True
    fail_fast: bool = False


@dataclass
class LoggingConfig:
    """日志配置。"""

    level: str = "INFO"
    stage_log: str = "logs/stages.jsonl"


@dataclass
class AppConfig:
    """应用配置。密钥通过 api_key() 访问，不进入 describe() 输出。"""

    model: ModelConfig = field(default_factory=ModelConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    root: Path = PROJECT_ROOT
    secrets: dict[str, str] = field(default_factory=dict)

    def api_key(self) -> str:
        value = self.secrets.get("api_key", "")
        if _is_placeholder(value):
            raise ConfigError(f"{SECRET_FILE} 中的 api_key 仍为占位值，请填入真实 Key。")
        return value

    def base_url(self) -> str:
        value = self.secrets.get("base_url", "")
        if _is_placeholder(value):
            raise ConfigError(f"{SECRET_FILE} 中的 base_url 仍为占位值，请填入 Hy3 服务地址。")
        return value

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else self.root / path

    def prompts_dir(self) -> Path:
        return self.resolve(self.paths.prompts_dir)

    def runs_dir(self) -> Path:
        return self.resolve(self.paths.runs_dir)

    def describe(self) -> dict[str, Any]:
        """可安全落盘的配置快照，不含任何密钥。"""
        snapshot: dict[str, Any] = {}
        for name in ("model", "runtime", "paths", "pipeline", "logging"):
            section = getattr(self, name)
            snapshot[name] = {f.name: getattr(section, f.name) for f in fields(section)}
        return snapshot


def load_secrets(root: Path | None = None) -> dict[str, str]:
    """读取 API_key.conf，并用环境变量覆盖同名项。

    环境变量优先级高于文件，便于 CI 注入；两者都不允许是占位值。
    """
    base = (root or PROJECT_ROOT).resolve()
    path = base / SECRET_FILE
    if not path.is_file():
        raise ConfigError(
            f"未找到密钥文件 {path}。请执行：cp {SECRET_TEMPLATE} {SECRET_FILE}，然后填入真实值。"
        )

    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    secrets: dict[str, str] = {}
    for section in parser.sections():
        for key, value in parser.items(section):
            secrets[key.strip()] = value.strip()

    env_api_key = os.environ.get(ENV_API_KEY)
    if env_api_key and not _is_placeholder(env_api_key):
        secrets["api_key"] = env_api_key.strip()
    env_base_url = os.environ.get(ENV_BASE_URL)
    if env_base_url and not _is_placeholder(env_base_url):
        secrets["base_url"] = env_base_url.strip()

    if _is_placeholder(secrets.get("api_key")):
        raise ConfigError(f"{SECRET_FILE} 中的 api_key 仍为占位值，请填入真实 Key。")
    if _is_placeholder(secrets.get("base_url")):
        raise ConfigError(f"{SECRET_FILE} 中的 base_url 仍为占位值，请填入 Hy3 服务地址。")
    return secrets


def _build_section(cls: type, raw: dict[str, Any], key: str, source: Path | None) -> Any:
    data = raw.get(key) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"配置项 {key} 应为映射，实际为 {type(data).__name__}。")
    allowed = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        warnings.warn(f"忽略未知配置项：{key}.{', '.join(unknown)}（来源：{source}）", stacklevel=2)
    return cls(**{k: v for k, v in data.items() if k in allowed})


def load_config(
    root: Path | None = None,
    config_path: str | Path | None = None,
    *,
    require_secrets: bool = True,
) -> AppConfig:
    """加载运行配置与密钥。

    config 文件缺失时回退到 dataclass 默认值（仅对默认路径告警），
    以便 --dry-run 等离线场景无需任何本地配置即可运行。
    """
    base = (root or PROJECT_ROOT).resolve()
    path = Path(config_path) if config_path else base / DEFAULT_CONFIG_FILE
    if not path.is_absolute():
        path = base / path

    raw: dict[str, Any] = {}
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if loaded is not None and not isinstance(loaded, dict):
            raise ConfigError(f"配置文件内容应为映射：{path}")
        raw = loaded or {}
    elif config_path is None:
        warnings.warn(
            f"未找到 {path}，使用默认运行参数。"
            f"可执行 cp configs/config.example.yaml {DEFAULT_CONFIG_FILE}。",
            stacklevel=2,
        )
    else:
        raise ConfigError(f"配置文件不存在：{path}")

    config = AppConfig(
        model=_build_section(ModelConfig, raw, "model", path),
        runtime=_build_section(RuntimeConfig, raw, "runtime", path),
        paths=_build_section(PathsConfig, raw, "paths", path),
        pipeline=_build_section(PipelineConfig, raw, "pipeline", path),
        logging=_build_section(LoggingConfig, raw, "logging", path),
        root=base,
    )
    if require_secrets:
        config.secrets = load_secrets(base)
    return config
