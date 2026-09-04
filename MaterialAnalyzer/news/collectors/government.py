from .factory import CollectorFactory
from .html_list import HtmlListCollector


@CollectorFactory.register("GOV_HTML", "GOV_HTML_LIST")
class GovernmentCollector(HtmlListCollector):
    """Configuration-driven government press-release collector."""
    pass
