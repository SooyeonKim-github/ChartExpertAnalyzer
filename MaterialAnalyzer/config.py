from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class MaterialCollectorConfig:
    request_timeout_sec: int = 15
    user_agent: str = "ChartExpertAnalyzer-MaterialCollector/1.0"

    naver_news_api_url: str = os.getenv(
        "NAVER_NEWS_API_URL",
        "https://openapi.naver.com/v1/search/news.json",
    )
    naver_display: int = 50
    naver_max_pages_per_query: int = 2

    opendart_api_url: str = "https://opendart.fss.or.kr/api/list.json"
    opendart_page_count: int = 100
    opendart_max_pages: int = 5

    policy_briefing_url: str = "https://www.korea.kr/briefing/pressReleaseList.do"
    policy_max_items: int = 100

    history_file: str = "data/material_items.csv"
    schedule_history_file: str = "data/schedule_items.csv"
    query_file: str = "data/news_queries.csv"
    schedule_lookahead_days: int = 21

    future_hint_keywords: tuple[str, ...] = (
        "예정",
        "개최",
        "발표",
        "공청회",
        "간담회",
        "회의",
        "정상회담",
        "방문",
        "순방",
        "출시",
        "공개",
        "상장",
        "착공",
        "준공",
        "시행",
        "의결",
        "심의",
        "추진",
        "계획",
        "로드맵",
        "컨퍼런스",
        "박람회",
        "포럼",
        "세미나",
    )

    def naver_credentials(self) -> tuple[str | None, str | None]:
        return os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")

    def opendart_api_key(self) -> str | None:
        return os.getenv("OPENDART_API_KEY")


DEFAULT_CONFIG = MaterialCollectorConfig()
