"""Fetch Club Elo team ratings to parquet.

Club Elo is the input for league strength (SPEC 4.2 int_league_strength) and
team strength (int_team_strength). Until it lands, seeds/league_tiers.csv holds
hand-written placeholder coefficients that Task 3 found are carrying most of the
ranking - so this is the highest-leverage remaining Phase 2 work.

STATUS 2026-09-05: api.clubelo.com returns HTTP 502 on every endpoint and date.
clubelo.com itself responds, so this is an upstream outage rather than a change
of interface. This module is written against the documented API and will work
when it returns; run it and check.

No HTML fallback, deliberately. The site's public pages carry Elo *ranks* on a
fixtures table, not per-club ratings, so scraping them would mean maintaining a
fragile parser that produces worse data than the API. SPEC 9's mitigation for a
broken scraper is to fail loudly with a clear message, not to improvise a
lower-quality source.

One request per snapshot date rather than per club: read_by_date returns every
club at once, which is ~1 request per season instead of ~800.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "soccerdata"
os.environ.setdefault("SOCCERDATA_DIR", str(CACHE))

DEST = ROOT / "data" / "raw" / "clubelo_ratings.parquet"

# One snapshot per season, taken in FEBRUARY - mid-season, so ratings reflect a
# settled squad rather than a summer of transfers or a pre-season lull. Using a
# consistent point each year is what makes season-on-season comparison honest.
SNAPSHOT_MONTH_DAY = "02-01"

# Below this, the snapshot is a partial response, not a quiet season. A normal
# Club Elo snapshot carries several thousand clubs across all of Europe.
MIN_CLUBS_PER_SNAPSHOT = 500

REQUIRED_COLUMNS = ["team", "country", "level", "elo", "from", "to", "rank"]


def snapshot_dates(seasons: list[int]) -> list[str]:
    """A season starting in year N is snapshotted in February of N+1."""
    return [f"{s + 1}-{SNAPSHOT_MONTH_DAY}" for s in seasons]


def fetch(seasons: list[int]):
    import pandas as pd
    import soccerdata as sd

    ce = sd.ClubElo()
    frames = []
    for season, date in zip(seasons, snapshot_dates(seasons), strict=True):
        print(f"  season {season} @ {date} … ", end="", flush=True)
        try:
            df = ce.read_by_date(date)
        except Exception as exc:  # noqa: BLE001 - see the message below
            raise RuntimeError(
                f"Club Elo fetch failed for {date}: {exc}\n"
                "  api.clubelo.com was returning HTTP 502 as of 2026-09-05. If it "
                "still is, this is an upstream outage - retry later rather than "
                "working around it. League strength will keep using the "
                "placeholder coefficients in seeds/league_tiers.csv until this "
                "succeeds, which is a known and documented limitation."
            ) from exc

        df = df.reset_index()
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise RuntimeError(
                f"Club Elo snapshot {date} is missing columns {missing}. "
                f"Got: {sorted(df.columns)}. The API's shape has changed - "
                "reconcile before trusting anything downstream."
            )
        if len(df) < MIN_CLUBS_PER_SNAPSHOT:
            raise RuntimeError(
                f"snapshot {date} returned {len(df)} clubs, expected at least "
                f"{MIN_CLUBS_PER_SNAPSHOT}. Refusing a partial response."
            )
        print(f"{len(df):>5} clubs")
        frames.append(df.assign(season=season, snapshot_date=date))
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=[2024, 2025],
        help="Seasons by starting year, matching macros/season_of.sql.",
    )
    args = ap.parse_args()
    logging.disable(logging.INFO)

    print(f"fetching Club Elo: {len(args.seasons)} season snapshots")
    try:
        df = fetch(args.seasons)
    except Exception as exc:  # noqa: BLE001 - any failure must leave data untouched
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("Existing parquet left untouched.", file=sys.stderr)
        return 1

    # Land to a temp path, then swap - same discipline as the other ingests.
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(DEST)

    print(f"\nOK -> {DEST}")
    print(f"  {len(df):,} club-seasons, {df['country'].nunique()} countries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
