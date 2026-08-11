"""Configuration management."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.domain.config_models import AppConfig, InstancePoolConfig, LoggingConfig, ServerConfig


class ConfigManager:
    """Loads and merges configuration from YAML files with environment variable overrides."""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)

    def load(
        self,
        default_file: str = "default.yaml",
        override_files: Optional[List[str]] = None,
    ) -> AppConfig:
        """Load configuration from YAML files with env var overrides.

        Args:
            default_file: Default configuration file name (loaded first).
            override_files: Additional YAML files to merge on top of defaults.

        Returns:
            AppConfig with merged configuration.

        Raises:
            FileNotFoundError: If default.yaml is missing.
            ValueError: If YAML content is malformed.
        """
        override_files = override_files or []

        # Load default config
        default_path = self.config_dir / default_file
        if not default_path.exists():
            raise FileNotFoundError(f"Default config file not found: {default_path}")

        config_dict = self._load_yaml(default_path)

        # Merge override files
        for override_file in override_files:
            override_path = self.config_dir / override_file
            if override_path.exists():
                override_dict = self._load_yaml(override_path)
                config_dict = self._deep_merge(config_dict, override_dict)

        # Apply environment variable overrides
        config_dict = self._apply_env_overrides(config_dict)

        # Build typed config objects
        return self._build_config(config_dict)

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load and parse a YAML file."""
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ValueError(f"Invalid YAML structure in {path}: expected a mapping at the root")
            return data
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML file {path}: {e}") from e

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge override dict into base dict."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to config dict."""
        # LOG_LEVEL -> logging.level
        log_level = os.getenv("LOG_LEVEL")
        if log_level is not None:
            if "logging" not in config:
                config["logging"] = {}
            config["logging"]["level"] = log_level

        # PORT -> server.port
        port = os.getenv("PORT")
        if port is not None:
            if "server" not in config:
                config["server"] = {}
            try:
                config["server"]["port"] = int(port)
            except ValueError:
                pass  # ignore invalid PORT values

        # DATA_DIR -> instance_pool.data_dir
        data_dir = os.getenv("DATA_DIR")
        if data_dir is not None:
            if "instance_pool" not in config:
                config["instance_pool"] = {}
            config["instance_pool"]["data_dir"] = data_dir

        return config

    def _build_config(self, config_dict: Dict[str, Any]) -> AppConfig:
        """Build typed AppConfig from raw dict."""
        server_dict = config_dict.get("server", {})
        logging_dict = config_dict.get("logging", {})
        pool_dict = config_dict.get("instance_pool", {})

        server = ServerConfig(
            name=str(server_dict.get("name", ServerConfig.name)),
            version=str(server_dict.get("version", ServerConfig.version)),
            transport=str(server_dict.get("transport", ServerConfig.transport)),
            host=str(server_dict.get("host", ServerConfig.host)),
            port=int(server_dict.get("port", ServerConfig.port)),
        )

        log_level = logging_dict.get("level", LoggingConfig.level)
        log_format = logging_dict.get("format", LoggingConfig.format)
        log_file = logging_dict.get("log_file")
        if log_file == "null":
            log_file = None

        logging_cfg = LoggingConfig(
            level=str(log_level),
            format=str(log_format),
            log_file=str(log_file) if log_file else None,
        )

        pool = InstancePoolConfig(
            max_instances=int(pool_dict.get("max_instances", InstancePoolConfig.max_instances)),
            eviction_timeout=int(pool_dict.get("eviction_timeout", InstancePoolConfig.eviction_timeout)),
            data_dir=str(pool_dict.get("data_dir", InstancePoolConfig.data_dir)),
            default_bank=str(pool_dict.get("default_bank", InstancePoolConfig.default_bank)),
        )

        return AppConfig(server=server, logging=logging_cfg, instance_pool=pool)
