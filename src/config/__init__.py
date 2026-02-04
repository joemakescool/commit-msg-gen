"""Configuration Management Package"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """User configuration with sensible defaults."""
    provider: str = "auto"
    model: Optional[str] = None
    style: str = "conventional"
    include_body: bool = True
    max_subject_length: int = 72
    ticket_prefix: str = "Refs"

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ConfigManager:
    """Manages loading and saving configuration."""

    CONFIG_FILENAME = ".cmrc"

    def __init__(self):
        self._config: Optional[Config] = None
        self._config_path: Optional[Path] = None

    def load(self) -> Config:
        if self._config is not None:
            return self._config

        local_path = Path.cwd() / self.CONFIG_FILENAME
        if local_path.exists():
            self._config = self._load_from_file(local_path)
            self._config_path = local_path
            return self._config

        home_path = Path.home() / self.CONFIG_FILENAME
        if home_path.exists():
            self._config = self._load_from_file(home_path)
            self._config_path = home_path
            return self._config

        self._config = Config()
        return self._config

    def _load_from_file(self, path: Path) -> Config:
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return Config.from_dict(data)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load {path}: {e}")
            return Config()

    def save(self, config: Config, global_config: bool = True) -> Path:
        path = Path.home() / self.CONFIG_FILENAME if global_config else Path.cwd() / self.CONFIG_FILENAME
        with open(path, 'w') as f:
            json.dump(config.to_dict(), f, indent=2)
        return path

    def get_config_path(self) -> Optional[Path]:
        return self._config_path


_manager = ConfigManager()


def load_config() -> Config:
    return _manager.load()


def save_config(config: Config, global_config: bool = True) -> Path:
    return _manager.save(config, global_config)


def get_config_path() -> Optional[Path]:
    return _manager.get_config_path()


__all__ = ["Config", "ConfigManager", "load_config", "save_config", "get_config_path"]
