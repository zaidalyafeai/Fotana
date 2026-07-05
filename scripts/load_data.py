#!/usr/bin/env python3
"""CLI to populate the local cache with football match metrics.

Examples
--------
Load the default 2015/16 top-league preset::

    python scripts/load_data.py --preset

Load a single competition/season::

    python scripts/load_data.py --competition-id 11 --season-id 27

List what StatsBomb Open Data offers::

    python scripts/load_data.py --list-competitions
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running the script directly (python scripts/load_data.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Store  # noqa: E402
from app.ingest import get_source  # noqa: E402
from app.pipeline import PRESET_2015_16_TOP_LEAGUES, load_dataset, load_preset  # noqa: E402


def _progress(done: int, total: int, label: str) -> None:
    print(f"  [{done:>3}/{total}] {label}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition-id", type=int)
    parser.add_argument("--season-id", type=int)
    parser.add_argument(
        "--preset",
        action="store_true",
        help="Load the curated 2015/16 top-league preset.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only load the first N matches (quick smoke tests).",
    )
    parser.add_argument(
        "--list-competitions",
        action="store_true",
        help="Print available competitions/seasons and exit.",
    )
    parser.add_argument("--source", default="statsbomb_open")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(argv)

    source = get_source(args.source)
    store = Store(args.data_dir) if args.data_dir else Store()

    if args.list_competitions:
        comps = source.competitions()
        cols = [
            c
            for c in ["competition_id", "season_id", "competition_name", "season_name"]
            if c in comps.columns
        ]
        print(comps[cols].to_string(index=False))
        return 0

    if args.preset:
        print("Loading 2015/16 top-league preset:")
        for entry in PRESET_2015_16_TOP_LEAGUES:
            print(f"  - {entry['name']}")
        load_preset(source=source, store=store, limit=args.limit, progress=_progress)
        print("Done.")
        return 0

    if args.competition_id is not None and args.season_id is not None:
        print(f"Loading competition {args.competition_id}, season {args.season_id}...")
        tables = load_dataset(
            args.competition_id,
            args.season_id,
            source=source,
            store=store,
            limit=args.limit,
            progress=_progress,
        )
        for level, df in tables.items():
            print(f"  {level}: {len(df)} rows")
        print("Done.")
        return 0

    parser.error("Provide --preset, --list-competitions, or both --competition-id and --season-id")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
