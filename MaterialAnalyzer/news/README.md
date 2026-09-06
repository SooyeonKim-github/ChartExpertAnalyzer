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
TickerLinker V1.1
        ↓
MaterialBacktester  ← next
```

Semantic similarity, embeddings, fuzzy company matching, and LLM inference are intentionally disabled in the current deterministic stages.

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

## MaterialScorer V1.1

```bat
MaterialAnalyzer\news\run_material_scorer.bat
```

Output: `MaterialAnalyzer\data\material_score_report.csv`

100-point components are Direct Company / Specificity 25, Event Certainty 20, Financial Impact 15, Quantification 15, Novelty 10, Source Reliability 10, and Multi-source Confirmation 5.

Status:

```text
85-100  STRONG
70-84   CONFIRMED
55-69   WATCH
0-54    REJECT
```

V1.1 caps the financial-impact component for routine governance housekeeping such as ordinary shareholder-record dates and ordinary shareholder-meeting notices/results.

## TickerLinker V1.1

```bat
MaterialAnalyzer\news\run_ticker_linker.bat
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

### KRX ticker master

Before linking, `run_ticker_linker.bat` performs a best-effort refresh of `ticker_master.csv` when it is older than 7 days. The builder uses `pykrx` and KOSPI + KOSDAQ. If KRX or pykrx is unavailable, the existing master is kept and linking continues.

Manual refresh:

```bat
MaterialAnalyzer\news\run_build_ticker_master.bat
```

The builder preserves existing aliases/sector/industry fields when it refreshes canonical KRX names and markets.

### Relation types

```text
DIRECT    base 1.00
SUPPLIER  base 0.80
CUSTOMER  base 0.70
SECTOR    base 0.50
THEME     base 0.35
```

For `SECTOR` / `THEME`, V1.1 applies stock-specific mapping relevance:

```text
effective_relation_weight = base relation weight × mapping_relevance
ticker_material_score     = material_score × effective_relation_weight
```

`material_score` itself is never overwritten; it remains the importance of the event.

### Linking order and safeguards

1. EventExtractor stock code -> `DIRECT`, confidence 100.
2. Exact normalized company/alias match -> `DIRECT`, confidence 98.
3. Evidence-backed `company_relationships.csv` -> `SUPPLIER` / `CUSTOMER` only when evidence is present.
4. A company-specific event never falls back to broad theme peers. If the company cannot be resolved, it remains `COMPANY_NOT_IN_MASTER` or `AMBIGUOUS_COMPANY`.
5. Company-less policy/sector events can enter theme analysis.
6. Theme recognition and ticker fan-out are separate decisions. `ThemeMaterialityGuard` must pass before stocks are emitted.
7. `REJECT` events do not fan out into theme stocks.
8. Indirect links are capped: total 8, SECTOR 5, THEME 3.
9. Fuzzy company matching, embeddings, and LLM linking are disabled.

### Theme Materiality Guard

`event_theme_rules.csv` contains theme keywords plus `strong_keywords`, `weak_keywords`, and `min_materiality`.

The materiality score starts from a theme match and adds evidence for material event types, strong business triggers, meaningful quantities/money/capacity, and progressed stages. It subtracts for weak informational triggers such as meetings, forums, education, contests, ceremonies, or seminars.

Typical behavior:

```text
AI 데이터센터 5조원 대규모 투자
→ AI theme recognized
→ materiality >= threshold
→ ticker fan-out allowed

AI 경진대회 참가자 모집
→ AI theme recognized
→ weak trigger penalty
→ THEME_NOT_MATERIAL
→ no ticker emitted

IAEA 출범식 참석
→ nuclear theme may be recognized
→ weak event
→ no nuclear-stock fan-out

해상풍력 25GW 보급 계획
→ offshore-wind theme + strong trigger + capacity
→ SECTOR links allowed
```

### Editable reference data

```text
MaterialAnalyzer\data\reference\ticker_master.csv
MaterialAnalyzer\data\reference\event_theme_rules.csv
MaterialAnalyzer\data\reference\theme_ticker_map.csv
MaterialAnalyzer\data\reference\company_relationships.csv
```

`ticker_master.csv` is additionally bootstrapped at runtime from historical EventExtractor rows that already contain exactly one company and one stock code. `company_relationships.csv` intentionally starts empty; add SUPPLIER/CUSTOMER only with concrete evidence.

### Reference-aware incremental behavior

V1.1 computes a SHA-256-based `reference_signature` from the four reference files plus proven bootstrap company/ticker pairs. `ticker_link_states` stores that signature.

Therefore any edit to ticker master, theme rules, theme mappings, or company relationships automatically makes prior events pending for relinking. No manual `--rebuild` is required. With no event/score/reference changes, a repeat run returns `processed=0`.

### Unresolved reasons

V1.1 exports specific reasons including:

```text
COMPANY_NOT_IN_MASTER
AMBIGUOUS_COMPANY
NO_COMPANY_OR_THEME
NO_THEME_MATCH
THEME_NOT_MATERIAL
NO_THEME_TICKER_MAP
REJECT_NOT_EXPANDED
NO_ELIGIBLE_LINK
```

This makes the unresolved report directly actionable instead of treating every failure identically.

## Next stage: MaterialBacktester

After reviewing the V1.1 link report, the next development step is `MaterialBacktester`.

Recommended backtest unit:

```text
event_id + ticker + relation_type + effective relation weight
+ material_score + ticker_material_score + positive_negative
```

Calculate D+1 / D+5 / D+10 / D+20 / D+40 / D+60 forward returns and compare performance by material score/status, positive vs negative, event type, novelty status, relation type, theme-materiality score, and ticker-material-score band. The goal is to replace hand-picked thresholds and relation weights with evidence from actual forward returns.
