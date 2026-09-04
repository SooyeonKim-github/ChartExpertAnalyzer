from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from .models import SourceEndpoint


CONFIG_DIR = Path(__file__).resolve().parent / "config"


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "y", "yes", "on"}


def load_sources(path: str | Path | None = None) -> Dict[str, dict]:
    source_path = Path(path) if path else CONFIG_DIR / "source_master.csv"
    with source_path.open("r", encoding="utf-8-sig", newline="") as f:
        return {row["source_id"]: row for row in csv.DictReader(f)}


def load_endpoints(path: str | Path | None = None, *, only_enabled: bool = True) -> List[SourceEndpoint]:
    endpoint_path = Path(path) if path else CONFIG_DIR / "source_endpoint_master.csv"
    sources = load_sources()
    endpoints = []
    with endpoint_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            enabled = _truthy(row.get("enabled", ""))
            if only_enabled and not enabled:
                continue
            source = sources.get(row["source_id"])
            if source is None:
                raise ValueError(f"source_id={row['source_id']} is not defined in source_master.csv")
            known = {"endpoint_id","source_id","endpoint_role","collector_type","target_section","interval_min","content_mode","enabled","list_url","detail_url_template","fallback_source_id","category","item_selector","title_selector","link_selector","date_selector","body_selector","author_selector","api_url","rss_url","headers_json"}
            endpoints.append(SourceEndpoint(endpoint_id=row["endpoint_id"], source_id=row["source_id"], source_name=source["source_name"], source_type=source["source_type"], source_grade=source["source_grade"], priority=int(source.get("priority") or 999), collector_type=row["collector_type"], endpoint_role=row.get("endpoint_role", ""), target_section=row.get("target_section", ""), interval_min=int(row.get("interval_min") or 10), content_mode=row.get("content_mode", "DISCOVERY"), enabled=enabled, list_url=row.get("list_url", ""), detail_url_template=row.get("detail_url_template", ""), fallback_source_id=row.get("fallback_source_id", ""), category=row.get("category", ""), item_selector=row.get("item_selector", ""), title_selector=row.get("title_selector", ""), link_selector=row.get("link_selector", ""), date_selector=row.get("date_selector", ""), body_selector=row.get("body_selector", ""), author_selector=row.get("author_selector", ""), api_url=row.get("api_url", ""), rss_url=row.get("rss_url", ""), headers_json=row.get("headers_json", ""), extra={k: v for k, v in row.items() if k not in known and v}))
    return sorted(endpoints, key=lambda x: (x.priority, x.endpoint_id))
