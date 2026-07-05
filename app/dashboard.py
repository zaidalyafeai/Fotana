"""Streamlit dashboard for exploring football discipline outliers.

Run with::

    streamlit run app/dashboard.py

If no data has been loaded yet, use the sidebar loader or the CLI::

    python scripts/load_data.py --preset

Data provided by StatsBomb - https://github.com/statsbomb/open-data
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Store  # noqa: E402
from app.metrics import RATIO_LABELS  # noqa: E402
from app.outliers import METHODS, detect  # noqa: E402
from app.pipeline import PRESET_2015_16_TOP_LEAGUES, load_dataset  # noqa: E402

st.set_page_config(
    page_title="Football Discipline Outliers",
    page_icon="soccer",
    layout="wide",
)

# Sensible denominator for each ratio, used both to filter low-volume rows
# and to size the scatter x-axis.
RATIO_DENOMINATOR = {
    "cards_per_100_challenges": "challenges",
    "cards_per_100_tackles": "tackles",
    "tackles_per_card": "tackles",
    "challenges_per_card": "challenges",
    "tackles_per_yellow": "tackles",
    "fouls_per_card": "fouls_committed",
    "cards_per_foul": "fouls_committed",
    "fouls_per_challenge": "challenges",
    "tackles_per_90": "minutes",
    "challenges_per_90": "minutes",
    "fouls_per_90": "minutes",
    "cards_per_90": "minutes",
}

ENTITY_LABEL = {"player": "Players", "team": "Teams", "match": "Team-in-match"}


@st.cache_data(show_spinner=False)
def _list_datasets() -> pd.DataFrame:
    return Store().list_datasets()


@st.cache_data(show_spinner=False)
def _load_metrics(level: str, competition_id: int, season_id: int) -> pd.DataFrame:
    return Store().load_metrics(level, competition_id, season_id)


def _name_column(df: pd.DataFrame) -> str:
    for col in ("player", "team"):
        if col in df.columns:
            return col
    return df.columns[0]


def _unique(cols: list[str]) -> list[str]:
    """Preserve order while dropping duplicate column names."""
    seen: set[str] = set()
    out: list[str] = []
    for c in cols:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def sidebar_loader() -> None:
    st.sidebar.header("Load data")
    st.sidebar.caption(
        "First run needs data. Loading downloads events from StatsBomb "
        "Open Data and can take a few minutes per league."
    )
    presets = {e["name"]: e for e in PRESET_2015_16_TOP_LEAGUES}
    choice = st.sidebar.selectbox("Preset league (2015/16)", list(presets))
    limit = st.sidebar.number_input(
        "Match limit (0 = all)", min_value=0, max_value=400, value=0, step=10
    )
    if st.sidebar.button("Load selected league"):
        entry = presets[choice]
        prog = st.sidebar.progress(0.0, text="Starting...")

        def _cb(done: int, total: int, label: str) -> None:
            prog.progress(done / max(total, 1), text=f"[{done}/{total}] {label}")

        load_dataset(
            entry["competition_id"],
            entry["season_id"],
            limit=None if limit == 0 else int(limit),
            progress=_cb,
        )
        prog.empty()
        _list_datasets.clear()
        _load_metrics.clear()
        st.sidebar.success(f"Loaded {choice}")
        st.rerun()


def main() -> None:
    st.title("Football Match Discipline Outliers")
    st.caption(
        "Investigating the relationship between challenges / tackles and "
        "cards, and flagging weird outliers. Data provided by StatsBomb."
    )

    sidebar_loader()

    datasets = _list_datasets()
    if datasets.empty:
        st.info(
            "No data loaded yet. Use **Load data** in the sidebar, or run "
            "`python scripts/load_data.py --preset` in a terminal."
        )
        return

    datasets = datasets.copy()
    datasets["label"] = (
        datasets["competition_name"] + " " + datasets["season_name"]
    )
    st.sidebar.header("Explore")
    label = st.sidebar.selectbox("Dataset", datasets["label"].tolist())
    row = datasets[datasets["label"] == label].iloc[0]

    level = st.sidebar.radio(
        "Aggregation level",
        options=["player", "team", "match"],
        format_func=lambda v: ENTITY_LABEL[v],
    )

    df = _load_metrics(level, int(row["competition_id"]), int(row["season_id"]))
    if df.empty:
        st.warning("This dataset/level has no rows.")
        return

    available_ratios = [c for c in RATIO_LABELS if c in df.columns and df[c].notna().any()]
    default_ratio = (
        "cards_per_100_challenges"
        if "cards_per_100_challenges" in available_ratios
        else available_ratios[0]
    )
    ratio = st.sidebar.selectbox(
        "Ratio / metric",
        available_ratios,
        index=available_ratios.index(default_ratio),
        format_func=lambda c: RATIO_LABELS.get(c, c),
    )

    denom_col = RATIO_DENOMINATOR.get(ratio, "challenges")
    denom_col = denom_col if denom_col in df.columns else None
    min_denom = 0.0
    if denom_col is not None:
        denom_max = float(df[denom_col].max())
        default_min = _default_min_denominator(level, denom_col, denom_max)
        min_denom = st.sidebar.slider(
            f"Minimum {denom_col} (volume filter)",
            min_value=0.0,
            max_value=max(denom_max, 1.0),
            value=float(default_min),
            help="Excludes low-volume rows whose ratios are noisy.",
        )

    methods = st.sidebar.multiselect(
        "Outlier methods",
        options=list(METHODS),
        default=list(METHODS),
        format_func=lambda m: m.replace("_", " ").title(),
    )
    if not methods:
        methods = list(METHODS)

    result = detect(
        df,
        ratio,
        methods=tuple(methods),
        min_denominator=min_denom if denom_col else None,
        denominator_column=denom_col,
    )
    work = result.frame
    name_col = _name_column(work)

    n_outliers = int(work["is_outlier"].sum()) if "is_outlier" in work else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entities analysed", len(work))
    c2.metric("Outliers flagged", n_outliers)
    c3.metric(f"Median {RATIO_LABELS.get(ratio, ratio)}", f"{work[ratio].median():.2f}")
    if "iqr" in result.bounds:
        lo, hi = result.bounds["iqr"]
        c4.metric("IQR fence (upper)", f"{hi:.2f}")

    _scatter(work, ratio, denom_col, name_col)
    _histogram(work, ratio, result)
    _table(work, ratio, name_col, level)


def _default_min_denominator(level: str, denom_col: str, denom_max: float) -> float:
    if denom_col == "minutes":
        return min(270.0, denom_max)  # ~3 full matches
    if level == "player":
        return min(20.0, denom_max)
    return 0.0


def _scatter(df: pd.DataFrame, ratio: str, denom_col: str | None, name_col: str) -> None:
    st.subheader("Challenges vs cards")
    x = denom_col if denom_col and denom_col in df.columns else "challenges"
    y = "cards" if "cards" in df.columns else ratio
    hover = _unique(
        [c for c in [name_col, "team", ratio, "challenges", "tackles", "cards", "matches"] if c in df.columns]
    )
    fig = px.scatter(
        df,
        x=x,
        y=y,
        color="is_outlier" if "is_outlier" in df.columns else None,
        size=ratio if df[ratio].ge(0).all() else None,
        hover_name=name_col,
        hover_data=hover,
        color_discrete_map={True: "#e45756", False: "#4c78a8"},
        labels={x: x.replace("_", " ").title(), y: y.title(), "is_outlier": "Outlier"},
    )
    fig.update_layout(height=460, legend_title_text="Outlier")
    st.plotly_chart(fig, width="stretch")


def _histogram(df: pd.DataFrame, ratio: str, result) -> None:
    st.subheader(f"Distribution of {RATIO_LABELS.get(ratio, ratio)}")
    fig = px.histogram(df, x=ratio, nbins=40)
    if "iqr" in result.bounds:
        lo, hi = result.bounds["iqr"]
        for bound in (lo, hi):
            if pd.notna(bound):
                fig.add_vline(x=bound, line_dash="dash", line_color="#e45756")
    fig.update_layout(height=340)
    st.plotly_chart(fig, width="stretch")


def _table(df: pd.DataFrame, ratio: str, name_col: str, level: str) -> None:
    st.subheader("Ranked outliers")
    display_cols = _unique(
        [
            c
            for c in [
                name_col,
                "team",
                "matches",
                "minutes",
                "tackles",
                "challenges",
                "fouls_committed",
                "yellow_cards",
                "cards",
                ratio,
                "outlier_method_count",
                "outlier_score",
                "is_outlier",
            ]
            if c in df.columns
        ]
    )
    show_only = st.checkbox("Show only flagged outliers", value=True)
    view = df[df["is_outlier"]] if (show_only and "is_outlier" in df.columns) else df
    st.dataframe(
        view[display_cols].round(2),
        width="stretch",
        hide_index=True,
    )
    st.download_button(
        "Download this table (CSV)",
        view[display_cols].to_csv(index=False).encode("utf-8"),
        file_name=f"outliers_{level}_{ratio}.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
