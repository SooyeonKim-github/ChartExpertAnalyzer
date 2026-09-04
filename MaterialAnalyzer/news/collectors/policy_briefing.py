from .factory import CollectorFactory
from .html_list import HtmlListCollector


@CollectorFactory.register("GOV_AGGREGATOR", "POLICY_BRIEFING")
class PolicyBriefingCollector(HtmlListCollector):
    """Policy Briefing fallback aggregator."""
    pass
