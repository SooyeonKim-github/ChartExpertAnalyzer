# NewsCollector V1.5

`MaterialAnalyzer.news` is the source-agnostic collection layer for material/news data.

It is intentionally separate from the legacy `MaterialAnalyzer.collectors` package so the existing workflow keeps working while sources are migrated.

## Architecture

```text
source_master.csv
source_endpoint_master.csv
        |
        v
CollectorFactory
        |
        v
discover
        |
        +-- known immutable candidate? -> SKIP before fetch
        +-- known mutable candidate?   -> latest 3 only re-fetch
        |
        v
fetch -> parse -> RawArticle
        |
        v
ArticleNormalizer
        |
        +-- exact duplicate checker
        +-- validator / classifier
        |
        v
SQLite: MaterialAnalyzer/data/news.db
        |
        +-- articles
        +-- source_states
        +-- collection_runs
```

## Live official sources

Current live endpoints:

- `DART_DISCLOSURE`
- `KIND_TODAY`
- `MOTIR_PRESS`
- `MSIT_PRESS`
- `MCEE_PRESS`
- `MFDS_PRESS`
- `FSC_PRESS`

The remaining source master entries stay disabled until their current endpoint/selectors and usage policy are verified.

## Incremental collection policy

`external_id` is stored as a first-class article field. If it is unavailable, normalized URL hash is used as the incremental fallback.

Default V1.5 behavior:

- DART / KIND: immutable. Known candidates are skipped before fetch.
- Government press releases: mutable. The latest 3 candidates are re-fetched so corrections can be detected; older known candidates are skipped.
- New candidates are always fetched and inserted.

Expected repeat-run behavior is therefore closer to:

```text
DART  found=100 fetch=0  skip=100
KIND  found=100 fetch=0  skip=100
MOTIR found=10  fetch=3  skip=7
MSIT  found=50  fetch=3  skip=47
...
```

instead of fetching every discovered item again.

## Source health

Each endpoint run is persisted to `collection_runs`, while the latest endpoint status is stored in `source_states`.

Health states:

- `HEALTHY`: latest run completed without failures
- `DEGRADED`: 1-2 consecutive failed/partial runs
- `FAILED`: 3 or more consecutive failed/partial runs
- `UNKNOWN`: no completed health evaluation yet

Stored state includes last success/failure time, consecutive failures, last discovered/fetched/inserted/updated/skipped/failed counts, error details, and latest checkpoint.

Show current source health:

```bat
python -m MaterialAnalyzer.news.show_health
```

Also show recent run history:

```bat
python -m MaterialAnalyzer.news.show_health --runs 20
```

## Run

```bat
MaterialAnalyzer\news\run_news_collector.bat
```

or:

```bat
python -m MaterialAnalyzer.news.main_collect
```

OpenDART requires `OPENDART_API_KEY`.

The batch script runs the V1.5 smoke test before live collection and pauses at the end unless `NEWS_COLLECTOR_NO_PAUSE=1` is set.

## Collector types

- `DART_API`
- `KIND_HTML`
- `GOV_RSS`
- `GOV_HTML_LIST`
- `GOV_AGGREGATOR`
- `NEWS_SECTION`
- `RSS`
- `API`

## Configuration policy

`source_master.csv` answers **who the source is**.

`source_endpoint_master.csv` answers **where/how to collect it**.

`source_material_map.csv` answers **which material/sector the source is strong at**.

Official sources use `FULL` where permitted. News/industry sources default to `DISCOVERY`, and full-body collection is activated only after source-specific review.

## Next step

After V1.5 is stable, the next major stage is `ArticleCluster`: group DART/KIND/government/media articles that describe the same underlying event before EventExtractor and MaterialScorer run.
