from .factory import CollectorFactory
from .html_list import HtmlListCollector


@CollectorFactory.register("KIND_HTML", "KIND")
class KindCollector(HtmlListCollector):
    """KIND adapter; V1 reuses the configuration-driven HTML collector."""
    pass
