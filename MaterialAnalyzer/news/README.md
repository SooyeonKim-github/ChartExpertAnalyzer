# MaterialAnalyzer News Pipeline

`MaterialAnalyzer.news` is the source-agnostic collection, clustering, and event-structuring layer used by MaterialAnalyzer.

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
EventExtractor V1 (rule-based)
        ↓
material_events
        ↓
event_report.csv
```

Semantic similarity, embeddings, and LLM clustering are intentionally **disabled** in ArticleCluster.

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

## EventExtractor V1

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

Main fields:
- `event_type`
- `event_stage`
- `event_title`
- `event_summary`
- `positive_negative`
- `quantified`
- companies / stock codes / numeric facts
- original source
- article/source/confirmation counts
- first/last seen time
- market date
- extraction confidence

Event extraction is incremental. If a cluster changes because a new confirmation article is added, only that changed cluster is re-extracted.
