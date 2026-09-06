from __future__ import annotations

from collections import defaultdict

from .company_resolver import CompanyResolver
from .models import LinkInput, TickerLinkRecord, TickerLinkRunResult
from .reference_data import ReferenceData, normalize_company
from .theme_extractor import ThemeExtractor


RELATION_WEIGHT = {
    "DIRECT": 1.00,
    "SUPPLIER": 0.80,
    "CUSTOMER": 0.70,
    "SECTOR": 0.50,
    "THEME": 0.35,
}
RELATION_PRIORITY = {"DIRECT": 5, "SUPPLIER": 4, "CUSTOMER": 3, "SECTOR": 2, "THEME": 1}


class TickerLinker:
    VERSION = "RULE_TICKER_LINK_V1"
    MAX_INDIRECT = 15
    MAX_RELATION_PER_TYPE = 5
    MAX_THEME_LINKS = 10

    def __init__(self, repository, reference_dir):
        self.repository = repository
        bootstrap_pairs = repository.get_direct_identity_pairs()
        self.reference = ReferenceData(reference_dir, bootstrap_pairs=bootstrap_pairs)
        self.company_resolver = CompanyResolver(self.reference)
        self.theme_extractor = ThemeExtractor(self.reference)
        self.theme_rows = defaultdict(list)
        for row in self.reference.theme_tickers:
            self.theme_rows[row.theme].append(row)
        for theme in self.theme_rows:
            self.theme_rows[theme].sort(key=lambda x: (-x.relation_weight, -x.confidence, x.ticker))

    @staticmethod
    def _record(event: LinkInput, *, ticker: str, name: str, relation_type: str,
                confidence: float, theme: str = "", reason: str = "", evidence: str = ""):
        weight = RELATION_WEIGHT[relation_type]
        return TickerLinkRecord(
            event_id=event.event_id,
            ticker=str(ticker).zfill(6),
            name=name,
            relation_type=relation_type,
            relation_weight=weight,
            link_confidence=round(max(0.0, min(100.0, confidence)), 2),
            theme=theme,
            link_reason=reason,
            evidence=evidence,
            material_score=event.material_score,
            material_status=event.material_status,
            ticker_material_score=round(event.material_score * weight, 2),
            positive_negative=event.positive_negative,
            link_version=TickerLinker.VERSION,
            event_updated_at=event.event_updated_at,
            score_updated_at=event.score_updated_at,
        )

    def _direct_links(self, event: LinkInput):
        links = []
        companies = list(event.companies)
        stocks = [str(code).zfill(6) for code in event.stock_codes]

        for idx, ticker in enumerate(stocks):
            master = self.reference.by_ticker.get(ticker)
            name = master.name if master else ""
            if len(companies) == len(stocks) and idx < len(companies):
                name = companies[idx] or name
            elif len(companies) == 1:
                name = companies[0] or name
            links.append(self._record(
                event,
                ticker=ticker,
                name=name or ticker,
                relation_type="DIRECT",
                confidence=100,
                reason="stock code directly identified by EventExtractor",
                evidence=f"event stock_code={ticker}",
            ))

        existing = {link.ticker for link in links}
        for company in companies:
            resolved = self.company_resolver.resolve(company)
            if resolved and resolved.ticker not in existing:
                existing.add(resolved.ticker)
                links.append(self._record(
                    event,
                    ticker=resolved.ticker,
                    name=resolved.name,
                    relation_type="DIRECT",
                    confidence=98,
                    reason="exact company/alias match in ticker master",
                    evidence=f"company={company}",
                ))
        return links

    def _relationship_links(self, event: LinkInput, direct_links):
        if not event.companies and not direct_links:
            return []
        event_company_keys = {normalize_company(name) for name in event.companies if name}
        event_tickers = {link.ticker for link in direct_links}
        out = []
        counts = defaultdict(int)

        for rel in self.reference.relationships:
            subject_match = bool(
                (rel.subject_ticker and rel.subject_ticker in event_tickers)
                or (rel.subject_name and normalize_company(rel.subject_name) in event_company_keys)
            )
            if not subject_match or rel.related_ticker in event_tickers:
                continue
            if counts[rel.relation_type] >= self.MAX_RELATION_PER_TYPE:
                continue
            counts[rel.relation_type] += 1
            out.append(self._record(
                event,
                ticker=rel.related_ticker,
                name=rel.related_name or rel.related_ticker,
                relation_type=rel.relation_type,
                confidence=rel.confidence * 100,
                reason=f"evidence-backed {rel.relation_type.lower()} relationship",
                evidence=rel.evidence,
            ))
        return out

    def _theme_links(self, event: LinkInput, direct_links):
        # Do not turn a company-specific catalyst into a broad related-stock list.
        # Theme expansion is for policy/sector events without a direct listed-company link.
        if direct_links or event.material_status == "REJECT":
            return []

        matches = self.theme_extractor.extract(event.event_type, event.event_title, event.event_summary)
        candidates = []
        for match in matches:
            for mapped in self.theme_rows.get(match.theme, ()):
                confidence = min(match.confidence, mapped.confidence) * 100
                candidates.append((
                    mapped.relation_weight * confidence,
                    self._record(
                        event,
                        ticker=mapped.ticker,
                        name=mapped.name,
                        relation_type=mapped.relation_type,
                        confidence=confidence,
                        theme=match.theme,
                        reason=f"theme rule matched: {'|'.join(match.matched_keywords)}",
                        evidence=mapped.reason,
                    ),
                ))
        candidates.sort(key=lambda item: (-item[0], item[1].ticker))
        return [item[1] for item in candidates[:self.MAX_THEME_LINKS]]

    @staticmethod
    def _dedupe(links):
        best = {}
        for link in links:
            current = best.get(link.ticker)
            if current is None:
                best[link.ticker] = link
                continue
            left = (RELATION_PRIORITY[link.relation_type], link.link_confidence)
            right = (RELATION_PRIORITY[current.relation_type], current.link_confidence)
            if left > right:
                best[link.ticker] = link
        return list(best.values())

    def link_event(self, event: LinkInput):
        direct = self._direct_links(event)
        relationships = self._relationship_links(event, direct)
        themes = self._theme_links(event, direct)
        links = self._dedupe([*direct, *relationships, *themes])

        direct_links = [x for x in links if x.relation_type == "DIRECT"]
        indirect_links = [x for x in links if x.relation_type != "DIRECT"]
        indirect_links.sort(key=lambda x: (-x.relation_weight, -x.link_confidence, x.ticker))
        return [*direct_links, *indirect_links[:self.MAX_INDIRECT]]

    def run(self, *, rebuild: bool = False, limit: int | None = None) -> TickerLinkRunResult:
        if rebuild:
            self.repository.clear_all()

        self.repository.prune_orphans()
        rows = self.repository.get_pending_events(link_version=self.VERSION, limit=limit)
        result = TickerLinkRunResult(processed=len(rows))

        for row in rows:
            event = LinkInput.from_row(row)
            links = self.link_event(event)
            if links:
                result.linked_events += 1
                unresolved_reason = ""
            else:
                result.unresolved_events += 1
                unresolved_reason = "no direct ticker/company exact match and no eligible theme/relationship mapping"
            self.repository.replace_event_links(event, links, self.VERSION, unresolved_reason)

        result.total_links = self.repository.link_count()
        result.total_events = self.repository.state_count()
        counts = self.repository.relation_counts()
        result.direct = counts.get("DIRECT", 0)
        result.supplier = counts.get("SUPPLIER", 0)
        result.customer = counts.get("CUSTOMER", 0)
        result.sector = counts.get("SECTOR", 0)
        result.theme = counts.get("THEME", 0)
        return result
