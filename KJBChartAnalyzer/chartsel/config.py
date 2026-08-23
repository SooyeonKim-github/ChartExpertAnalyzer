from __future__ import annotations
from pathlib import Path
import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'config' / 'default.yaml'

def load_config(path: str | None = None) -> dict:
    target = Path(path) if path else DEFAULT_PATH
    with open(target, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
