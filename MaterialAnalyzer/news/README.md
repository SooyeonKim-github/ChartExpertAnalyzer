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
HistoricalMaterialRangeCollector  ← next
        ↓
MaterialBacktester
```

Semantic similarity, embeddings, fuzzy company matching, and LLM inference are intentionally disabled in the deterministic linking stages.

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

Output: `MaterialAnalyzer\data\material_score_report.csv`

100-point components: Direct Company / Specificity 25, Event Certainty 20, Financial Impact 15, Quantification 15, Novelty 10, Source Reliability 10, Multi-source Confirmation 5.

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

### Robust ticker master

Before linking, the generated KOSPI/KOSDAQ master is refreshed best-effort when the last successful refresh is older than 7 days.

Provider order:

```text
1. MarketData.service shared pykrx transport
   - reuses the repository's KRX session/header fixes
2. FinanceDataReader StockListing("KRX")
3. direct pykrx
4. existing ticker_master_krx.csv if every live provider fails
5. tracked ticker_master.csv + proven EventExtractor bootstrap pairs always remain available
```

Reference split:

```text
ticker_master.csv       = tracked manual seed / aliases
ticker_master_krx.csv   = generated full KRX list, gitignored
```

Known listed companies that previously remained unresolved are also seeded manually so temporary KRX outages do not block exact DIRECT resolution.

`company_status_overrides.csv` explicitly marks known non-listed companies such as pre-IPO firms. Those return `NON_LISTED_COMPANY` rather than being mistaken for a missing ticker-master entry.

### Relation types

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

### Linking safeguards

1. EventExtractor stock code -> `DIRECT`.
2. Exact normalized company/alias -> `DIRECT`.
3. Evidence-backed relationships only -> `SUPPLIER` / `CUSTOMER`.
4. Company-specific events never fall back to broad theme peers.
5. Company-less policy/sector events may enter theme analysis.
6. `ThemeMaterialityGuard` must pass before ticker fan-out.
7. REJECT events do not fan out.
8. Indirect links are capped: total 8, SECTOR 5, THEME 3.
9. Fuzzy company matching, embeddings, and LLM linking remain disabled.

### Theme Materiality Guard

`event_theme_rules.csv` contains theme keywords, strong triggers, weak triggers, and per-theme threshold.

Noise such as meetings, forums, education, contests, ceremonies, and seminars is penalized. Strong business triggers include concrete investment, construction, capacity, supply, production, launch, cluster/industrial-belt activation, and other theme-specific real-economy signals.

Examples:

```text
AI 경진대회 참가자 모집
→ THEME_NOT_MATERIAL

IAEA 출범식 참석
→ no nuclear-stock fan-out

반도체·첨단소재 미국기업 20억달러 투자유치
→ strong semiconductor trigger + meaningful amount
→ semiconductor SECTOR links

배터리 삼각벨트 본격 가동
→ strong secondary-battery industrial trigger
→ secondary-battery SECTOR links

AI 데이터센터 대규모 투자
→ strong AI infrastructure trigger
→ eligible theme links
```

### Editable references

```text
MaterialAnalyzer\data\reference\ticker_master.csv
MaterialAnalyzer\data\reference\ticker_master_krx.csv
MaterialAnalyzer\data\reference\event_theme_rules.csv
MaterialAnalyzer\data\reference\theme_ticker_map.csv
MaterialAnalyzer\data\reference\company_relationships.csv
MaterialAnalyzer\data\reference\company_status_overrides.csv
```

Any reference edit or successful generated-master refresh changes the SHA-based `reference_signature` and automatically relinks prior events. No manual `--rebuild` is needed. An unchanged repeat should return `processed=0`.

### Unresolved reasons

```text
NON_LISTED_COMPANY
COMPANY_NOT_IN_MASTER
AMBIGUOUS_COMPANY
NO_COMPANY_OR_THEME
NO_THEME_MATCH
THEME_NOT_MATERIAL
NO_THEME_TICKER_MAP
REJECT_NOT_EXPANDED
NO_ELIGIBLE_LINK
```

## Next stage

After the V1.2 link output is validated, build `HistoricalMaterialRangeCollector` to accumulate enough historical events before implementing `MaterialBacktester`. The backtester should calculate D+1 / D+5 / D+10 / D+20 / D+40 / D+60 and compare performance by material score/status, polarity, event type, novelty, relation type, theme materiality, and ticker-material-score band. Those results can then calibrate the current thresholds and relation weights.
