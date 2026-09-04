from __future__ import annotations

from typing import Dict, Type

from ..exceptions import ConfigurationError
from ..models import SourceEndpoint
from .base import BaseCollector


class CollectorFactory:
    REGISTRY: Dict[str, Type[BaseCollector]] = {}

    @classmethod
    def register(cls, *collector_types: str):
        def decorator(collector_cls: Type[BaseCollector]):
            for collector_type in collector_types:
                cls.REGISTRY[collector_type.upper()] = collector_cls
            return collector_cls
        return decorator

    @classmethod
    def create(cls, endpoint: SourceEndpoint) -> BaseCollector:
        collector_cls = cls.REGISTRY.get(endpoint.collector_type.upper())
        if collector_cls is None:
            raise ConfigurationError(f"unknown collector_type={endpoint.collector_type} endpoint={endpoint.endpoint_id}")
        return collector_cls(endpoint)
