from __future__ import annotations

import tempfile
from pathlib import Path

from .collectors import CollectorFactory
from .config_loader import load_endpoints, load_sources
from .storage import ArticleRepository, Database


def main():
    sources = load_sources()
    endpoints = load_endpoints(only_enabled=False)
    assert len(sources) == 36, f"expected 36 sources, got {len(sources)}"
    assert len(endpoints) == 36, f"expected 36 endpoints, got {len(endpoints)}"
    assert "DART_API" in CollectorFactory.REGISTRY
    assert "NEWS_SECTION" in CollectorFactory.REGISTRY
    with tempfile.TemporaryDirectory() as td:
        repo = ArticleRepository(Database(Path(td) / "news.db"))
        assert repo.exists_article_id("missing") is False
    print("[OK] NewsCollector smoke test")
    print(f"     sources={len(sources)} endpoints={len(endpoints)}")


if __name__ == "__main__":
    main()
