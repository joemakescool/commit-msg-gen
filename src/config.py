"""
Config Module

Handles user configuration for commit-msg-gen.
Looks for config in multiple places (in order):

1. .cmrc in current directory (project-specific)
2. .cmrc in home directory (global default)
3. Built-in defaults

Config format (JSON):
{
    "provider": "ollama",
    "model": "llama3.2:3b",
    "style": "conventional"
}
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """
    User configuration with sensible defaults.
    """
    # LLM settings (actively used)
    provider: str = "auto"  # "auto", "ollama", "claude"
    model: Optional[str] = None  # Model name override

    # TODO: These fields are defined for future use but not yet implemented
    # Uncomment and implement as needed:
    # style: str = "conventional"  # conventional, simple, detailed
    # include_body: bool = True
    # max_subject_length: int = 50
    # auto_commit: bool = False
    # show_diff_stats: bool = True
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        """Create Config from dictionary, ignoring unknown keys."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ConfigManager:
    """
    Manages loading and saving configuration.
    
    Lookup order:
    1. .cmrc in current directory
    2. .cmrc in home directory
    3. Defaults
    """
    
    CONFIG_FILENAME = ".cmrc"
    
    def __init__(self):
        self._config: Optional[Config] = None
        self._config_path: Optional[Path] = None
    
    def load(self) -> Config:
        """
        Load configuration from file or return defaults.
        
        Caches the result for subsequent calls.
        """
        if self._config is not None:
            return self._config
        
        # Try local config first
        local_path = Path.cwd() / self.CONFIG_FILENAME
        if local_path.exists():
            self._config = self._load_from_file(local_path)
            self._config_path = local_path
            return self._config
        
        # Try home directory
        home_path = Path.home() / self.CONFIG_FILENAME
        if home_path.exists():
            self._config = self._load_from_file(home_path)
            self._config_path = home_path
            return self._config
        
        # Use defaults
        self._config = Config()
        return self._config
    
    def _load_from_file(self, path: Path) -> Config:
        """Load config from a JSON file."""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return Config.from_dict(data)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load {path}: {e}")
            return Config()
    
    def save(self, config: Config, global_config: bool = True) -> Path:
        """
        Save configuration to file.
        
        Args:
            config: Configuration to save
            global_config: If True, save to home directory; else current directory
            
        Returns:
            Path where config was saved
        """
        if global_config:
            path = Path.home() / self.CONFIG_FILENAME
        else:
            path = Path.cwd() / self.CONFIG_FILENAME
        
        with open(path, 'w') as f:
            json.dump(config.to_dict(), f, indent=2)
        
        return path
    
    def get_config_path(self) -> Optional[Path]:
        """Return the path of the loaded config file, if any."""
        return self._config_path
    
    def create_default_config(self, provider: str = "ollama", model: str = None) -> Path:
        """
        Create a default config file in home directory.
        
        Convenience method for first-time setup.
        """
        config = Config(provider=provider, model=model)
        return self.save(config, global_config=True)


# Singleton instance for easy access
_manager = ConfigManager()


def load_config() -> Config:
    """Load configuration (convenience function)."""
    return _manager.load()


def save_config(config: Config, global_config: bool = True) -> Path:
    """Save configuration (convenience function)."""
    return _manager.save(config, global_config)


def get_config_path() -> Optional[Path]:
    """Get the path of loaded config (convenience function)."""
    return _manager.get_config_path()


# CLI test
if __name__ == "__main__":
    print("Config Module Test")
    print("=" * 40)
    
    # Load config
    config = load_config()
    path = get_config_path()
    
    print(f"Config loaded from: {path or 'defaults'}")
    print(f"\nCurrent settings:")
    for key, value in config.to_dict().items():
        print(f"  {key}: {value}")
    
    # Show where config files would be
    print(f"\nConfig file locations:")
    print(f"  Local:  {Path.cwd() / '.cmrc'}")
    print(f"  Global: {Path.home() / '.cmrc'}")
