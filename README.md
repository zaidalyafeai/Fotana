# Football Match Discipline Outliers

An app to collect statistics from football (soccer) matches and find weird
outliers - with a focus on the relationship between **challenges / tackles**
and **cards** (yellow and red).

It ingests match event data (default: free **StatsBomb Open Data**, no API
key required), computes discipline metrics at match / team / player level,
detects statistical outliers, and presents them in an interactive Streamlit
dashboard.

## What it answers

- Which players or teams pick up far more (or far fewer) cards than their
  volume of tackles / challenges would suggest?
- What is the typical `cards per 100 challenges`, `tackles per card`, or
  `fouls per card` - and who sits at the extremes?

## Data source

By default the app uses [StatsBomb Open Data](https://github.com/statsbomb/open-data),
which provides free, event-level data (tackles, duels, fouls, cards) for a
range of competitions.

Coverage varies by league/season. The **2015/16 season is a full, all-teams
release** for La Liga, Premier League, Serie A, and Ligue 1, which makes it
ideal for fair cross-team outlier comparisons (this is the built-in preset).
Many other La Liga seasons are Barcelona-centric, so Real Madrid, for
example, appears fully only in 2015/16 and via Clasicos elsewhere.

The ingestion layer is pluggable (`app/ingest/base.py`), so a live provider
(e.g. API-Football) can be added later behind the same interface.

## Install

```bash
pip install -r requirements.txt
```

## Load data

Load the curated 2015/16 top-league preset:

```bash
python scripts/load_data.py --preset
```

Or a single competition/season (StatsBomb IDs; e.g. La Liga = 11, season 27):

```bash
python scripts/load_data.py --competition-id 11 --season-id 27
```

Quickly try a few matches only:

```bash
python scripts/load_data.py --competition-id 11 --season-id 27 --limit 5
```

List everything StatsBomb Open Data offers:

```bash
python scripts/load_data.py --list-competitions
```

Downloaded events are cached as Parquet under `data/cache/`, and computed
metric tables are stored in `data/metrics.db` (SQLite). Data can also be
loaded directly from the dashboard sidebar.

## Live demo (GitHub Pages)

The app is deployed as a static site on GitHub Pages (no Python or Streamlit
required in the browser):

**https://zaidalyafeai.github.io/Fotana/**

The built site (2015/16 La Liga, Premier League, Serie A, Ligue 1) lives in
[`docs/`](docs/). To enable hosting:

1. Open **Settings → Pages** in this repo.
2. Under **Build and deployment → Source**, choose **Deploy from a branch**.
3. Select branch **`main`**, folder **`/docs`**, and save.

The site should be live within a minute or two.

For automated rebuilds on every push, switch the Pages source to **GitHub
Actions** instead. The workflow in [`.github/workflows/pages.yml`](.github/workflows/pages.yml)
downloads StatsBomb data, recomputes metrics, and publishes a fresh artifact.

To rebuild the static site locally:

```bash
python scripts/load_data.py --preset
python scripts/export_static_site.py --output docs
python -m http.server --directory docs
```

Then open http://localhost:8000/

## Run the Streamlit dashboard (local)

```bash
streamlit run app/dashboard.py
```

Use the sidebar to pick a dataset, aggregation level (player / team /
match), a ratio metric, a minimum-volume filter, and which outlier methods
to apply. The main panel shows a challenges-vs-cards scatter (outliers
highlighted), the distribution of the chosen ratio with IQR fences, and a
ranked, downloadable table of outliers.

## How it works

```
StatsBomb Open Data (JSON via statsbombpy)
        |  app/ingest
        v
Parquet event cache + SQLite metrics   (app/db.py)
        |  app/metrics.py
        v
Match / team / player metrics + ratios
        |  app/outliers.py
        v
Streamlit dashboard  (app/dashboard.py)
        |  scripts/export_static_site.py
        v
GitHub Pages static dashboard  (site/)
```

### Metrics (`app/metrics.py`)

From the event feed, per team and per player:

- **Tackles** - `Duel` events with `duel_type == "Tackle"`.
- **Challenges** - all `Duel` events plus `50/50` events.
- **Fouls committed** - `Foul Committed` events.
- **Cards** - yellow / second yellow / red from `foul_committed_card` and
  `bad_behaviour_card`.
- Player minutes are estimated from starting XI, substitutions and player-off
  events for per-90 metrics.

Derived ratios include `cards_per_100_challenges`, `tackles_per_card`,
`tackles_per_yellow`, `fouls_per_card`, `cards_per_foul`, and per-90 rates.
Ratios that divide by cards are left undefined (`NaN`) when a row has zero
cards, so they do not distort outlier scoring.

### Outlier detection (`app/outliers.py`)

Three complementary univariate methods: z-score, modified (MAD-based)
z-score, and IQR fences. Rows are ranked by a robust deviation magnitude
weighted by how many methods agree. A minimum-volume filter avoids flagging
noisy ratios from tiny samples.

## Tests

```bash
python -m pytest tests/ -q
```

## Attribution

Data provided by [StatsBomb](https://statsbomb.com/). Per the StatsBomb Open
Data licence, any published charts, tables, or research derived from this
data must credit StatsBomb.
