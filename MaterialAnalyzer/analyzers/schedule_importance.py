from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
import re
from typing import Iterable

from ..analysis_models import ScheduleImportanceResult, ThemeMatch
from ..schedule_models import ScheduleItem


_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_MONEY_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>조|억|만)\s*원")

_AUTHORITY_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (15, ("대통령", "정상회담", "국무회의", "총리")),
    (13, ("정부", "기획재정부", "산업통상자원부", "국토교통부", "과학기술정보통신부", "보건복지부", "금융위원회")),
    (11, ("산업부", "국토부", "과기정통부", "복지부", "환경부", "중기부", "고용부", "통계청", "금융위")),
    (8, ("공공기관", "공사", "공단", "연구원")),
    (5, ("협회", "학회", "위원회")),
)

_POLICY_STRONG = ("기본계획", "종합대책", "육성전략", "지원대책", "특별법", "법안", "시행령", "예산", "투자계획", "로드맵")
_POLICY_MEDIUM = ("정책", "대책", "지원", "규제완화", "규제 완화", "산업 육성", "전략", "계획", "협력")

_STOPWORDS = {
    "관련", "예정", "개최", "발표", "정부", "대한", "위한", "오는", "오늘", "내일", "회의", "간담회",
    "정책", "계획", "추진", "공개", "이번", "다음", "보도", "자료", "시장", "산업",
}


class ScheduleImportanceAnalyzer:
    """Score the importance of a dated market schedule using explainable V1 rules.

    V1 deliberately excludes historical price reaction. Novelty only measures whether
    similar material text has appeared in the accumulated raw-material history.
    """

    def __init__(self, material_history_file: Path | None = None) -> None:
        self.material_history_file = material_history_file
        self._history_rows = self._load_history(material_history_file)

    def analyze(
        self,
        schedule: ScheduleItem,
        scan_date: date,
        theme_matches: Iterable[ThemeMatch] = (),
    ) -> ScheduleImportanceResult:
        text = f"{schedule.title} {schedule.summary}".strip()
        themes = list(theme_matches)

        authority = float(self._authority_score(text))
        novelty, novelty_status, similar_count = self._novelty_score(text, scan_date)
        amount_krw = self._extract_largest_money(text)
        money = float(self._money_score(amount_krw))
        policy = float(self._policy_score(text, schedule.schedule_kind))
        theme_clarity = float(self._theme_clarity_score(themes))
        certainty = round(max(0.0, min(schedule.confidence, 1.0)) * 20.0, 2)

        total = round(authority + novelty + money + policy + theme_clarity + certainty, 2)
        priority = self._priority(total)
        reason = self._reason(
            authority=authority,
            novelty=novelty,
            money=money,
            policy=policy,
            theme_clarity=theme_clarity,
            certainty=certainty,
            similar_count=similar_count,
            novelty_status=novelty_status,
        )

        return ScheduleImportanceResult(
            schedule_score=total,
            priority=priority,
            authority_score=authority,
            novelty_score=novelty,
            money_score=money,
            policy_score=policy,
            theme_clarity_score=theme_clarity,
            event_certainty_score=certainty,
            novelty_status=novelty_status,
            similar_history_count=similar_count,
            money_amount_krw=amount_krw,
            reason=reason,
        )

    @staticmethod
    def _authority_score(text: str) -> int:
        for score, keywords in _AUTHORITY_RULES:
            if any(keyword in text for keyword in keywords):
                return score
        return 3

    def _novelty_score(self, text: str, scan_date: date) -> tuple[float, str, int]:
        if not self._history_rows:
            return 10.0, "INSUFFICIENT_HISTORY", 0

        current_tokens = self._tokens(text)
        if not current_tokens:
            return 10.0, "INSUFFICIENT_TEXT", 0

        similar = 0
        comparable = 0
        for row in self._history_rows:
            row_date = self._row_date(row)
            if row_date is not None and row_date >= scan_date:
                continue
            historical_text = f"{row.get('title', '')} {row.get('summary', '')}".strip()
            historical_tokens = self._tokens(historical_text)
            if not historical_tokens:
                continue
            comparable += 1
            intersection = len(current_tokens & historical_tokens)
            union = len(current_tokens | historical_tokens)
            similarity = intersection / union if union else 0.0
            if similarity >= 0.42 or (
                intersection >= 3 and intersection / max(len(current_tokens), 1) >= 0.6
            ):
                similar += 1

        if comparable < 20:
            return 10.0, "INSUFFICIENT_HISTORY", similar
        if similar == 0:
            return 20.0, "NEW_IN_HISTORY", 0
        if similar == 1:
            return 16.0, "LOW_REPEAT", 1
        if similar <= 3:
            return 11.0, "REPEATED", similar
        if similar <= 7:
            return 7.0, "FREQUENT_REPEAT", similar
        return 4.0, "ROUTINE_REPEAT", similar

    @staticmethod
    def _extract_largest_money(text: str) -> int:
        amounts: list[int] = []
        multipliers = {"조": 1_000_000_000_000, "억": 100_000_000, "만": 10_000}
        for match in _MONEY_RE.finditer(text):
            num = float(match.group("num"))
            unit = match.group("unit")
            amounts.append(int(num * multipliers[unit]))
        return max(amounts, default=0)

    @staticmethod
    def _money_score(amount_krw: int) -> int:
        if amount_krw >= 100_000_000_000_000:
            return 15
        if amount_krw >= 10_000_000_000_000:
            return 13
        if amount_krw >= 1_000_000_000_000:
            return 10
        if amount_krw >= 100_000_000_000:
            return 7
        if amount_krw > 0:
            return 4
        return 0

    @staticmethod
    def _policy_score(text: str, schedule_kind: str) -> int:
        if any(keyword in text for keyword in _POLICY_STRONG):
            return 15
        if any(keyword in text for keyword in _POLICY_MEDIUM):
            return 11
        if schedule_kind in {"정책발표", "시행", "의결", "공청회"}:
            return 9
        if schedule_kind in {"정상회담", "회의", "간담회"}:
            return 6
        return 3

    @staticmethod
    def _theme_clarity_score(themes: list[ThemeMatch]) -> int:
        if not themes:
            return 2
        best = max(theme.confidence for theme in themes)
        if best >= 0.9:
            return 15
        if best >= 0.75:
            return 12
        if best >= 0.55:
            return 8
        return 4

    @staticmethod
    def _priority(score: float) -> str:
        if score >= 85:
            return "A_PRIORITY"
        if score >= 70:
            return "WATCH"
        if score >= 55:
            return "LOW_PRIORITY"
        return "IGNORE"

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in _TOKEN_RE.findall(text)
            if token not in _STOPWORDS and len(token) >= 2
        }

    @staticmethod
    def _load_history(path: Path | None) -> list[dict[str, str]]:
        if path is None or not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            return [dict(row) for row in csv.DictReader(fp)]

    @staticmethod
    def _row_date(row: dict[str, str]) -> date | None:
        raw = (row.get("published_at") or row.get("collected_at") or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw[:10], fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _reason(**scores: object) -> str:
        parts = [
            f"authority={scores['authority']}",
            f"novelty={scores['novelty']}({scores['novelty_status']}, similar={scores['similar_count']})",
            f"money={scores['money']}",
            f"policy={scores['policy']}",
            f"theme={scores['theme_clarity']}",
            f"certainty={scores['certainty']}",
        ]
        return "; ".join(parts)
