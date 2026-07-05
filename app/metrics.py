"""Metrics engine.

Turns raw StatsBomb-style event feeds into discipline-oriented metrics at
three levels of aggregation:

* ``match``  - one row per team per match (team-in-match).
* ``team``   - one row per team, aggregated across all loaded matches.
* ``player`` - one row per player, aggregated across all loaded matches.

The headline question this app investigates is the relationship between
challenges / tackles and cards, so the derived ratios centre on that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Raw count columns produced by :func:`extract_match`.
COUNT_COLUMNS = [
    "tackles",
    "duels",
    "fifty_fifties",
    "challenges",
    "fouls_committed",
    "yellow_cards",
    "second_yellows",
    "red_cards",
    "cards",
]


def _col(events: pd.DataFrame, name: str) -> pd.Series:
    """Return a column if present, otherwise an all-NaN series."""
    if name in events.columns:
        return events[name]
    return pd.Series([np.nan] * len(events), index=events.index)


def _match_end_minute(events: pd.DataFrame) -> float:
    """Best-effort length of the match in minutes (incl. stoppage)."""
    if "minute" not in events.columns or events["minute"].dropna().empty:
        return 90.0
    return float(events["minute"].max()) + 1.0


def _player_minutes(events: pd.DataFrame) -> dict[int, float]:
    """Estimate minutes played per ``player_id`` from the event feed.

    Starters play from minute 0; substitutes from the minute they come on;
    players are stopped at the minute they are subbed off or sent off.
    """
    match_end = _match_end_minute(events)
    minutes: dict[int, float] = {}

    with_player = events[events["player_id"].notna()] if "player_id" in events else events.iloc[0:0]
    all_ids = {int(pid) for pid in with_player["player_id"].unique()}

    # Substitutions: the event ``player`` leaves, the replacement enters.
    on_minute: dict[int, float] = {}
    off_minute: dict[int, float] = {}
    subs = events[events.get("type").eq("Substitution")] if "type" in events else events.iloc[0:0]
    repl_id_col = "substitution_replacement_id" in events.columns
    for _, row in subs.iterrows():
        minute = float(row.get("minute", match_end) or match_end)
        pid = row.get("player_id")
        if pd.notna(pid):
            off_minute[int(pid)] = minute
        if repl_id_col and pd.notna(row.get("substitution_replacement_id")):
            on_minute[int(row["substitution_replacement_id"])] = minute

    # Player Off events (red cards / injuries that end a player's match).
    offs = events[events.get("type").eq("Player Off")] if "type" in events else events.iloc[0:0]
    for _, row in offs.iterrows():
        pid = row.get("player_id")
        if pd.notna(pid):
            off_minute[int(pid)] = float(row.get("minute", match_end) or match_end)

    replacements = set(on_minute)
    for pid in all_ids:
        start = on_minute.get(pid, 0.0) if pid in replacements else 0.0
        end = off_minute.get(pid, match_end)
        minutes[pid] = max(0.0, end - start)
    return minutes


def extract_match(events: pd.DataFrame, match_id: int) -> dict[str, pd.DataFrame]:
    """Extract per-player and per-team discipline counts for one match.

    Returns a dict with ``players`` and ``teams`` DataFrames.
    """
    events = events.copy()
    match_end = _match_end_minute(events)

    etype = _col(events, "type")
    duel_type = _col(events, "duel_type")
    foul_card = _col(events, "foul_committed_card")
    behaviour_card = _col(events, "bad_behaviour_card")

    is_duel = etype.eq("Duel")
    is_tackle = is_duel & duel_type.eq("Tackle")
    is_fifty = etype.eq("50/50")
    is_foul = etype.eq("Foul Committed")

    card = foul_card.fillna(behaviour_card)
    is_yellow = card.eq("Yellow Card")
    is_second_yellow = card.eq("Second Yellow")
    is_red = card.eq("Red Card")

    work = pd.DataFrame(
        {
            "team": _col(events, "team"),
            "team_id": _col(events, "team_id"),
            "player": _col(events, "player"),
            "player_id": _col(events, "player_id"),
            "tackles": is_tackle.astype(int),
            "duels": is_duel.astype(int),
            "fifty_fifties": is_fifty.astype(int),
            "fouls_committed": is_foul.astype(int),
            "yellow_cards": is_yellow.astype(int),
            "second_yellows": is_second_yellow.astype(int),
            "red_cards": is_red.astype(int),
        }
    )
    work["challenges"] = work["duels"] + work["fifty_fifties"]
    # A second yellow also implies a red (sending off) and both are cards.
    work["cards"] = work["yellow_cards"] + work["second_yellows"] + work["red_cards"]

    agg = {c: "sum" for c in COUNT_COLUMNS}

    players = (
        work[work["player_id"].notna()]
        .groupby(["team_id", "team", "player_id", "player"], as_index=False)
        .agg(agg)
    )
    minutes = _player_minutes(events)
    players["minutes"] = players["player_id"].map(minutes).fillna(0.0)
    players.insert(0, "match_id", match_id)

    teams = work.groupby(["team_id", "team"], as_index=False).agg(agg)
    teams["minutes"] = match_end
    teams.insert(0, "match_id", match_id)

    return {"players": players, "teams": teams}


def add_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived discipline ratios to an aggregated counts frame.

    Ratios that divide by a card count use ``NaN`` when there are no cards
    (the ratio is undefined / infinite and would distort outlier scoring).
    """
    df = df.copy()

    def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
        den = den.astype(float)
        return np.where(den > 0, num.astype(float) / den, np.nan)

    df["tackles_per_card"] = safe_div(df["tackles"], df["cards"])
    df["challenges_per_card"] = safe_div(df["challenges"], df["cards"])
    df["fouls_per_card"] = safe_div(df["fouls_committed"], df["cards"])
    df["tackles_per_yellow"] = safe_div(df["tackles"], df["yellow_cards"])

    # "How card-happy" per unit of defensive engagement (higher = more
    # cards for the same amount of challenging). Scaled for readability.
    df["cards_per_100_challenges"] = safe_div(df["cards"], df["challenges"]) * 100
    df["cards_per_100_tackles"] = safe_div(df["cards"], df["tackles"]) * 100
    df["fouls_per_challenge"] = safe_div(df["fouls_committed"], df["challenges"])
    df["cards_per_foul"] = safe_div(df["cards"], df["fouls_committed"])

    if "minutes" in df.columns:
        per90 = safe_div(pd.Series(np.full(len(df), 90.0), index=df.index), df["minutes"])
        df["tackles_per_90"] = df["tackles"].astype(float) * per90
        df["challenges_per_90"] = df["challenges"].astype(float) * per90
        df["fouls_per_90"] = df["fouls_committed"].astype(float) * per90
        df["cards_per_90"] = df["cards"].astype(float) * per90

    return df


