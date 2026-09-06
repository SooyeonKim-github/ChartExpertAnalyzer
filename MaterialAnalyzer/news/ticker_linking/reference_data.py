from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from .models import CompanyRelationship, ThemeRule, ThemeTickerRef, TickerRef


CORP_SUFFIX_RE = re.compile(r"(?:주식회사|\(주\)|㈜)")
NON_ALNUM_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")


def normalize_company(value: str | None) -> str:
    text = CORP_SUFFIX_RE.sub("", value or "").casefold()
    return NON_ALNUM_RE.sub("", text)


def _enabled(row) -> bool:
    return str(row.get("enabled", "1")).strip().casefold() not in {"0", "false", "n", "no"}


def _split(value) -> tuple[str, ...]:
    return tuple(x.strip() for x in str(value or "").split("|") if x.strip())


class ReferenceData:
    FILES = ("ticker_master.csv", "event_theme_rules.csv", "theme_ticker_map.csv", "company_relationships.csv")

    def __init__(self, reference_dir: Path, bootstrap_pairs=()):
        self.reference_dir = Path(reference_dir)
        self.bootstrap_pairs = tuple(sorted((str(t).zfill(6), str(c).strip()) for t, c in bootstrap_pairs if t and c))
        self.signature = self._signature()
        self.tickers = self._load_ticker_master(self.reference_dir / "ticker_master.csv", self.bootstrap_pairs)
        self.theme_rules = self._load_theme_rules(self.reference_dir / "event_theme_rules.csv")
        self.theme_tickers = self._load_theme_tickers(self.reference_dir / "theme_ticker_map.csv")
        self.relationships = self._load_relationships(self.reference_dir / "company_relationships.csv")
        self.by_ticker = {row.ticker: row for row in self.tickers}
        self.by_company, self.ambiguous_companies = self._company_index(self.tickers)

    def _signature(self) -> str:
        digest = hashlib.sha256()
        for name in self.FILES:
            path = self.reference_dir / name
            digest.update(name.encode("utf-8"))
            if path.exists():
                digest.update(path.read_bytes())
        for ticker, company in self.bootstrap_pairs:
            digest.update(f"{ticker}|{normalize_company(company)}\n".encode("utf-8"))
        return digest.hexdigest()[:20]

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
        return out, ambiguous

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
                    by_ticker[ticker] = TickerRef(
                        ticker=ticker,
                        name=name,
                        aliases=_split(row.get("aliases", "")),
                        market=str(row.get("market", "")).strip(),
                        sector=str(row.get("sector", "")).strip(),
                        industry=str(row.get("industry", "")).strip(),
                    )
        for ticker, company in bootstrap_pairs:
            current = by_ticker.get(ticker)
            if current is None:
                by_ticker[ticker] = TickerRef(ticker=ticker, name=company)
            else:
                aliases = tuple(dict.fromkeys((*current.aliases, company)))
                by_ticker[ticker] = TickerRef(current.ticker, current.name, aliases, current.market, current.sector, current.industry)
        return list(by_ticker.values())

    @staticmethod
    def _load_theme_rules(path: Path) -> list[ThemeRule]:
        rows: list[ThemeRule] = []
        if not path.exists():
            return rows
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            for row in csv.DictReader(fp):
                if not _enabled(row):
                    continue
                try:
                    confidence = float(row.get("confidence", 0.8))
                    threshold = float(row.get("min_materiality", 70))
                except (TypeError, ValueError):
                    continue
                theme = str(row.get("theme", "")).strip()
                keywords = _split(row.get("keywords", ""))
                if theme and keywords:
                    rows.append(ThemeRule(
                        theme=theme,
                        event_types=tuple(x.upper() for x in _split(row.get("event_types", ""))),
                        keywords=keywords,
                        strong_keywords=_split(row.get("strong_keywords", "")),
                        weak_keywords=_split(row.get("weak_keywords", "")),
                        confidence=max(0.0, min(1.0, confidence)),
                        min_materiality=max(0.0, min(100.0, threshold)),
                    ))
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
                    relevance = float(row.get("mapping_relevance", row.get("relevance", confidence)))
                except (TypeError, ValueError):
                    continue
                theme = str(row.get("theme", "")).strip()
                ticker = str(row.get("ticker", "")).strip().zfill(6)
                name = str(row.get("name", "")).strip()
                relation_type = str(row.get("relation_type", "THEME")).strip().upper()
                if theme and ticker and name and relation_type in {"SECTOR", "THEME"}:
                    rows.append(ThemeTickerRef(theme, ticker, name, relation_type,
                        max(0.0, min(1.0, weight)), max(0.0, min(1.0, confidence)),
                        max(0.0, min(1.0, relevance)), str(row.get("reason", "")).strip()))
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
                evidence = str(row.get("evidence", "")).strip()
                if relation_type not in {"SUPPLIER", "CUSTOMER"} or not evidence:
                    continue
                try:
                    weight = float(row.get("relation_weight", 0.8 if relation_type == "SUPPLIER" else 0.7))
                    confidence = float(row.get("confidence", 0.8))
                except (TypeError, ValueError):
                    continue
                rows.append(CompanyRelationship(
                    str(row.get("subject_name", "")).strip(),
                    str(row.get("subject_ticker", "")).strip().zfill(6) if str(row.get("subject_ticker", "")).strip() else "",
                    str(row.get("related_ticker", "")).strip().zfill(6),
                    str(row.get("related_name", "")).strip(), relation_type,
                    max(0.0, min(1.0, weight)), max(0.0, min(1.0, confidence)), evidence))
        return rows
