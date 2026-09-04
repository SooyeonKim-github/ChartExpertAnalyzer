from __future__ import annotations

import hashlib
from .models import ArticleFeatures


def build_event_key(features: ArticleFeatures) -> str:
    raw = "|".join([
        features.market_date or "",
        features.event_type,
        ",".join(features.companies),
        ",".join(features.stock_codes),
        ",".join(features.numbers[:4]),
        ",".join(features.tokens[:8]),
    ])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"{features.event_type}:{digest}"