def aggregate(
    player_frames: list[pd.DataFrame],
    team_frames: list[pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Combine per-match extracts into match/team/player metric tables."""
    players_all = (
        pd.concat(player_frames, ignore_index=True)
        if player_frames
        else pd.DataFrame(columns=["match_id", "team_id", "team", "player_id", "player", "minutes", *COUNT_COLUMNS])
    )
    teams_all = (
        pd.concat(team_frames, ignore_index=True)
        if team_frames
        else pd.DataFrame(columns=["match_id", "team_id", "team", "minutes", *COUNT_COLUMNS])
    )

    # Match level: one row per team per match (already the shape of teams_all).
    match_level = add_ratios(teams_all.copy())

    # Team level: aggregate across matches.
    if not teams_all.empty:
        team_agg = {c: "sum" for c in COUNT_COLUMNS}
        team_agg["minutes"] = "sum"
        team_level = teams_all.groupby(["team_id", "team"], as_index=False).agg(team_agg)
        team_level["matches"] = (
            teams_all.groupby(["team_id", "team"])["match_id"].nunique().values
        )
        team_level = add_ratios(team_level)
    else:
        team_level = add_ratios(teams_all.copy())

    # Player level: aggregate across matches.
    if not players_all.empty:
        player_agg = {c: "sum" for c in COUNT_COLUMNS}
        player_agg["minutes"] = "sum"
        player_level = players_all.groupby(
            ["player_id", "player", "team_id", "team"], as_index=False
        ).agg(player_agg)
        player_level["matches"] = (
            players_all.groupby(["player_id", "player", "team_id", "team"])["match_id"]
            .nunique()
            .values
        )
        player_level = add_ratios(player_level)
    else:
        player_level = add_ratios(players_all.copy())

    return {"match": match_level, "team": team_level, "player": player_level}


#: Human-friendly labels for ratio columns used in the dashboard.
RATIO_LABELS = {
    "cards_per_100_challenges": "Cards per 100 challenges",
    "cards_per_100_tackles": "Cards per 100 tackles",
    "tackles_per_card": "Tackles per card",
    "challenges_per_card": "Challenges per card",
    "tackles_per_yellow": "Tackles per yellow card",
    "fouls_per_card": "Fouls per card",
    "cards_per_foul": "Cards per foul",
    "fouls_per_challenge": "Fouls per challenge",
    "tackles_per_90": "Tackles per 90",
    "challenges_per_90": "Challenges per 90",
    "fouls_per_90": "Fouls per 90",
    "cards_per_90": "Cards per 90",
}
