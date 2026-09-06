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
HistoricalMaterialRangeCollector V1.1
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

Company-specific events never fan out to broad themes. Company-less industry/policy events must pass `ThemeMaterialityGuard`.

## HistoricalMaterialRangeCollector V1.1

Run:

```bat
MaterialAnalyzer\run_material_range.bat
```

Example:

```text
Date range YYYYMMDD~YYYYMMDD: 20260101~20260831
```

Historical storage is isolated from the live DB:

```text
Live        MaterialAnalyzer\data\news.db
Historical  MaterialAnalyzer\data\history\material_history.db
```

The requested range automatically adds 180 days of context by default so NoveltyAnalyzer can distinguish `NEW_EVENT` from older `FOLLOW_UP` / `CONFIRMATION` history.

### V1.1 performance path

Historical DART no longer uses the ordinary article-by-article CollectorService path. OpenDART range metadata is immutable, so V1.1 uses:

```text
DART date chunk
  ↓
full API pagination
  ↓
existing receipt IDs cached once in memory
  ↓
normalize only new rows
  ↓
single bulk SQLite upsert transaction
```

The history DB uses WAL, `synchronous=NORMAL`, memory temp storage, a larger cache, and a busy timeout. These settings apply only to `material_history.db`; the live `news.db` keeps its normal settings.

Raw DART disclosures are still retained completely. To avoid sending hundreds of thousands of routine rows into ArticleCluster, V1.1 marks obvious non-backtest/routine rows as:

```text
SKIP_HISTORY_NONLISTED
SKIP_HISTORY_ROUTINE
```

Examples of routine skips include periodic reports, ordinary shareholder-meeting notices, ownership-form reports, prospectus/issuance-result forms, and similar repetitive filings. Strong catalysts such as supply contracts, capital raises, CB/BW/EB, M&A, facility investment, major share acquisition/disposal, buyback/cancellation, dividends, ownership control changes, lawsuits, trading suspension/delisting, and earnings-surprise disclosures remain eligible.

Previously collected DART rows are reclassified before every derived rebuild, so a resumed V1 database automatically receives the V1.1 prefilter without re-downloading completed chunks.

ArticleCluster ignores only `SKIP_HISTORY_*` rows. Live articles remain unaffected because their normal status is `PENDING`.

### Point-in-time safeguards

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
DART   RANGE_API   - date range + full pagination, resumable chunks
KIND   LIVE_ONLY   - DART is canonical historical disclosure source
MOTIR  PAGED_LIST  - best-effort historical traversal
MSIT   PAGED_LIST  - best-effort historical traversal
MCEE   PAGED_LIST  - best-effort historical traversal
MFDS   PAGED_LIST  - best-effort historical traversal
FSC    PAGED_LIST  - best-effort historical traversal
```

Every covered date is stored in `historical_source_coverage`; failures remain visible instead of being silently treated as "no news".

### Resume and execution modes

DART chunks that reach `COMPLETE` are skipped automatically on rerun. Failed chunks remain retryable.

Full collection + derived rebuild:

```bat
python -m MaterialAnalyzer.run_material_range --date-range 20260101~20260831
```

Collect/resume raw history only:

```bat
python -m MaterialAnalyzer.run_material_range --date-range 20260101~20260831 --collect-only
```

Rebuild derived layers without network collection:

```bat
python -m MaterialAnalyzer.run_material_range --date-range 20260101~20260831 --derive-only
```

Backward-compatible aliases `--collection-only` and `--no-collect` remain supported.

### Derived pipeline

Before clustering V1.1 prints prefilter statistics such as raw/eligible/routine/non-listed counts. ArticleCluster prints progress every 5,000 eligible rows.

```text
raw articles
 ↓
HistoricalAnalysisPrefilter
 ↓
ArticleCluster          # progress every 5,000
 ↓
EventExtractor
 ↓
NoveltyAnalyzer         # chronological
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

`material_history_backtest.csv` contains the requested-range rows that are eligible for the future-return backtest. Context and ineligible rows stay in raw/history storage instead of being deleted.

## Next stage: MaterialBacktester

MaterialBacktester should read `material_history_backtest.csv`, attach D+1 / D+5 / D+10 / D+20 / D+40 / D+60 returns, and compare performance by material status/score, polarity, event type, novelty status, relation type, theme materiality, and ticker-material-score bands. Those results will then calibrate score thresholds and relation weights.
