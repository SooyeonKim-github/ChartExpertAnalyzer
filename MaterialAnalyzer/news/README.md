# MaterialAnalyzer News Pipeline

`MaterialAnalyzer.news` is the deterministic source-agnostic material pipeline used by MaterialAnalyzer.

## Current pipeline

```text
NewsCollector V1.5
        ↓
ArticleNormalizer / Exact dedupe
        ↓
ArticleCluster V1.1
        ↓
EventExtractor V1.1
        ↓
NoveltyAnalyzer V1.1
        ↓
MaterialScorer V1.1
        ↓
TickerLinker V1
        ↓
MaterialBacktester  ← next
```

Semantic similarity, embeddings, fuzzy company matching, and LLM inference are intentionally disabled in the current deterministic stages unless explicitly added later.

## Main execution order

```bat
MaterialAnalyzer\news\run_news_collector.bat
MaterialAnalyzer\news\run_article_cluster.bat
MaterialAnalyzer\news\run_event_extractor.bat
MaterialAnalyzer\news\run_novelty_analyzer.bat
MaterialAnalyzer\news\run_material_scorer.bat
MaterialAnalyzer\news\run_ticker_linker.bat
```

Each stage is incremental unless `--rebuild` is explicitly used.

## EventExtractor V1.1

```bat
MaterialAnalyzer\news\run_event_extractor.bat
```

Output:

```text
MaterialAnalyzer\data\event_report.csv
```

Event type classification is `TITLE -> SUMMARY -> BODY high-precision fallback`. `quantified=1` requires a meaningful business number rather than phone/date/article-id noise. Routine administrative events remain stored but can be excluded with `material_candidate=0`.

## NoveltyAnalyzer V1.1

```bat
MaterialAnalyzer\news\run_novelty_analyzer.bat
```

Output:

```text
MaterialAnalyzer\data\novelty_report.csv
```

Statuses:
- `NEW_EVENT`
- `FOLLOW_UP`
- `CONFIRMATION`
- `REHASH`
- `MARKET_REACTION`

V1.1 includes a litigation guard. Different legal subjects such as `전환사채발행금지` and `신주발행금지` do not become one family merely because both are injunction cases. The same subject progressing from filing to appeal can become `FOLLOW_UP`.

## MaterialScorer V1.1

```bat
MaterialAnalyzer\news\run_material_scorer.bat
```

Output:

```text
MaterialAnalyzer\data\material_score_report.csv
```

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

Status:

```text
85-100  STRONG
70-84   CONFIRMED
55-69   WATCH
0-54    REJECT
```

### V1.1 routine-governance guard

Direct DART/KIND disclosure and certainty should not make ordinary governance housekeeping look like a strong catalyst. Titles such as these receive a capped financial-impact component:

```text
주주명부 기준일/폐쇄
일반 임시·정기 주주총회 소집
일반 임시·정기 주주총회 결과
```

The event is still retained; only its standalone financial-impact score is reduced. Representative/director changes or genuinely material corporate actions are not automatically treated as routine.

V1.1 uses scoring version `RULE_MATERIAL_SCORE_V1_1`, so existing V1 scores are automatically recalculated once.

## TickerLinker V1

```bat
MaterialAnalyzer\news\run_ticker_linker.bat
```

Manual rebuild:

```bat
MaterialAnalyzer\news\run_ticker_linker.bat --rebuild
```

Outputs:

```text
MaterialAnalyzer\data\ticker_link_report.csv
MaterialAnalyzer\data\ticker_link_unresolved.csv
```

Storage:

```text
material_ticker_links
ticker_link_states
```

### Relation types

```text
DIRECT    1.00
SUPPLIER  0.80
CUSTOMER  0.70
SECTOR    0.50
THEME     0.35
```

`material_score` is preserved as event importance. Ticker relevance is stored separately:

```text
ticker_material_score = material_score × relation_weight
```

`positive_negative` is also preserved, so a high score can represent either an important positive catalyst or an important negative catalyst.

### Linking order and safeguards

1. EventExtractor stock code -> `DIRECT`, confidence 100.
2. Exact normalized company/alias match -> `DIRECT`, confidence 98.
3. Evidence-backed `company_relationships.csv` -> `SUPPLIER` / `CUSTOMER` only when evidence is present.
4. If there is no direct listed-company link, deterministic theme rules can create `SECTOR` / `THEME` links.
5. `REJECT` events do not fan out into theme stocks.
6. A company-specific direct catalyst does not fan out to broad theme peers.
7. No fuzzy company matching in V1; ambiguous/unmatched names remain unresolved.
8. Indirect expansion is capped to prevent the linker from becoming a generic related-stock generator.

### Editable reference data

```text
MaterialAnalyzer\data\reference\ticker_master.csv
MaterialAnalyzer\data\reference\event_theme_rules.csv
MaterialAnalyzer\data\reference\theme_ticker_map.csv
MaterialAnalyzer\data\reference\company_relationships.csv
```

`ticker_master.csv` is also bootstrapped at runtime from historical EventExtractor rows that already contain exactly one company and one stock code. This lets proven direct mappings accumulate without fuzzy matching.

`company_relationships.csv` intentionally starts empty. Add `SUPPLIER` / `CUSTOMER` rows only when a concrete source/evidence is available.

### Incremental behavior

`ticker_link_states` records the event version, MaterialScorer timestamp, link version, and linked count. If neither the event nor material score changes, a repeat run should return:

```text
processed = 0
```

Unresolved events are still recorded in state and exported separately, so they do not get pointlessly reprocessed on every run.

## Next stage

The next development step is `MaterialBacktester`.

Recommended backtest unit:

```text
event_id + ticker + relation_type + ticker_material_score + positive_negative
```

For each link, calculate forward returns such as D+1 / D+5 / D+10 / D+20 / D+40 / D+60, then compare performance by:
- material status/score band
- positive vs negative
- event type
- novelty status
- relation type (`DIRECT` vs `SECTOR` vs `THEME`)
- ticker-material-score band

The key purpose is to calibrate whether the current 100-point material score and relation weights actually separate high-value catalysts from noise before wiring the output into the final `collected_materials.csv`.
