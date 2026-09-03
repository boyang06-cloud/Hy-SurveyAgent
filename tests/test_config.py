"""app/config.py 的单元测试：密钥读取、占位值拒绝、环境变量覆盖、配置快照脱敏。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.config import (
    DEFAULT_CONFIG_FILE,
    ENV_API_KEY,
    SECRET_FILE,
    AppConfig,
    ConfigError,
    load_config,
    load_secrets,
)

TEST_KEY = "sk-unit-test-000000000"
TEST_BASE_URL = "https://hy3.unit.test/v1"
CONF_TEMPLATE = "[hy3]\napi_key = {api_key}\nbase_url = {base_url}\n"


def write_conf(root: Path, api_key: str = TEST_KEY, base_url: str = TEST_BASE_URL) -> Path:
    path = root / SECRET_FILE
    path.write_text(CONF_TEMPLATE.format(api_key=api_key, base_url=base_url), encoding="utf-8")
    return path


def test_load_secrets_reads_conf(tmp_path: Path) -> None:
    write_conf(tmp_path)
    secrets = load_secrets(tmp_path)
    assert secrets["api_key"] == TEST_KEY
    assert secrets["base_url"] == TEST_BASE_URL


def test_load_secrets_rejects_placeholder(tmp_path: Path) -> None:
    write_conf(tmp_path, api_key="YOUR_HY3_API_KEY")
    with pytest.raises(ConfigError, match="api_key"):
        load_secrets(tmp_path)


def test_load_secrets_missing_file_points_to_template(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cp "):
        load_secrets(tmp_path)


def test_env_overrides_conf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    write_conf(tmp_path)
    monkeypatch.setenv(ENV_API_KEY, "sk-unit-env-000000000000")
    assert load_secrets(tmp_path)["api_key"] == "sk-unit-env-000000000000"


def test_describe_excludes_secrets() -> None:
    config = AppConfig(secrets={"api_key": TEST_KEY, "base_url": TEST_BASE_URL})
    snapshot = config.describe()
    assert set(snapshot) == {"model", "runtime", "paths", "pipeline", "logging"}
    assert TEST_KEY not in str(snapshot)


def test_load_config_applies_yaml(tmp_path: Path) -> None:
    write_conf(tmp_path)
    config_file = tmp_path / DEFAULT_CONFIG_FILE
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        yaml.safe_dump(
            {
                "model": {"name": "hy3-unit", "temperature": 0.1},
                "runtime": {"max_concurrency": 3},
                "paths": {"runs_dir": "tmp_runs"},
            }
        ),
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.model.name == "hy3-unit"
    assert config.model.temperature == 0.1
    assert config.runtime.max_concurrency == 3
    assert config.runs_dir() == tmp_path / "tmp_runs"
    assert config.api_key() == TEST_KEY


def test_load_config_keeps_defaults_when_file_missing(tmp_path: Path) -> None:
    write_conf(tmp_path)
    with pytest.warns(UserWarning, match="使用默认运行参数"):
        config = load_config(tmp_path)
    assert config.model.temperature == AppConfig().model.temperature


def test_load_config_can_skip_secrets_for_dry_run(tmp_path: Path) -> None:
    config = load_config(tmp_path, require_secrets=False)
    assert config.secrets == {}
    with pytest.raises(ConfigError):
        config.api_key()
