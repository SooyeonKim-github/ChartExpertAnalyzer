# ThemeSectorAnalyzer V1.2

ThemeSectorAnalyzer V1.2 classifies market/industry materials without linking them to individual tickers.

## Design

```text
ArticleCluster representative
        ↓
Sector classifier
        ↓
Theme rule classifier
        ↓
Theme Family / Theme / Direction
        ↓
theme_sector_report.csv
theme_daily_summary.csv
```

The Python classifier is generic. Theme-specific precision logic belongs in `data/reference/theme_master.yaml`.

## Theme Family

Every theme must reference one `family` defined in `theme_families`.

Example:

```yaml
theme_families:
  POWER_NUCLEAR:
    name_ko: 전력·원전

themes:
  NUCLEAR_EXPORT:
    name_ko: 원전 수출
    family: POWER_NUCLEAR
```

V1.2 ships with 17 families and 78 core themes.

## Rule grammar

Each theme may define a `rules` mapping.

```yaml
rules:
  scope: title_summary
  require_any: [반도체, AI칩, GPU]
  require_all: [관세]
  exclude_any: [단순 협의, 정례회의]
```

### `scope`

Supported values:

```text
all            title + summary + body
title_summary  title + summary
title          title only
summary        summary only
```

`scope` applies to `require_any`, `require_all`, and `exclude_any`.

### `require_any`

At least one keyword must be present in the configured scope.

### `require_all`

Every listed keyword must be present in the configured scope.

### `exclude_any`

If any listed keyword is present, the theme is rejected.

## Direction

Normal themes infer direction from global and per-theme positive/negative keywords.

Themes whose direction is structurally ambiguous can use `fixed_direction`.

```yaml
RATE_HIKE:
  default_direction: MIXED
  fixed_direction: MIXED
```

## Example: nuclear export

```yaml
NUCLEAR_EXPORT:
  name_ko: 원전 수출
  family: POWER_NUCLEAR
  sectors: [POWER_ENERGY, CONSTRUCTION]
  subsectors: [NUCLEAR]
  strong_keywords: [원전 수출, 원전 수주, SMR 수출]
  keywords: [원전 프로젝트, 원전 건설, 원전 협력]
  rules:
    scope: title_summary
    require_any: [수출, 수주, 해외, 계약, 체코, 폴란드]
```

This prevents domestic SMR policy articles from being classified as export catalysts.

## Example: automobile tariff

```yaml
AUTO_TARIFF_RISK:
  name_ko: 자동차 관세 리스크
  family: AUTO_MOBILITY
  sectors: [AUTOMOTIVE]
  strong_keywords: [자동차 관세, 완성차 관세]
  keywords: [차량 관세]
  rules:
    scope: title_summary
    require_any: [자동차, 완성차, 차량]
    require_all: [관세]
```

## Output additions

V1.2 adds these columns to detail and daily-summary reports:

```text
theme_family
theme_family_name_ko
```

## Validation

Run:

```bat
MaterialAnalyzer\news\run_theme_sector_analyzer.bat
```

The batch file runs `theme_sector_smoke_test` before analyzing the latest seven calendar days. The smoke test covers family loading, theme-count range, scope, require_any, require_all, exclude_any, fixed direction, and report columns.
