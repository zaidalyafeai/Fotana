"""StatsBomb Open Data source.

Uses the ``statsbombpy`` package to stream StatsBomb's free, public event
data. No authentication is required for the open data.

Data provided by StatsBomb - https://github.com/statsbomb/open-data
"""

from __future__ import annotations

import os

import pandas as pd

# Silence the "credentials were not supplied" warnings printed by
# statsbombpy when accessing the free open data (no auth needed).
os.environ.setdefault("NO_AUTH_WARNINGS", "1")

from statsbombpy import sb  # noqa: E402  (must set env var before import use)

from .base import DataSource


class StatsBombSource(DataSource):
    """Read football event data from StatsBomb Open Data."""

    name = "statsbomb_open"

    def competitions(self) -> pd.DataFrame:
        return sb.competitions()

    def matches(self, competition_id: int, season_id: int) -> pd.DataFrame:
        return sb.matches(competition_id=competition_id, season_id=season_id)

    def events(self, match_id: int) -> pd.DataFrame:
        return sb.events(match_id=match_id)
