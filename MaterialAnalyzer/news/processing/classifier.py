from __future__ import annotations

import re

from ..models import RawArticle


MARKET_REACTION_PREFIXES = ("[특징주]", "[급등주]", "[상한가]", "[오늘의 종목]", "[오늘의종목]")


class RuleArticleClassifier:
    def classify(self, article: RawArticle) -> str:
        title = re.sub(r"\s+", " ", article.title).strip()
        if article.source_type == "OFFICIAL" and article.category == "DISCLOSURE":
            return "DISCLOSURE"
        if article.source_type == "GOV":
            return "PRESS_RELEASE"
        if any(title.startswith(prefix) for prefix in MARKET_REACTION_PREFIXES):
            return "MARKET_REACTION"
        return article.article_class or "UNKNOWN"
