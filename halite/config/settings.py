"""
AppConfig load/save via TOML (§7.1, §5).
Config lives at ~/.halite/config.toml.  First run creates it with defaults.
"""
from __future__ import annotations

import tomli_w
from pathlib import Path

from halite.models.schemas import AppConfig

CONFIG_DIR = Path.home() / ".halite"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def _ensure_config_dir() -> None:
    """Create ~/.halite/ if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    """
    Load config from ~/.halite/config.toml.
    If the file doesn't exist, create it with defaults and return those.
    """
    _ensure_config_dir()

    if not CONFIG_FILE.exists():
        cfg = AppConfig()
        save_config(cfg)
        return cfg

    try:
        import tomllib  # Python 3.11+
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
        return AppConfig(**data)
    except Exception as exc:
        # Corrupt config — back up and reset (§6.3 pattern for DB, applied here too)
        backup = CONFIG_DIR / f"config.toml.corrupt-{Path(CONFIG_FILE).stat().st_mtime_ns}"
        CONFIG_FILE.rename(backup)
        cfg = AppConfig()
        save_config(cfg)
        from halite.utils.logging_config import logger
        logger.warning(
            "Config file was corrupt; backed up to {} and created fresh default. Error: {}",
            backup, exc,
        )
        return cfg


def save_config(cfg: AppConfig) -> None:
    """Persist AppConfig to TOML."""
    _ensure_config_dir()
    data = cfg.model_dump(mode="json")
    # tomli_w cannot serialize None — drop None values (they're optional fields)
    cleaned = {k: v for k, v in data.items() if v is not None}
    with open(CONFIG_FILE, "w") as f:
        f.write(tomli_w.dumps(cleaned))
