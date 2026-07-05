"""Persistence layer.

* Raw match events are cached as Parquet files so they are only downloaded
  once (StatsBomb open data is served as static JSON over the network).
* Computed metric tables (match / team / player) and a catalogue of loaded
  datasets live in a small SQLite database for fast dashboard queries.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Store:
    """File-backed cache + SQLite metric store."""

    def __init__(self, base_dir: str | Path = DEFAULT_DATA_DIR):
        self.base_dir = Path(base_dir)
        self.events_dir = self.base_dir / "cache" / "events"
        self.db_path = self.base_dir / "metrics.db"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # -- events cache -----------------------------------------------------
    def _event_path(self, match_id: int) -> Path:
        return self.events_dir / f"{int(match_id)}.parquet"

    def has_events(self, match_id: int) -> bool:
        return self._event_path(match_id).exists()

    def save_events(self, match_id: int, events: pd.DataFrame) -> None:
        # Parquet needs homogeneous column types; object columns holding
        # dicts/lists are dropped as they are unused downstream.
        safe = events.copy()
        for col in safe.columns:
            if safe[col].map(lambda v: isinstance(v, (dict, list))).any():
                safe = safe.drop(columns=[col])
        safe.to_parquet(self._event_path(match_id), index=False)

    def load_events(self, match_id: int) -> pd.DataFrame:
        return pd.read_parquet(self._event_path(match_id))

    # -- sqlite metric store ---------------------------------------------
    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    competition_id INTEGER,
                    season_id INTEGER,
                    competition_name TEXT,
                    season_name TEXT,
                    source TEXT,
                    matches INTEGER,
                    loaded_at TEXT,
                    PRIMARY KEY (competition_id, season_id, source)
                )
                """
            )

    @staticmethod
    def _table(level: str, competition_id: int, season_id: int) -> str:
        return f"metrics_{level}_{int(competition_id)}_{int(season_id)}"

    def save_metrics(
        self,
        level: str,
        df: pd.DataFrame,
        competition_id: int,
        season_id: int,
    ) -> None:
        with sqlite3.connect(self.db_path) as con:
            df.to_sql(
                self._table(level, competition_id, season_id),
                con,
                if_exists="replace",
                index=False,
            )

    def load_metrics(
        self, level: str, competition_id: int, season_id: int
    ) -> pd.DataFrame:
        table = self._table(level, competition_id, season_id)
        with sqlite3.connect(self.db_path) as con:
            return pd.read_sql(f'SELECT * FROM "{table}"', con)

    def register_dataset(
        self,
        competition_id: int,
        season_id: int,
        competition_name: str,
        season_name: str,
        source: str,
        matches: int,
    ) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                INSERT OR REPLACE INTO datasets
                (competition_id, season_id, competition_name, season_name,
                 source, matches, loaded_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    int(competition_id),
                    int(season_id),
                    competition_name,
                    season_name,
                    source,
                    int(matches),
                ),
            )

    def list_datasets(self) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as con:
            try:
                return pd.read_sql(
                    "SELECT * FROM datasets ORDER BY competition_name, season_name",
                    con,
                )
            except Exception:
                return pd.DataFrame()
