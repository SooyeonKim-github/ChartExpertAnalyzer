# MaterialAnalyzer News Pipeline

`MaterialAnalyzer.news` is the source-agnostic collection, clustering, event-structuring, novelty, and material-scoring layer used by MaterialAnalyzer.

## Current pipeline

```text
7 live official sources
        ↓
NewsCollector V1.5
        ↓
ArticleNormalizer / Exact dedupe
        ↓
ArticleCluster V1.1 (rule-only)
        ↓
EventExtractor V1.1 (title-first rule-based)
        ↓
material_events
        ↓
NoveltyAnalyzer V1.1 (rule-only family + delta + litigation guard)
        ↓
event_families + event_novelty
        ↓
MaterialScorer V1 (deterministic 100-point score)
        ↓
material_scores
```

Semantic similarity, embeddings, and LLM clustering are intentionally disabled in ArticleCluster and NoveltyAnalyzer.

## Main execution order

```bat
MaterialAnalyzer\news\run_news_collector.bat
MaterialAnalyzer\news\run_article_cluster.bat
MaterialAnalyzer\news\run_event_extractor.bat
MaterialAnalyzer\news\run_novelty_analyzer.bat
MaterialAnalyzer\news\run_material_scorer.bat
```

Each stage is incremental unless `--rebuild` is explicitly used.

## NewsCollector

```bat
MaterialAnalyzer\news\run_news_collector.bat
```

OpenDART requires `OPENDART_API_KEY`.

Repeated collection is incremental:
- DART/KIND: known items are skipped before fetch.
- Government sources: latest items may be re-fetched to capture edits.
- `source_states` and `collection_runs` persist endpoint health/history.

## ArticleCluster V1.1

```bat
MaterialAnalyzer\news\run_article_cluster.bat
```

Output:

```text
MaterialAnalyzer\data\cluster_report.csv
```

Safeguards include exact/bridge DART-KIND receipt matching, numeric conflict penalties, repeated-disclosure ambiguity guards, and same-source different-receipt separation. Raw `articles` are never deleted or collapsed.

## EventExtractor V1.1

```bat
MaterialAnalyzer\news\run_event_extractor.bat
```

Output:

```text
MaterialAnalyzer\data\event_report.csv
```

Storage:

```text
material_events
```

Event type classification is layered:

```text
TITLE
  ↓ if UNKNOWN
SUMMARY
  ↓ if UNKNOWN
BODY high-precision rules only
```

Stage rules include `REQUESTED`, `PLANNED`, `CONFIRMED`, `APPROVED`, `STARTED`, `COMPLETED`, and `RELEASED`.

`quantified=1` requires a business-meaningful numeric fact such as money, percent, capacity, quantity, duration, or clinical phase. Calendar years, phone numbers, and article ids alone do not qualify.

Routine/administrative events are retained but excluded from downstream material scoring with `material_candidate=0`.

## NoveltyAnalyzer V1.1

```bat
MaterialAnalyzer\news\run_novelty_analyzer.bat
```

Manual rebuild:

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

Novelty statuses:
- `NEW_EVENT`
- `FOLLOW_UP`
- `CONFIRMATION`
- `REHASH`
- `MARKET_REACTION`

Family matching is deterministic and uses ticker/company identity, compatible event type, normalized title/token overlap, event-specific anchors, meaningful numeric facts, and time distance. Auto-family threshold is `68`.

### V1.1 litigation guard

Generic legal words alone are not sufficient to join lawsuits. Concrete legal subjects are extracted first.

Examples:

```text
전환사채발행금지 가처분
vs
신주발행금지 가처분
→ different family / NEW_EVENT
```

```text
전환사채발행금지 가처분 신청
→ 전환사채발행금지 가처분 항고
→ same family / FOLLOW_UP
```

Tracked litigation deltas:
- `litigation_procedure_changed`
- `litigation_procedure_progressed`

Other deltas include stage, meaningful number, company/counterparty, polarity, source reliability, and confirmation-source changes.

V1.1 is version-aware. Existing V1 novelty rows are reprocessed once after upgrade. A second unchanged run should return `processed=0`.

## MaterialScorer V1

```bat
MaterialAnalyzer\news\run_material_scorer.bat
```

Manual rebuild:

```bat
MaterialAnalyzer\news\run_material_scorer.bat --rebuild
```

Output:

```text
MaterialAnalyzer\data\material_score_report.csv
```

Storage:

```text
material_scores
```

MaterialScorer only scores `material_candidate=1` events that already have NoveltyAnalyzer results. `MARKET_REACTION` is excluded from material scoring.

### 100-point score

| Component | Max |
|---|---:|
| Direct Company / Specificity | 25 |
| Event Certainty | 20 |
| Financial Impact | 15 |
| Quantification | 15 |
| Novelty | 10 |
| Source Reliability | 10 |
| Multi-source Confirmation | 5 |
| **Total** | **100** |

Directness rules preserve policy events: a listed ticker receives the highest direct score, a named company receives a high score, and a concrete official government/sector event can still receive specificity credit even without a direct company.

Novelty component:

```text
NEW_EVENT        10
FOLLOW_UP         8
CONFIRMATION      5
REHASH             1
MARKET_REACTION    0
```

Final material status:

```text
85-100  STRONG
70-84   CONFIRMED
55-69   WATCH
0-54    REJECT
```

Material scoring is incremental and version-aware. If either the source event or novelty result changes, the corresponding event is rescored. A second unchanged run should return `processed=0`.

## Next stage

The next downstream layer is `TickerLinker`, which will connect company-less policy/sector events and company events to tradable tickers using explicit relation types such as `DIRECT`, `SUPPLIER`, `CUSTOMER`, `SECTOR`, and `THEME`. After that, `MaterialBacktester` can evaluate forward returns by material score/status and event type.
