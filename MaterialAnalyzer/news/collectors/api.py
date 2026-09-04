from __future__ import annotations

from ..exceptions import ConfigurationError
from .base import BaseCollector
from .factory import CollectorFactory


@CollectorFactory.register("API")
class ApiCollector(BaseCollector):
    def discover(self):
        raise ConfigurationError(f"generic API endpoint requires a concrete adapter: {self.endpoint.endpoint_id}")

    def fetch(self, candidate):
        return self.http.get(candidate.url)

    def parse(self, candidate, fetched):
        raise ConfigurationError(f"generic API endpoint requires parse implementation: {self.endpoint.endpoint_id}")
