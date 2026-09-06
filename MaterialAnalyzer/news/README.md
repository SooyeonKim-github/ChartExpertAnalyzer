# MaterialAnalyzer News Pipeline

`MaterialAnalyzer.news` is the deterministic source-agnostic material pipeline used by MaterialAnalyzer.

## Current pipeline

```text
NewsCollector V1.5
        ↓
ArticleCluster V1.1
        ↓
EventExtractor V1.1
        ↓
NoveltyAnalyzer V1.1
        ↓
MaterialScorer V1.1
        ↓
TickerLinker V1.2
        ↓
HistoricalMaterialRangeCollector V1
        ↓
MaterialBacktester  ← next
```

Semantic similarity, embeddings, fuzzy company matching, and LLM inference are intentionally disabled in the deterministic linking stages.

## Main live execution order

```bat
MaterialAnalyzer\news\run_news_collector.bat
MaterialAnalyzer\news\run_article_cluster.bat
MaterialAnalyzer\news\run_event_extractor.bat
MaterialAnalyzer\news\run_novelty_analyzer.bat
MaterialAnalyzer\news\run_material_scorer.bat
MaterialAnalyzer\news\run_ticker_linker.bat
```

## MaterialScorer V1.1

Output: `MaterialAnalyzer\data\material_score_report.csv`

```text
85-100  STRONG
70-84   CONFIRMED
55-69   WATCH
0-54    REJECT
```

Routine governance housekeeping has capped financial impact so ordinary shareholder-record dates and ordinary shareholder-meeting notices/results do not become strong catalysts simply because they are official disclosures.

## TickerLinker V1.2

```bat
MaterialAnalyzer\news\run_ticker_linker.bat
```

Outputs:

```text
MaterialAnalyzer\data\ticker_link_report.csv
MaterialAnalyzer\data\ticker_link_unresolved.csv
```

Ticker-master provider order:

```text
1. MarketData.service shared pykrx transport
2. FinanceDataReader StockListing("KRX")
3. direct pykrx
4. existing ticker_master_krx.csv
5. tracked ticker_master.csv + proven EventExtractor bootstrap pairs
```

Relation types:

```text
DIRECT    base 1.00
SUPPLIER  base 0.80
CUSTOMER  base 0.70
SECTOR    base 0.50
THEME     base 0.35
```

For `SECTOR` / `THEME`:

```text
effective_relation_weight = base relation weight × mapping_relevance
ticker_material_score     = material_score × effective_relation_weight
```

Company-specific events never fan out to broad themes. Company-less industry/policy events must pass `ThemeMaterialityGuard`. Meetings, forums, education, contests, ceremonies, and similar weak triggers are penalized while concrete investment, construction, capacity, supply, production, industrial-belt activation, and other real-economy triggers can pass.

## HistoricalMaterialRangeCollector V1

Run:

```bat
MaterialAnalyzer\run_material_range.bat
```

Example:

```text
Date range YYYYMMDD~YYYYMMDD: 20260101~20260630
```

Optional direct CLI:

```bat
python -m MaterialAnalyzer.run_material_range --date-range 20260101~20260630 --warmup-days 180 --chunk-days 7
```

Historical storage is isolated from the live DB:

```text
Live       MaterialAnalyzer\data\news.db
Historical MaterialAnalyzer\data\history\material_history.db
```

The requested range automatically adds 180 days of context by default so NoveltyAnalyzer can distinguish `NEW_EVENT` from older `FOLLOW_UP` / `CONFIRMATION` history. Context events remain in `material_history.csv` with `context_only=1` but are not emitted into the backtest-eligible file.

### Point-in-time safeguards

Historical backfill never uses today's collection timestamp as the event signal time.

```text
Historical first_seen_at = published_at

EXACT timestamp <= 15:30 on a trading day
→ same trading day

EXACT timestamp > 15:30
→ next trading day

DATE-only / UNKNOWN-time historical disclosure
→ next trading day

weekend / exchange holiday
→ next actual trading day when MarketData calendar is available
```

This deliberately biases ambiguous publication timing later rather than introducing look-ahead.

### Source capabilities

```text
DART   RANGE_API   - date range + full pagination, 7-day resumable chunks
KIND   LIVE_ONLY   - skipped in historical mode; DART is canonical historical disclosure source
MOTIR  PAGED_LIST  - best-effort historical board traversal
MSIT   PAGED_LIST  - best-effort historical board traversal
MCEE   PAGED_LIST  - best-effort historical board traversal
MFDS   PAGED_LIST  - best-effort historical board traversal
FSC    PAGED_LIST  - best-effort historical board traversal
```

Government boards differ in pagination behavior, so their historical traversal is intentionally best-effort. Every covered date is stored in `historical_source_coverage`; failures remain visible instead of being silently treated as "no news".

### Resume model

History DB adds:

```text
historical_range_runs
historical_range_chunks
historical_source_coverage
```

DART chunks that reach `COMPLETE` are skipped automatically on rerun. Failed chunks remain retryable. Raw historical articles are retained, so changing Event/Novelty/Score/Ticker rules does not require re-downloading history.

Derived-only rebuild:

```bat
python -m MaterialAnalyzer.run_material_range --date-range 20260101~20260630 --no-collect
```

Collection-only mode:

```bat
python -m MaterialAnalyzer.run_material_range --date-range 20260101~20260630 --collection-only
```

After collection, the derived layers are rebuilt in deterministic chronological order:

```text
raw articles
 ↓
ArticleCluster
 ↓
EventExtractor
 ↓
NoveltyAnalyzer   # first_seen_at ASC
 ↓
MaterialScorer
 ↓
TickerLinker
```

Outputs:

```text
MaterialAnalyzer\data\history\material_history.db
MaterialAnalyzer\data\history\material_history.csv
MaterialAnalyzer\data\history\material_history_backtest.csv
MaterialAnalyzer\data\history\historical_source_coverage.csv
MaterialAnalyzer\data\history\cluster_report.csv
MaterialAnalyzer\data\history\event_report.csv
MaterialAnalyzer\data\history\novelty_report.csv
MaterialAnalyzer\data\history\material_score_report.csv
MaterialAnalyzer\data\history\ticker_link_report.csv
MaterialAnalyzer\data\history\ticker_link_unresolved.csv
```

`material_history_backtest.csv` includes only requested-range rows that have a known publication time/date, a resolved `market_date`, a ticker link, and no failed representative-source coverage marker. `material_history.csv` retains context/out-of-range rows with explicit eligibility flags instead of deleting them.

Recommended first validation run is six months, for example `20260101~20260630`, before expanding to several years.

## Next stage: MaterialBacktester

MaterialBacktester should read `material_history_backtest.csv`, attach D+1 / D+5 / D+10 / D+20 / D+40 / D+60 returns, and compare performance by material status/score, polarity, event type, novelty status, relation type, theme materiality, and ticker-material-score bands. Those results will then calibrate score thresholds and relation weights.
