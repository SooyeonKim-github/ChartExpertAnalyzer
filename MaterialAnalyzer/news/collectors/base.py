from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..http import HttpClient
from ..models import ArticleCandidate, FetchedContent, RawArticle, SourceEndpoint


class BaseCollector(ABC):
    """Source adapter: discover -> fetch -> parse."""

    def __init__(self, endpoint: SourceEndpoint, http_client: HttpClient | None = None):
        self.endpoint = endpoint
        self.http = http_client or HttpClient()

    @abstractmethod
    def discover(self) -> List[ArticleCandidate]:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, candidate: ArticleCandidate) -> FetchedContent:
        raise NotImplementedError

    @abstractmethod
    def parse(self, candidate: ArticleCandidate, fetched: FetchedContent) -> RawArticle:
        raise NotImplementedError
