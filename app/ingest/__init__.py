"""Data ingestion layer.

Exposes a pluggable :class:`DataSource` interface so that additional
providers (e.g. a live API) can be added alongside the default StatsBomb
Open Data source.
"""

from .base import DataSource
from .statsbomb import StatsBombSource

__all__ = ["DataSource", "StatsBombSource", "get_source"]


def get_source(name: str = "statsbomb_open") -> DataSource:
    """Return a data source instance by name."""
    sources = {
        "statsbomb_open": StatsBombSource,
    }
    if name not in sources:
        raise ValueError(
            f"Unknown data source '{name}'. Available: {sorted(sources)}"
        )
    return sources[name]()
