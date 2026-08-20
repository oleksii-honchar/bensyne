"""Configuration management tests."""

import os
from pathlib import Path

import pytest

from src.domain.config_models import AppConfig, InstancePoolConfig, LoggingConfig, ServerConfig
from src.infrastructure.config.manager import ConfigManager


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with default.yaml."""
    default_yaml = tmp_path / "default.yaml"
    default_yaml.write_text(
        """
server:
  name: "bensyne"
  version: "1.0.0"
  transport: "streamable-http"
  host: "0.0.0.0"
  port: 3000

logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  log_file: null

instance_pool:
  max_instances: 50
  eviction_timeout: 300
  data_dir: "/data"
  default_bank: "default"
"""
    )
    return tmp_path


class TestServerConfig:
    def test_server_config_fields(self):
        """ServerConfig has correct typed fields."""
        cfg = ServerConfig(
            name="test",
            version="1.0.0",
            transport="streamable-http",
            host="0.0.0.0",
            port=3000,
        )
        assert cfg.name == "test"
        assert cfg.version == "1.0.0"
        assert cfg.transport == "streamable-http"
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 3000


class TestLoggingConfig:
    def test_logging_config_fields(self):
        """LoggingConfig has correct typed fields."""
        cfg = LoggingConfig(
            level="DEBUG",
            format="%(message)s",
            log_file=None,
        )
        assert cfg.level == "DEBUG"
        assert cfg.format == "%(message)s"
        assert cfg.log_file is None

    def test_logging_config_with_file(self):
        """LoggingConfig supports log_file path."""
        cfg = LoggingConfig(
            level="INFO",
            format="%(message)s",
            log_file="/var/log/app.log",
        )
        assert cfg.log_file == "/var/log/app.log"


class TestInstancePoolConfig:
    def test_instance_pool_config_fields(self):
        """InstancePoolConfig has correct typed fields."""
        cfg = InstancePoolConfig(
            max_instances=50,
            eviction_timeout=300,
            data_dir="/data",
            default_bank="default",
        )
        assert cfg.max_instances == 50
        assert cfg.eviction_timeout == 300
        assert cfg.data_dir == "/data"
        assert cfg.default_bank == "default"

    def test_instance_pool_config_default_data_dir_is_data_root(self):
        """InstancePoolConfig bakes the single fixed container data root /data."""
        cfg = InstancePoolConfig()
        assert cfg.data_dir == "/data"


class TestAppConfig:
    def test_app_config_composition(self):
        """AppConfig composes all sub-configs."""
        server = ServerConfig(name="test", version="1.0.0", transport="streamable-http", host="0.0.0.0", port=3000)
        logging_cfg = LoggingConfig(level="INFO", format="%(message)s", log_file=None)
        pool = InstancePoolConfig(max_instances=50, eviction_timeout=300, data_dir="/data", default_bank="default")

        cfg = AppConfig(server=server, logging=logging_cfg, instance_pool=pool)

        assert cfg.server.name == "test"
        assert cfg.logging.level == "INFO"
        assert cfg.instance_pool.max_instances == 50


class TestConfigManager:
    def test_load_defaults_correctly(self, config_dir: Path):
        """ConfigManager loads all default values from YAML."""
        manager = ConfigManager(config_dir=str(config_dir))
        cfg = manager.load()

        assert isinstance(cfg, AppConfig)
        assert cfg.server.name == "bensyne"
        assert cfg.server.version == "1.0.0"
        assert cfg.server.transport == "streamable-http"
        assert cfg.server.host == "0.0.0.0"
        assert cfg.server.port == 3000

        assert cfg.logging.level == "INFO"
        assert cfg.logging.format == "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        assert cfg.logging.log_file is None

        assert cfg.instance_pool.max_instances == 50
        assert cfg.instance_pool.eviction_timeout == 300
        assert cfg.instance_pool.data_dir == "/data"
        assert cfg.instance_pool.default_bank == "default"

    def test_env_var_overrides_yaml_values(self, config_dir: Path, monkeypatch: pytest.MonkeyPatch):
        """LOG_LEVEL env var overrides logging.level from YAML."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        manager = ConfigManager(config_dir=str(config_dir))
        cfg = manager.load()

        assert cfg.logging.level == "DEBUG"

    def test_load_override_file(self, tmp_path: Path):
        """ConfigManager merges override file on top of defaults."""
        default_yaml = tmp_path / "default.yaml"
        default_yaml.write_text(
            """
server:
  name: "bensyne"
  version: "1.0.0"
  transport: "streamable-http"
  host: "0.0.0.0"
  port: 3000

logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  log_file: null

instance_pool:
  max_instances: 50
  eviction_timeout: 300
  data_dir: "/data"
  default_bank: "default"
"""
        )

        override_yaml = tmp_path / "development.yaml"
        override_yaml.write_text(
            """
instance_pool:
  data_dir: "./data/dev"
"""
        )

        manager = ConfigManager(config_dir=str(tmp_path))
        cfg = manager.load(override_files=["development.yaml"])

        assert cfg.instance_pool.data_dir == "./data/dev"
        assert cfg.instance_pool.max_instances == 50  # unchanged from default

    def test_env_var_and_override_file_combined(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Both env vars and override files are applied; env vars take precedence."""
        monkeypatch.setenv("LOG_LEVEL", "WARNING")

        default_yaml = tmp_path / "default.yaml"
        default_yaml.write_text(
            """
server:
  name: "bensyne"
  version: "1.0.0"
  transport: "streamable-http"
  host: "0.0.0.0"
  port: 3000

logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  log_file: null

instance_pool:
  max_instances: 50
  eviction_timeout: 300
  data_dir: "/data"
  default_bank: "default"
"""
        )

        override_yaml = tmp_path / "development.yaml"
        override_yaml.write_text(
            """
logging:
  level: "DEBUG"

instance_pool:
  data_dir: "./data/dev"
"""
        )

        manager = ConfigManager(config_dir=str(tmp_path))
        cfg = manager.load(override_files=["development.yaml"])

        assert cfg.logging.level == "WARNING"  # env var wins over override file
        assert cfg.instance_pool.data_dir == "./data/dev"  # from override file

    def test_raises_on_missing_default_yaml(self, tmp_path: Path):
        """ConfigManager raises FileNotFoundError when default.yaml is missing."""
        with pytest.raises(FileNotFoundError, match="default.yaml"):
            manager = ConfigManager(config_dir=str(tmp_path))
            manager.load()

    def test_raises_on_invalid_yaml(self, tmp_path: Path):
        """ConfigManager raises ValueError for malformed YAML."""
        default_yaml = tmp_path / "default.yaml"
        default_yaml.write_text("invalid: yaml: content: [")

        with pytest.raises(ValueError, match="YAML"):
            manager = ConfigManager(config_dir=str(tmp_path))
            manager.load()
