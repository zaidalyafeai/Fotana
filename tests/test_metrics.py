"""Unit tests for the metrics engine using small synthetic event feeds."""

import numpy as np
import pandas as pd
import pytest

from app.metrics import add_ratios, aggregate, extract_match


def _event(**kw):
    base = {
        "type": None,
        "team": None,
        "team_id": None,
        "player": None,
        "player_id": None,
        "minute": 10,
        "duel_type": None,
        "foul_committed_card": None,
    }
    base.update(kw)
    return base


def synthetic_match():
    """Team A: 2 tackles, 1 aerial duel, 1 fifty-fifty, 1 foul + yellow.

    Team B: 1 tackle, 1 foul (no card).
    """
    rows = [
        _event(type="Duel", duel_type="Tackle", team="A", team_id=1, player="p1", player_id=101),
        _event(type="Duel", duel_type="Tackle", team="A", team_id=1, player="p1", player_id=101),
        _event(type="Duel", duel_type="Aerial Lost", team="A", team_id=1, player="p2", player_id=102),
        _event(type="50/50", team="A", team_id=1, player="p2", player_id=102),
        _event(type="Foul Committed", foul_committed_card="Yellow Card", team="A", team_id=1, player="p1", player_id=101),
        _event(type="Pass", team="A", team_id=1, player="p1", player_id=101),
        _event(type="Duel", duel_type="Tackle", team="B", team_id=2, player="p3", player_id=201),
        _event(type="Foul Committed", team="B", team_id=2, player="p3", player_id=201),
        # A late event so the match length is ~90 minutes.
        _event(type="Half End", team="A", team_id=1, minute=90),
    ]
    return pd.DataFrame(rows)


def test_extract_counts_per_team():
    events = synthetic_match()
    out = extract_match(events, match_id=999)
    teams = out["teams"].set_index("team")

    a = teams.loc["A"]
    assert a["tackles"] == 2
    assert a["duels"] == 3  # 2 tackles + 1 aerial
    assert a["fifty_fifties"] == 1
    assert a["challenges"] == 4  # 3 duels + 1 fifty-fifty
    assert a["fouls_committed"] == 1
    assert a["yellow_cards"] == 1
    assert a["cards"] == 1

    b = teams.loc["B"]
    assert b["tackles"] == 1
    assert b["cards"] == 0


def test_extract_counts_per_player():
    events = synthetic_match()
    out = extract_match(events, match_id=999)
    players = out["players"].set_index("player")

    assert players.loc["p1", "tackles"] == 2
    assert players.loc["p1", "yellow_cards"] == 1
    assert players.loc["p2", "challenges"] == 2  # 1 aerial + 1 fifty-fifty
    assert "match_id" in out["players"].columns


def test_add_ratios_handles_zero_cards():
    df = pd.DataFrame(
        {
            "tackles": [10, 5],
            "duels": [12, 6],
            "fifty_fifties": [0, 0],
            "challenges": [12, 6],
            "fouls_committed": [4, 2],
            "yellow_cards": [2, 0],
            "second_yellows": [0, 0],
            "red_cards": [0, 0],
            "cards": [2, 0],
        }
    )
    out = add_ratios(df)
    assert out.loc[0, "tackles_per_card"] == 5.0
    # No cards -> ratio is undefined (NaN), not infinity.
    assert np.isnan(out.loc[1, "tackles_per_card"])
    assert out.loc[0, "cards_per_100_challenges"] == pytest.approx(100 * 2 / 12)


def test_player_minutes_starter_vs_sub():
    rows = [
        _event(type="Pass", team="A", team_id=1, player="starter", player_id=1, minute=1),
        _event(type="Substitution", team="A", team_id=1, player="starter", player_id=1, minute=60),
        _event(type="Pass", team="A", team_id=1, player="sub", player_id=2, minute=70),
        _event(type="Half End", team="A", team_id=1, minute=90),
    ]
    # Provide the replacement id column so the sub's on-minute is known.
    df = pd.DataFrame(rows)
    df["substitution_replacement_id"] = [np.nan, 2, np.nan, np.nan]

    out = extract_match(df, match_id=1)
    players = out["players"].set_index("player_id")
    # match_end = 91; starter played 0..60, sub played 60..91.
    assert players.loc[1, "minutes"] == 60.0
    assert players.loc[2, "minutes"] == 31.0


def test_aggregate_sums_across_matches():
    m1 = extract_match(synthetic_match(), match_id=1)
    m2 = extract_match(synthetic_match(), match_id=2)
    tables = aggregate(
        [m1["players"], m2["players"]], [m1["teams"], m2["teams"]]
    )
    team = tables["team"].set_index("team")
    assert team.loc["A", "tackles"] == 4  # 2 per match, 2 matches
    assert team.loc["A", "matches"] == 2
    assert "tackles_per_card" in tables["team"].columns
    assert set(tables) == {"match", "team", "player"}
