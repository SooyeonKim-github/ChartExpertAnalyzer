from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class MasterConfigError(ValueError):
    pass


@dataclass(frozen=True)
class MasterCatalog:
    sectors: dict[str, dict[str, Any]]
    themes: dict[str, dict[str, Any]]
    positive_direction_keywords: tuple[str, ...]
    negative_direction_keywords: tuple[str, ...]

    @classmethod
    def load(cls, sector_path: str | Path, theme_path: str | Path) -> "MasterCatalog":
        sector_data = _load_yaml(Path(sector_path))
        theme_data = _load_yaml(Path(theme_path))

        sectors = sector_data.get("sectors") or {}
        themes = theme_data.get("themes") or {}
        direction = theme_data.get("direction_keywords") or {}

        if not isinstance(sectors, dict) or not sectors:
            raise MasterConfigError("sector_master.yaml must contain a non-empty 'sectors' mapping")
        if not isinstance(themes, dict) or not themes:
            raise MasterConfigError("theme_master.yaml must contain a non-empty 'themes' mapping")

        _validate_sector_master(sectors)
        _validate_theme_master(themes, sectors)

        return cls(
            sectors=sectors,
            themes=themes,
            positive_direction_keywords=tuple(_as_list(direction.get("positive"))),
            negative_direction_keywords=tuple(_as_list(direction.get("negative"))),
        )

    def sector_name(self, sector: str) -> str:
        return str((self.sectors.get(sector) or {}).get("name_ko") or sector)

    def subsector_name(self, subsector: str) -> str:
        for sector_cfg in self.sectors.values():
            cfg = (sector_cfg.get("subsectors") or {}).get(subsector)
            if cfg:
                return str(cfg.get("name_ko") or subsector)
        return subsector


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise MasterConfigError(f"YAML root must be a mapping: {path}")
    return data


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    raise MasterConfigError(f"Expected list/string, got {type(value).__name__}")


def _validate_sector_master(sectors: dict[str, dict[str, Any]]) -> None:
    seen_subsectors: set[str] = set()
    for sector, cfg in sectors.items():
        if not isinstance(cfg, dict):
            raise MasterConfigError(f"Sector '{sector}' must be a mapping")
        if not cfg.get("name_ko"):
            raise MasterConfigError(f"Sector '{sector}' is missing name_ko")
        subsectors = cfg.get("subsectors") or {}
        if not isinstance(subsectors, dict):
            raise MasterConfigError(f"Sector '{sector}'.subsectors must be a mapping")
        for subsector, sub_cfg in subsectors.items():
            if subsector in seen_subsectors:
                raise MasterConfigError(f"Duplicate subsector code: {subsector}")
            seen_subsectors.add(subsector)
            if not isinstance(sub_cfg, dict) or not sub_cfg.get("name_ko"):
                raise MasterConfigError(f"Subsector '{subsector}' requires name_ko")


def _validate_theme_master(
    themes: dict[str, dict[str, Any]],
    sectors: dict[str, dict[str, Any]],
) -> None:
    valid_subsectors = {
        key
        for sector_cfg in sectors.values()
        for key in (sector_cfg.get("subsectors") or {}).keys()
    }
    for theme, cfg in themes.items():
        if not isinstance(cfg, dict):
            raise MasterConfigError(f"Theme '{theme}' must be a mapping")
        if not cfg.get("name_ko"):
            raise MasterConfigError(f"Theme '{theme}' is missing name_ko")
        for sector in _as_list(cfg.get("sectors")):
            if sector not in sectors:
                raise MasterConfigError(f"Theme '{theme}' references unknown sector '{sector}'")
        for subsector in _as_list(cfg.get("subsectors")):
            if subsector not in valid_subsectors:
                raise MasterConfigError(
                    f"Theme '{theme}' references unknown subsector '{subsector}'"
                )
        if not (_as_list(cfg.get("strong_keywords")) or _as_list(cfg.get("keywords"))):
            raise MasterConfigError(f"Theme '{theme}' has no keywords")
        direction = str(cfg.get("default_direction") or "NEUTRAL").upper()
        if direction not in {"POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"}:
            raise MasterConfigError(
                f"Theme '{theme}' has invalid default_direction '{direction}'"
            )
