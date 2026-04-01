"""Game configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_CONFIG_DIR = Path(__file__).parent
_config_cache: dict[str, Any] | None = None


def load_config() -> dict[str, Any]:
    """Load and cache game configuration from YAML files."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    defaults_path = _CONFIG_DIR / "defaults.yaml"
    with open(defaults_path) as f:
        config = yaml.safe_load(f)

    models_path = _CONFIG_DIR / "models.yaml"
    if models_path.exists():
        with open(models_path) as f:
            config["crew_models"] = yaml.safe_load(f)

    _config_cache = config
    return config


def get_model_for_crew(crew_name: str) -> str:
    """Resolve the LLM model for a specific crew."""
    config = load_config()
    crew_models = config.get("crew_models", {}).get("crews", {})
    override_key = crew_models.get(crew_name)
    if override_key is None:
        return config["llm"]["default_model"]
    return config["llm"]["overrides"].get(override_key, config["llm"]["default_model"])
