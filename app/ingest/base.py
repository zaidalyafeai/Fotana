"""Abstract data source interface.

Every provider returns pandas DataFrames with a stable, documented set of
columns so the rest of the pipeline (storage, metrics, outliers, dashboard)
is independent of where the data came from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataSource(ABC):
    """Interface all football data providers must implement."""

    #: Short, unique identifier for the source.
    name: str = "base"

    @abstractmethod
    def competitions(self) -> pd.DataFrame:
        """Return available competition/season combinations.

        Expected columns include at least ``competition_id``,
        ``season_id``, ``competition_name`` and ``season_name``.
        """

    @abstractmethod
    def matches(self, competition_id: int, season_id: int) -> pd.DataFrame:
        """Return matches for a competition/season.

        Expected columns include at least ``match_id``, ``home_team`` and
        ``away_team``.
        """

    @abstractmethod
    def events(self, match_id: int) -> pd.DataFrame:
        """Return the event feed for a single match.

        The frame is one row per event. Discipline analysis relies on the
        ``type``, ``team``, ``team_id``, ``player``, ``player_id`` and
        ``minute`` columns, plus (when present) ``duel_type``,
        ``foul_committed_card`` and ``bad_behaviour_card``.
        """
