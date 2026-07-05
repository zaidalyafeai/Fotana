"""End-to-end loading pipeline.

Fetches matches and events for a competition/season, extracts discipline
metrics, and stores the aggregated match/team/player tables for the
dashboard to read.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from .db import Store
from .ingest import DataSource, get_source
from .metrics import aggregate, extract_match

#: Curated defaults. The 2015/16 season is StatsBomb's full, all-teams
#: release for these leagues, giving fair cross-team comparisons.
PRESET_2015_16_TOP_LEAGUES = [
    {"competition_id": 11, "season_id": 27, "name": "La Liga 2015/2016"},
    {"competition_id": 2, "season_id": 27, "name": "Premier League 2015/2016"},
    {"competition_id": 12, "season_id": 27, "name": "Serie A 2015/2016"},
    {"competition_id": 7, "season_id": 27, "name": "Ligue 1 2015/2016"},
]


def load_dataset(
    competition_id: int,
    season_id: int,
    source: DataSource | None = None,
    store: Store | None = None,
    limit: int | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """Load one competition/season and persist its metric tables.

    ``limit`` caps the number of matches (useful for quick smoke tests).
    ``progress`` is an optional callback ``(done, total, message)``.
    """
    source = source or get_source()
    store = store or Store()

    matches = source.matches(competition_id, season_id)
    if limit is not None:
        matches = matches.head(limit)
    total = len(matches)

    comp_name = _first(matches, "competition", f"competition {competition_id}")
    season_name = _first(matches, "season", f"season {season_id}")

    player_frames: list[pd.DataFrame] = []
    team_frames: list[pd.DataFrame] = []

    for i, (_, match) in enumerate(matches.iterrows(), start=1):
        match_id = int(match["match_id"])
        label = _match_label(match)
        if progress:
            progress(i, total, label)

        if store.has_events(match_id):
            events = store.load_events(match_id)
        else:
            events = source.events(match_id)
            store.save_events(match_id, events)

        extracted = extract_match(events, match_id)
        player_frames.append(extracted["players"])
        team_frames.append(extracted["teams"])

    tables = aggregate(player_frames, team_frames)

    for level, df in tables.items():
        store.save_metrics(level, df, competition_id, season_id)
    store.register_dataset(
        competition_id, season_id, comp_name, season_name, source.name, total
    )
    return tables


def load_preset(
    preset: list[dict] | None = None,
    source: DataSource | None = None,
    store: Store | None = None,
    limit: int | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> None:
    """Load every competition/season in a preset list."""
    preset = preset or PRESET_2015_16_TOP_LEAGUES
    source = source or get_source()
    store = store or Store()
    for entry in preset:
        load_dataset(
            entry["competition_id"],
            entry["season_id"],
            source=source,
            store=store,
            limit=limit,
            progress=progress,
        )


def _first(df: pd.DataFrame, column: str, default: str) -> str:
    if column in df.columns and not df[column].dropna().empty:
        return str(df[column].dropna().iloc[0])
    return default


def _match_label(match: pd.Series) -> str:
    home = match.get("home_team", "?")
    away = match.get("away_team", "?")
    return f"{home} vs {away}"
