from __future__ import annotations

from collections import defaultdict

from .company_resolver import CompanyResolver
from .models import LinkInput, TickerLinkRecord, TickerLinkRunResult
from .reference_data import ReferenceData, normalize_company
from .theme_extractor import ThemeExtractor
from .theme_materiality_guard import ThemeMaterialityGuard


RELATION_WEIGHT = {
    "DIRECT": 1.00,
    "SUPPLIER": 0.80,
    "CUSTOMER": 0.70,
    "SECTOR": 0.50,
    "THEME": 0.35,
}
RELATION_PRIORITY = {"DIRECT": 5, "SUPPLIER": 4, "CUSTOMER": 3, "SECTOR": 2, "THEME": 1}


class TickerLinker:
    VERSION = "RULE_TICKER_LINK_V1_2"
    MAX_INDIRECT = 8
    MAX_RELATION_PER_TYPE = 5
    MAX_SECTOR_LINKS = 5
    MAX_THEME_LINKS = 3

    def __init__(self, repository, reference_dir):
        self.repository = repository
        bootstrap_pairs = repository.get_direct_identity_pairs()
        self.reference = ReferenceData(reference_dir, bootstrap_pairs=bootstrap_pairs)
        self.reference_signature = self.reference.signature
        self.company_resolver = CompanyResolver(self.reference)
        self.theme_extractor = ThemeExtractor(self.reference)
        self.materiality_guard = ThemeMaterialityGuard()
        self.theme_rows = defaultdict(list)
        for row in self.reference.theme_tickers:
            self.theme_rows[row.theme].append(row)
        for theme in self.theme_rows:
            self.theme_rows[theme].sort(
                key=lambda x: (-(x.relation_weight * x.mapping_relevance), -x.confidence, x.ticker)
            )

    def _record(self, event: LinkInput, *, ticker: str, name: str, relation_type: str,
                confidence: float, theme: str = "", reason: str = "", evidence: str = "",
                relation_weight: float | None = None, mapping_relevance: float = 1.0,
                theme_materiality_score: float = 0.0):
        weight = RELATION_WEIGHT[relation_type] if relation_weight is None else relation_weight
        weight = max(0.0, min(1.0, float(weight)))
        relevance = max(0.0, min(1.0, float(mapping_relevance)))
        return TickerLinkRecord(
            event_id=event.event_id,
            ticker=str(ticker).zfill(6),
            name=name,
            relation_type=relation_type,
            relation_weight=round(weight, 4),
            mapping_relevance=round(relevance, 4),
            link_confidence=round(max(0.0, min(100.0, confidence)), 2),
            theme=theme,
            theme_materiality_score=round(theme_materiality_score, 2),
            link_reason=reason,
            evidence=evidence,
            material_score=event.material_score,
            material_status=event.material_status,
            ticker_material_score=round(event.material_score * weight, 2),
            positive_negative=event.positive_negative,
            link_version=self.VERSION,
            reference_signature=self.reference_signature,
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
                event, ticker=ticker, name=name or ticker, relation_type="DIRECT", confidence=100,
                reason="stock code directly identified by EventExtractor",
                evidence=f"event stock_code={ticker}", relation_weight=1.0,
            ))

        existing = {link.ticker for link in links}
        for company in companies:
            resolved = self.company_resolver.resolve(company)
            if resolved and resolved.ticker not in existing:
                existing.add(resolved.ticker)
                links.append(self._record(
                    event, ticker=resolved.ticker, name=resolved.name, relation_type="DIRECT", confidence=98,
                    reason="exact company/alias match in ticker master", evidence=f"company={company}",
                    relation_weight=1.0,
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
                event, ticker=rel.related_ticker, name=rel.related_name or rel.related_ticker,
                relation_type=rel.relation_type, confidence=rel.confidence * 100,
                reason=f"evidence-backed {rel.relation_type.lower()} relationship", evidence=rel.evidence,
                relation_weight=rel.relation_weight,
            ))
        return out

    def _theme_analysis(self, event: LinkInput):
        matches = self.theme_extractor.extract(event.event_type, event.event_title, event.event_summary)
        return [(match, self.materiality_guard.evaluate(event, match)) for match in matches]

    def _theme_links(self, event: LinkInput, direct_links, analysis):
        if direct_links or event.companies or event.material_status == "REJECT":
            return []

        candidates = []
        sector_count = 0
        theme_count = 0
        for match, materiality in analysis:
            if not materiality.eligible:
                continue
            for mapped in self.theme_rows.get(match.theme, ()):
                if mapped.relation_type == "SECTOR" and sector_count >= self.MAX_SECTOR_LINKS:
                    continue
                if mapped.relation_type == "THEME" and theme_count >= self.MAX_THEME_LINKS:
                    continue
                confidence = min(match.confidence, mapped.confidence) * 100
                effective_weight = mapped.relation_weight * mapped.mapping_relevance
                record = self._record(
                    event,
                    ticker=mapped.ticker,
                    name=mapped.name,
                    relation_type=mapped.relation_type,
                    relation_weight=effective_weight,
                    mapping_relevance=mapped.mapping_relevance,
                    confidence=confidence,
                    theme=match.theme,
                    theme_materiality_score=materiality.score,
                    reason=(f"material theme rule matched: {'|'.join(match.matched_keywords)}; "
                            f"{materiality.reason}"),
                    evidence=mapped.reason,
                )
                candidates.append((effective_weight * confidence, record))
                if mapped.relation_type == "SECTOR":
                    sector_count += 1
                else:
                    theme_count += 1
        candidates.sort(key=lambda item: (-item[0], item[1].ticker))
        return [item[1] for item in candidates[:self.MAX_INDIRECT]]

    @staticmethod
    def _dedupe(links):
        best = {}
        for link in links:
            current = best.get(link.ticker)
            if current is None:
                best[link.ticker] = link
                continue
            left = (RELATION_PRIORITY[link.relation_type], link.relation_weight, link.link_confidence)
            right = (RELATION_PRIORITY[current.relation_type], current.relation_weight, current.link_confidence)
            if left > right:
                best[link.ticker] = link
        return list(best.values())

    def _unresolved_reason(self, event: LinkInput, direct_links, analysis) -> str:
        if direct_links:
            return ""
        if event.companies:
            statuses = [self.company_resolver.status(company) for company in event.companies]
            if "NON_LISTED_COMPANY" in statuses:
                return "NON_LISTED_COMPANY"
            if "AMBIGUOUS_COMPANY" in statuses:
                return "AMBIGUOUS_COMPANY"
            if "COMPANY_NOT_IN_MASTER" in statuses:
                return "COMPANY_NOT_IN_MASTER"
        if event.material_status == "REJECT":
            return "REJECT_NOT_EXPANDED"
        if not analysis:
            return "NO_COMPANY_OR_THEME" if not event.companies else "NO_THEME_MATCH"
        eligible = [(match, mat) for match, mat in analysis if mat.eligible]
        if not eligible:
            return "THEME_NOT_MATERIAL"
        if not any(self.theme_rows.get(match.theme) for match, _ in eligible):
            return "NO_THEME_TICKER_MAP"
        return "NO_ELIGIBLE_LINK"

    def link_event(self, event: LinkInput):
        direct = self._direct_links(event)
        relationships = self._relationship_links(event, direct)
        analysis = self._theme_analysis(event)
        themes = self._theme_links(event, direct, analysis)
        links = self._dedupe([*direct, *relationships, *themes])
        direct_links = [x for x in links if x.relation_type == "DIRECT"]
        indirect_links = [x for x in links if x.relation_type != "DIRECT"]
        indirect_links.sort(key=lambda x: (-x.relation_weight, -x.link_confidence, x.ticker))
        final_links = [*direct_links, *indirect_links[:self.MAX_INDIRECT]]
        return final_links, self._unresolved_reason(event, direct, analysis)

    def run(self, *, rebuild: bool = False, limit: int | None = None) -> TickerLinkRunResult:
        if rebuild:
            self.repository.clear_all()
        self.repository.prune_orphans()
        rows = self.repository.get_pending_events(
            link_version=self.VERSION,
            reference_signature=self.reference_signature,
            limit=limit,
        )
        result = TickerLinkRunResult(processed=len(rows))
        for row in rows:
            event = LinkInput.from_row(row)
            links, unresolved_reason = self.link_event(event)
            if links:
                result.linked_events += 1
                unresolved_reason = ""
            else:
                result.unresolved_events += 1
            self.repository.replace_event_links(
                event, links, self.VERSION, self.reference_signature, unresolved_reason
            )
        result.total_links = self.repository.link_count()
        result.total_events = self.repository.state_count()
        counts = self.repository.relation_counts()
        result.direct = counts.get("DIRECT", 0)
        result.supplier = counts.get("SUPPLIER", 0)
        result.customer = counts.get("CUSTOMER", 0)
        result.sector = counts.get("SECTOR", 0)
        result.theme = counts.get("THEME", 0)
        return result
