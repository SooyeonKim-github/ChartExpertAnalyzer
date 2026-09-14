from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class MasterConfigError(ValueError):
    pass


_VALID_DIRECTIONS = {"POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"}
_VALID_SCOPES = {"all", "title_summary", "title", "summary"}
_RULE_LIST_KEYS = {"require_any", "require_all", "exclude_any"}


@dataclass(frozen=True)
class MasterCatalog:
    sectors: dict[str, dict[str, Any]]
    theme_families: dict[str, dict[str, Any]]
    themes: dict[str, dict[str, Any]]
    positive_direction_keywords: tuple[str, ...]
    negative_direction_keywords: tuple[str, ...]

    @classmethod
    def load(cls, sector_path: str | Path, theme_path: str | Path) -> "MasterCatalog":
        sector_path = Path(sector_path)
        theme_path = Path(theme_path)

        sector_data = _load_yaml(sector_path)
        theme_data = _load_yaml(theme_path)

        # V1.2.1: production tuning is kept in small override files so the base
        # taxonomy remains stable and live-data adjustments are easy to review.
        sector_override = sector_path.with_name(f"{sector_path.stem}_overrides.yaml")
        theme_override = theme_path.with_name(f"{theme_path.stem}_overrides.yaml")
        if sector_override.exists():
            sector_data = _deep_merge(sector_data, _load_yaml(sector_override))
        if theme_override.exists():
            theme_data = _deep_merge(theme_data, _load_yaml(theme_override))

        sectors = sector_data.get("sectors") or {}
        theme_families = theme_data.get("theme_families") or {}
        themes = theme_data.get("themes") or {}
        direction = theme_data.get("direction_keywords") or {}

        if not isinstance(sectors, dict) or not sectors:
            raise MasterConfigError("sector_master.yaml must contain a non-empty 'sectors' mapping")
        if not isinstance(theme_families, dict) or not theme_families:
            raise MasterConfigError("theme_master.yaml must contain a non-empty 'theme_families' mapping")
        if not isinstance(themes, dict) or not themes:
            raise MasterConfigError("theme_master.yaml must contain a non-empty 'themes' mapping")

        _validate_sector_master(sectors)
        _validate_theme_families(theme_families)
        _validate_theme_master(themes, sectors, theme_families)

        return cls(
            sectors=sectors,
            theme_families=theme_families,
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

    def family_name(self, family: str) -> str:
        return str((self.theme_families.get(family) or {}).get("name_ko") or family)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise MasterConfigError(f"YAML root must be a mapping: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = _deep_merge(current, value)
        else:
            # Lists intentionally replace instead of append. This lets precision
            # tuning remove generic aliases/keywords from the base taxonomy.
            result[key] = value
    return result


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


def _validate_theme_families(theme_families: dict[str, dict[str, Any]]) -> None:
    for family, cfg in theme_families.items():
        if not isinstance(cfg, dict):
            raise MasterConfigError(f"Theme family '{family}' must be a mapping")
        if not cfg.get("name_ko"):
            raise MasterConfigError(f"Theme family '{family}' is missing name_ko")


def _validate_theme_master(
    themes: dict[str, dict[str, Any]],
    sectors: dict[str, dict[str, Any]],
    theme_families: dict[str, dict[str, Any]],
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

        family = str(cfg.get("family") or "").strip()
        if not family:
            raise MasterConfigError(f"Theme '{theme}' is missing family")
        if family not in theme_families:
            raise MasterConfigError(f"Theme '{theme}' references unknown family '{family}'")

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
        if direction not in _VALID_DIRECTIONS:
            raise MasterConfigError(
                f"Theme '{theme}' has invalid default_direction '{direction}'"
            )

        fixed_direction = str(cfg.get("fixed_direction") or "").upper()
        if fixed_direction and fixed_direction not in _VALID_DIRECTIONS:
            raise MasterConfigError(
                f"Theme '{theme}' has invalid fixed_direction '{fixed_direction}'"
            )

        rules = cfg.get("rules") or {}
        if not isinstance(rules, dict):
            raise MasterConfigError(f"Theme '{theme}'.rules must be a mapping")

        scope = str(rules.get("scope") or "all").lower()
        if scope not in _VALID_SCOPES:
            raise MasterConfigError(
                f"Theme '{theme}'.rules.scope must be one of {sorted(_VALID_SCOPES)}"
            )

        unknown_keys = set(rules) - ({"scope"} | _RULE_LIST_KEYS)
        if unknown_keys:
            raise MasterConfigError(
                f"Theme '{theme}'.rules has unsupported keys: {sorted(unknown_keys)}"
            )

        for key in _RULE_LIST_KEYS:
            _as_list(rules.get(key))
