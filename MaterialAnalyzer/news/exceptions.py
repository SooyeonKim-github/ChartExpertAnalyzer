class CollectorError(Exception):
    """Base exception for news collection failures."""


class DiscoverError(CollectorError):
    pass


class FetchError(CollectorError):
    pass


class ParseError(CollectorError):
    pass


class RateLimitError(CollectorError):
    pass


class AccessDeniedError(CollectorError):
    pass


class ConfigurationError(CollectorError):
    pass
