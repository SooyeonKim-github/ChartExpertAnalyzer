from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: str | Path) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    for section in ("universe", "data", "trend"):
        if section not in cfg:
            raise ValueError(f"Missing config section: {section}")
    return cfg
