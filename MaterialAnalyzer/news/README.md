# MaterialAnalyzer NewsCollector / ArticleCluster

`MaterialAnalyzer.news` is the source-agnostic collection and clustering layer used by MaterialAnalyzer.

## Current pipeline

```text
7 live official sources
        ↓
NewsCollector V1.5
        ↓
ArticleNormalizer
        ↓
Exact duplicate check
        ↓
Incremental Collection
        ↓
Source Health / Run History
        ↓
ArticleCluster V1 (rule-only)
        ↓
cluster_report.csv
```

Semantic similarity, embeddings, and LLM clustering are intentionally **disabled** in ArticleCluster V1.

## Live official sources

- DART
- KIND
- 산업통상부
- 과학기술정보통신부
- 기후에너지환경부
- 식품의약품안전처
- 금융위원회

## NewsCollector

```bat
MaterialAnalyzer\news\run_news_collector.bat
```

OpenDART requires `OPENDART_API_KEY`.

Repeated collection is incremental:
- DART/KIND: known items are skipped before fetch.
- Government sources: latest 3 items are re-fetched to capture edits.
- `source_states` and `collection_runs` persist endpoint health/history.

Health can be inspected with:

```bat
python -m MaterialAnalyzer.news.show_health --runs 20
```

## ArticleCluster V1

Run:

```bat
MaterialAnalyzer\news\run_article_cluster.bat
```

or:

```bat
python -m MaterialAnalyzer.news.run_article_cluster
```

Default mode is incremental: only articles that do not yet belong to a cluster are processed.

To rebuild all clusters from the raw `articles` table:

```bat
python -m MaterialAnalyzer.news.run_article_cluster --rebuild
```

Output:

```text
MaterialAnalyzer\data\cluster_report.csv
```

### Rule-only matching

ArticleCluster V1 uses:
- DART/KIND shared receipt number
- company metadata
- stock code metadata
- event keyword class
- normalized-title lexical similarity
- title token overlap
- numeric/amount/quantity agreement
- market-date proximity

Numeric conflicts are penalized heavily. Different receipt numbers from the same disclosure source are not merged only because they share a generic filing title.

### Cluster storage

- `article_clusters`
- `article_cluster_members`

Raw articles are never deleted or collapsed. A cluster is a separate event-level grouping layer.

`confirmation_count` counts distinct non-`MARKET_REACTION` sources beyond the first source, so later market-reaction articles do not inflate source confirmation.
