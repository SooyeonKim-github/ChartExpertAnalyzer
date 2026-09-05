# MaterialAnalyzer News Pipeline

`MaterialAnalyzer.news` is the source-agnostic collection, clustering, event-structuring, and novelty layer used by MaterialAnalyzer.

## Current pipeline

```text
7 live official sources
        ↓
NewsCollector V1.5
        ↓
ArticleNormalizer / Exact dedupe
        ↓
Incremental Collection
        ↓
Source Health / Run History
        ↓
ArticleCluster V1.1 (rule-only)
        ↓
cluster_report.csv
        ↓
EventExtractor V1.1 (title-first rule-based)
        ↓
material_events
        ↓
event_report.csv
        ↓
NoveltyAnalyzer V1 (rule-only family + delta)
        ↓
event_families + event_novelty
        ↓
novelty_report.csv
```

Semantic similarity, embeddings, and LLM clustering are intentionally disabled in ArticleCluster and NoveltyAnalyzer V1.

## NewsCollector

```bat
MaterialAnalyzer\news\run_news_collector.bat
```

OpenDART requires `OPENDART_API_KEY`.

Repeated collection is incremental:
- DART/KIND: known items are skipped before fetch.
- Government sources: latest 3 items are re-fetched to capture edits.
- `source_states` and `collection_runs` persist endpoint health/history.

Health:

```bat
python -m MaterialAnalyzer.news.show_health --runs 20
```

## ArticleCluster V1.1

Run and rebuild current raw articles with V1.1 rules:

```bat
MaterialAnalyzer\news\run_article_cluster.bat
```

Manual incremental mode:

```bat
python -m MaterialAnalyzer.news.run_article_cluster
```

Manual rebuild:

```bat
python -m MaterialAnalyzer.news.run_article_cluster --rebuild
```

Output:

```text
MaterialAnalyzer\data\cluster_report.csv
```

### V1.1 disclosure safeguards

- Exact DART/KIND receipt id is the strongest key.
- DART/KIND ids such as `20260904900749` and `20260904000749` use a bridge key based on date + final sequence.
- The bridge key still requires company/stock evidence and title similarity.
- If the same company + normalized title + market date contains multiple DART or KIND filings, generic title matching is blocked.
- Numeric conflicts are penalized.
- Same-source different receipt ids are never merged only because the filing title is generic.

Raw `articles` are never deleted or collapsed.

Cluster storage:
- `article_clusters`
- `article_cluster_members`

## EventExtractor V1.1

EventExtractor converts one cluster into one structured event. It does not merge clusters.

Run:

```bat
MaterialAnalyzer\news\run_event_extractor.bat
```

Manual incremental mode:

```bat
python -m MaterialAnalyzer.news.run_event_extractor
```

Manual rebuild:

```bat
python -m MaterialAnalyzer.news.run_event_extractor --rebuild
```

Output:

```text
MaterialAnalyzer\data\event_report.csv
```

Storage:

```text
material_events
```

### V1.1 classification policy

Event type classification is layered to prevent body-text contamination:

```text
TITLE
  ↓ if UNKNOWN
SUMMARY
  ↓ if UNKNOWN
BODY high-precision rules only
```

Broad words such as `AI`, `지원금`, `배터리`, or `제재` found only somewhere in a government press-release body do not automatically determine the event type.

Stage rules use specific phrases before broad words:
- `승인 신청`, `허가 신청` -> `REQUESTED`
- plan/target/review -> `PLANNED`
- contract/order/decision -> `CONFIRMED`
- approval/license -> `APPROVED`
- start/operation/launch -> `STARTED`
- completion -> `COMPLETED`
- trading-halt/designation release -> `RELEASED`

`REQUESTED` events are tracked but are not promoted as confirmed material candidates.

### Meaningful numeric facts

`quantified=1` requires a business-meaningful numeric fact such as:
- money
- percent
- capacity (`GW`, `MW`, `GWh`, ...)
- quantity (`척`, `대`, `개`, `명`, ...)
- duration
- clinical phase

Calendar years, phone numbers, article ids, and other bare numbers are not enough to set `quantified=1`.

### Material candidate filter

Routine/administrative events are stored as events but excluded from downstream material scoring with `material_candidate=0`, including examples such as:
- market warning / investment caution
- short-selling restriction
- ETF/ETN administrative changes
- routine securities filings
- routine ownership filings
- routine IR notices
- unknown events
- application/request stage events

Event extraction is incremental and version-aware. If neither the cluster nor extractor version changes, a repeat run should process zero events.

## NoveltyAnalyzer V1

NoveltyAnalyzer analyzes material events over time and determines whether each event is actually new information or a continuation of an existing event family.

Run:

```bat
MaterialAnalyzer\news\run_novelty_analyzer.bat
```

Manual incremental mode:

```bat
python -m MaterialAnalyzer.news.run_novelty_analyzer
```

Manual rebuild:

```bat
python -m MaterialAnalyzer.news.run_novelty_analyzer --rebuild
```

The batch runner forwards arguments, so this also works:

```bat
MaterialAnalyzer\news\run_novelty_analyzer.bat --rebuild
```

Output:

```text
MaterialAnalyzer\data\novelty_report.csv
```

Storage:
- `event_families`
- `event_novelty`

### Novelty statuses

- `NEW_EVENT`: no sufficiently related prior material event.
- `FOLLOW_UP`: same event family with meaningful new information such as stage, amount, counterpart, or polarity change.
- `CONFIRMATION`: same event family confirmed by a stronger/new source without a substantive event delta.
- `REHASH`: same event family repeated without meaningful new information.
- `MARKET_REACTION`: price/market reaction article rather than a new catalyst.

### Event-family matching

V1 is deterministic and rule-based. It uses:
- ticker/company identity
- event type or explicitly compatible type
- normalized title lexical similarity
- token overlap
- event-specific informative title anchors
- meaningful numeric overlap/change
- time distance

The auto-family threshold is `68`.

Important safeguards:
- different named companies/tickers cannot join only because titles are similar;
- same company + same event type is not enough;
- generic words such as `계약`, `수주`, `투자`, `승인`, and company names are removed when checking event-specific anchors;
- same-company unrelated contracts such as `LNG선 공급계약` and `반도체 장비 공급계약` stay in separate families unless stronger evidence links them;
- company-less government events require stronger lexical evidence.

### Delta detection

Once a prior family parent is found, NoveltyAnalyzer checks:
- `stage_changed`
- `stage_progressed`
- `number_changed`
- `company_changed`
- `polarity_changed`
- `source_reliability_increased`
- `confirmation_source_added`

These are stored with `new_information_count`, parent event, family id, and novelty reason.

### Novelty scoring

V1 stores a 0-100 `novelty_score` for later MaterialScorer use.

Typical interpretation:
- `NEW_EVENT`: 100
- `FOLLOW_UP`: 60-100 depending on delta strength
- `CONFIRMATION`: 55-75
- `REHASH`: 15
- `MARKET_REACTION`: 5

Novelty analysis is incremental and version-aware. Only `material_candidate=1` events are analyzed by default, plus explicitly classified `MARKET_REACTION` articles so market reactions can be suppressed later. A repeat run with no EventExtractor changes should process zero events.

## Next stage

The next downstream layer is `MaterialScorer`, which will combine event certainty, financial impact, quantification, novelty, source reliability, and confirmation into a final material score/status.
