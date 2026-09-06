from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import CompanyRelationship, ThemeTickerRef, TickerRef


CORP_SUFFIX_RE = re.compile(r"(?:주식회사|\(주\)|㈜)")
NON_ALNUM_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")


def normalize_company(value: str | None) -> str:
    text = CORP_SUFFIX_RE.sub("", value or "").casefold()
    return NON_ALNUM_RE.sub("", text)


def _enabled(row) -> bool:
    return str(row.get("enabled", "1")).strip().casefold() not in {"0", "false", "n", "no"}


class ReferenceData:
    def __init__(self, reference_dir: Path, bootstrap_pairs=()):
        self.reference_dir = Path(reference_dir)
        self.tickers = self._load_ticker_master(self.reference_dir / "ticker_master.csv", bootstrap_pairs)
        self.theme_rules = self._load_theme_rules(self.reference_dir / "event_theme_rules.csv")
        self.theme_tickers = self._load_theme_tickers(self.reference_dir / "theme_ticker_map.csv")
        self.relationships = self._load_relationships(self.reference_dir / "company_relationships.csv")
        self.by_ticker = {row.ticker: row for row in self.tickers}
        self.by_company = self._company_index(self.tickers)

    @staticmethod
    def _company_index(rows: list[TickerRef]):
        out: dict[str, TickerRef] = {}
        ambiguous: set[str] = set()
        for row in rows:
            for value in (row.name, *row.aliases):
                key = normalize_company(value)
                if not key:
                    continue
                if key in out and out[key].ticker != row.ticker:
                    ambiguous.add(key)
                else:
                    out[key] = row
        for key in ambiguous:
            out.pop(key, None)
        return out

    @staticmethod
    def _load_ticker_master(path: Path, bootstrap_pairs) -> list[TickerRef]:
        by_ticker: dict[str, TickerRef] = {}
        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as fp:
                for row in csv.DictReader(fp):
                    if not _enabled(row):
                        continue
                    ticker = str(row.get("ticker", "")).strip().zfill(6)
                    name = str(row.get("name", "")).strip()
                    if not ticker or not name:
                        continue
                    aliases = tuple(x.strip() for x in str(row.get("aliases", "")).split("|") if x.strip())
                    by_ticker[ticker] = TickerRef(
                        ticker=ticker,
                        name=name,
                        aliases=aliases,
                        market=str(row.get("market", "")).strip(),
                        sector=str(row.get("sector", "")).strip(),
                        industry=str(row.get("industry", "")).strip(),
                    )

        # Direct company+ticker pairs already proven by EventExtractor bootstrap future exact resolution.
        for ticker, company in bootstrap_pairs:
            ticker = str(ticker).strip().zfill(6)
            company = str(company).strip()
            if ticker and company and ticker not in by_ticker:
                by_ticker[ticker] = TickerRef(ticker=ticker, name=company)
            elif ticker and company and ticker in by_ticker:
                current = by_ticker[ticker]
                aliases = tuple(dict.fromkeys((*current.aliases, company)))
                by_ticker[ticker] = TickerRef(
                    ticker=current.ticker,
                    name=current.name,
                    aliases=aliases,
                    market=current.market,
                    sector=current.sector,
                    industry=current.industry,
                )
        return list(by_ticker.values())

    @staticmethod
    def _load_theme_rules(path: Path):
        rows = []
        if not path.exists():
            return rows
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            for row in csv.DictReader(fp):
                if not _enabled(row):
                    continue
                theme = str(row.get("theme", "")).strip()
                keywords = tuple(x.strip() for x in str(row.get("keywords", "")).split("|") if x.strip())
                event_types = tuple(x.strip().upper() for x in str(row.get("event_types", "")).split("|") if x.strip())
                try:
                    confidence = float(row.get("confidence", 0.8))
                except (TypeError, ValueError):
                    confidence = 0.8
                if theme and keywords:
                    rows.append((theme, event_types, keywords, max(0.0, min(1.0, confidence))))
        return rows

    @staticmethod
    def _load_theme_tickers(path: Path) -> list[ThemeTickerRef]:
        rows = []
        if not path.exists():
            return rows
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            for row in csv.DictReader(fp):
                if not _enabled(row):
                    continue
                try:
                    weight = float(row.get("relation_weight", 0.35))
                    confidence = float(row.get("confidence", 0.7))
                except (TypeError, ValueError):
                    continue
                theme = str(row.get("theme", "")).strip()
                ticker = str(row.get("ticker", "")).strip().zfill(6)
                name = str(row.get("name", "")).strip()
                relation_type = str(row.get("relation_type", "THEME")).strip().upper()
                if theme and ticker and name and relation_type in {"SECTOR", "THEME"}:
                    rows.append(ThemeTickerRef(
                        theme=theme,
                        ticker=ticker,
                        name=name,
                        relation_type=relation_type,
                        relation_weight=max(0.0, min(1.0, weight)),
                        confidence=max(0.0, min(1.0, confidence)),
                        reason=str(row.get("reason", "")).strip(),
                    ))
        return rows

    @staticmethod
    def _load_relationships(path: Path) -> list[CompanyRelationship]:
        rows = []
        if not path.exists():
            return rows
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            for row in csv.DictReader(fp):
                if not _enabled(row):
                    continue
                relation_type = str(row.get("relation_type", "")).strip().upper()
                if relation_type not in {"SUPPLIER", "CUSTOMER"}:
                    continue
                evidence = str(row.get("evidence", "")).strip()
                if not evidence:
                    continue
                try:
                    weight = float(row.get("relation_weight", 0.8 if relation_type == "SUPPLIER" else 0.7))
                    confidence = float(row.get("confidence", 0.8))
                except (TypeError, ValueError):
                    continue
                rows.append(CompanyRelationship(
                    subject_name=str(row.get("subject_name", "")).strip(),
                    subject_ticker=str(row.get("subject_ticker", "")).strip().zfill(6) if str(row.get("subject_ticker", "")).strip() else "",
                    related_ticker=str(row.get("related_ticker", "")).strip().zfill(6),
                    related_name=str(row.get("related_name", "")).strip(),
                    relation_type=relation_type,
                    relation_weight=max(0.0, min(1.0, weight)),
                    confidence=max(0.0, min(1.0, confidence)),
                    evidence=evidence,
                ))
        return rows
