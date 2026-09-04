# NewsCollector V1

`MaterialAnalyzer.news` is the new source-agnostic collection layer for material/news data.

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
discover -> fetch -> parse
        |
        v
RawArticle
        |
        v
CollectorService
        |
        +-- normalizer
        +-- validator
        +-- classifier
        +-- exact duplicate checker
        |
        v
SQLite: MaterialAnalyzer/data/news.db
```

## Collector types

- `DART_API`
- `KIND_HTML`
- `GOV_RSS`
- `GOV_HTML_LIST`
- `GOV_AGGREGATOR`
- `NEWS_SECTION`
- `RSS`
- `API`

The 36-source master is committed, but only endpoints with `enabled=1` are executed. DART is enabled by default. Source-specific HTML/RSS endpoints remain disabled until their current URL/selectors and usage policy are verified. This is deliberate: an unverified selector must not silently collect the wrong text.

## Run

```bat
MaterialAnalyzer\news\run_news_collector.bat
```

or

```bat
python -m MaterialAnalyzer.news.main_collect
```

OpenDART requires `OPENDART_API_KEY`.

## Configuration policy

`source_master.csv` answers **who the source is**.

`source_endpoint_master.csv` answers **where/how to collect it**.

`source_material_map.csv` answers **which material/sector the source is strong at**.

Official sources use `FULL` where permitted. News/industry sources default to `DISCOVERY`, and full-body collection is activated only after source-specific review.

## Next step

`PassThroughNormalizer` is intentionally minimal. The next implementation stage is `ArticleNormalizer`, which will own canonical URL cleanup, Unicode/whitespace normalization, title cleanup, clean-body rules, timestamps, market date, and stable hash generation.
