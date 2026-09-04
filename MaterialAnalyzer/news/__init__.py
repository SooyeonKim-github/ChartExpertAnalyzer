"""News collection infrastructure for MaterialAnalyzer.

This package is intentionally independent from the legacy MaterialAnalyzer.collectors
package so the existing collector workflow can continue while NewsCollector V1 is
introduced incrementally.
"""

from .config_loader import load_endpoints, load_sources

__all__ = ["load_sources", "load_endpoints"]
