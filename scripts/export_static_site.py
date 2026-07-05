#!/usr/bin/env python3
"""Export loaded metrics to a static site for GitHub Pages.

Reads metric tables from the local SQLite store (populate first with
``scripts/load_data.py --preset``) and writes JSON plus the static UI
into the output directory (typically ``docs/``).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Store  # noqa: E402
from app.metrics import RATIO_LABELS  # noqa: E402

LEVELS = ("player", "team", "match")
SITE_SRC = Path(__file__).resolve().parent.parent / "site"


def _json_safe(records: list[dict]) -> list[dict]:
    out = []
    for row in records:
        clean = {}
        for k, v in row.items():
            if v is None:
                clean[k] = None
            elif isinstance(v, float) and (v != v):  # NaN
                clean[k] = None
            else:
                clean[k] = v
        out.append(clean)
    return out


def export(output: Path, store: Store | None = None) -> None:
    store = store or Store()
    datasets = store.list_datasets()
    if datasets.empty:
        raise SystemExit(
            "No datasets in the local store. Run: python scripts/load_data.py --preset"
        )

    data_dir = output / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    manifest_datasets = []
    for _, row in datasets.iterrows():
        cid = int(row["competition_id"])
        sid = int(row["season_id"])
        key = f"{cid}_{sid}"
        manifest_datasets.append(
            {
                "key": key,
                "competition_id": cid,
                "season_id": sid,
                "competition_name": row["competition_name"],
                "season_name": row["season_name"],
                "matches": int(row["matches"]),
                "levels": {},
            }
        )
        entry = manifest_datasets[-1]
        for level in LEVELS:
            df = store.load_metrics(level, cid, sid)
            filename = f"{key}_{level}.json"
            records = _json_safe(df.to_dict(orient="records"))
            (data_dir / filename).write_text(json.dumps(records), encoding="utf-8")
            entry["levels"][level] = filename

    manifest = {
        "datasets": manifest_datasets,
        "ratio_labels": RATIO_LABELS,
        "attribution": "Data provided by StatsBomb - https://github.com/statsbomb/open-data",
    }
    (data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    if SITE_SRC.exists():
        for item in SITE_SRC.iterdir():
            dest = output / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
    else:
        raise SystemExit(f"Missing static site source at {SITE_SRC}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs",
        help="Directory to write the GitHub Pages site (default: docs/)",
    )
    parser.add_argument("--data-dir", default=None, help="Metrics store base dir")
    args = parser.parse_args(argv)

    store = Store(args.data_dir) if args.data_dir else Store()
    export(args.output, store=store)
    print(f"Static site written to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
