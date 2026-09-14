# ThemeSectorAnalyzer V1.2.1

V1.2.1 is a live-data precision/recall tuning layer built from the first V1.2 report.

## Override model

`MasterCatalog.load()` automatically loads these optional files when present next to the base masters:

- `sector_master_overrides.yaml`
- `theme_master_overrides.yaml`

Mappings are recursively merged. Lists replace base lists intentionally, allowing generic aliases or keywords to be removed without rewriting the base taxonomy.

## Sector precision fixes

The following generic tokens were removed from broad sector classification:

- `POWER_ENERGY`: standalone `발전`
- `ENTERTAINMENT_MEDIA`: standalone `콘텐츠`
- `CONSUMER_RETAIL`: standalone `소비`

This prevents examples such as `양자 분야 발전방향`, `의약정보 콘텐츠`, and `한국소비자원` from creating unrelated sectors.

## Existing-theme recall fixes

- `BIO_APPROVAL`: adds `신약 허가`, `국내 개발 신약 허가`, `품목 허가` variants.
- `RENEWABLE_INVESTMENT`: separates investment expressions from general renewable-energy policy.
- `ROBOT_AUTOMATION`: adds `AI 로봇 실증`, `로봇 실증`, `피지컬 AI` variants.

## New themes from SECTOR_ONLY evidence

- `AI_DATA_CENTER_POLICY`
- `PHYSICAL_AI_POLICY`
- `AI_GLOBAL_COOPERATION`
- `AI_INDUSTRY_SUPPORT`
- `ESSENTIAL_DRUG_SUPPLY`
- `RENEWABLE_POLICY`
- `SOLAR_INDUSTRY_SUPPORT`
- `HOUSING_FINANCE_SUPPORT`
- `TRADE_FINANCE_SUPPORT`
- `CLIMATE_FINANCE`
- `ENERGY_SECURITY`
- `ICT_EXPORT_GROWTH`

The base V1.2 taxonomy remains unchanged. With the override layer loaded, the effective catalog is 90 themes.

## Validation

`theme_sector_smoke_test.py` now checks both V1.2 precision regressions and V1.2.1 live-data cases, including sector false-positive suppression and promotion of representative SECTOR_ONLY headlines.
