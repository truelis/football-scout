"""Fetch Understat player-season stats (xG, xA, xGChain, xGBuildup) to parquet.

Understat is the only free source of advanced stats since FBref lost its Opta
licence in January 2026, and it covers the top five leagues plus Russia - and
nothing else. That limit is not a configuration choice, it is the whole reason
SPEC 2.2 builds v1 where the data is and extends outward later.

Idempotent: re-running refetches (soccerdata caches on disk) and rewrites the
parquet atomically. A failed fetch never replaces a good file.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Keep soccerdata's cache inside data/ so the whole project stays self-contained
# and gitignored. Must be set BEFORE soccerdata is imported - it reads the env
# var at import time to locate its config and cache directories.
CACHE = ROOT / "data" / "soccerdata"
os.environ.setdefault("SOCCERDATA_DIR", str(CACHE))

DEST = ROOT / "data" / "raw" / "understat_player_season.parquet"

# soccerdata ships the top five only. Understat itself also publishes the
# Russian Premier League, which SPEC 2.1 counts as in scope, so it is added
# through soccerdata's custom-league mechanism. This dict is the source of
# truth and is written into the (gitignored) cache config on every run, so a
# fresh clone reproduces it rather than silently losing Russia.
EXTRA_LEAGUES = {
    "RUS-Premier League": {
        "Understat": "RFPL",
        "season_start": "Jul",
        "season_end": "May",
    }
}

LEAGUES = [
    "ENG-Premier League",
    "ESP-La Liga",
    "ITA-Serie A",
    "GER-Bundesliga",
    "FRA-Ligue 1",
    "RUS-Premier League",
]

# Columns the scoring model depends on. Their absence is a schema break, not a
# quiet degradation - fail rather than build a shortlist on missing xG.
REQUIRED_COLUMNS = [
    "minutes",
    "goals",
    "xg",
    "np_goals",
    "np_xg",
    "assists",
    "xa",
    "shots",
    "key_passes",
    "xg_chain",
    "xg_buildup",
    "position",
    "matches",
]

# A league-season below this is a partial scrape, not a small league. The
# smallest real case is Russia at ~470 rows for a full season.
MIN_ROWS_PER_LEAGUE_SEASON = 250


def _install_league_dict() -> None:
    cfg = CACHE / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "league_dict.json").write_text(json.dumps(EXTRA_LEAGUES, indent=2))


def fetch(seasons: list[str]):
    import pandas as pd
    import soccerdata as sd

    frames = []
    for league in LEAGUES:
        for season in seasons:
            print(f"  {league:24} {season} … ", end="", flush=True)
            try:
                df = sd.Understat(leagues=league, seasons=season).read_player_season_stats()
            except Exception as exc:  # noqa: BLE001 - see below
                # Loud, and specific about which league-season died. A silent
                # skip here would produce a shortlist missing a whole league
                # with nothing in the output to say so.
                raise RuntimeError(f"Understat fetch failed for {league} {season}: {exc}") from exc
            if len(df) < MIN_ROWS_PER_LEAGUE_SEASON:
                raise RuntimeError(
                    f"{league} {season} returned {len(df)} rows, expected at least "
                    f"{MIN_ROWS_PER_LEAGUE_SEASON}. Refusing a partial scrape."
                )
            missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                raise RuntimeError(f"{league} {season} is missing columns: {missing}")
            print(f"{len(df):>5} players")
            frames.append(df.reset_index())
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--seasons",
        nargs="+",
        default=["2024", "2025"],
        help="Understat season keys; '2025' means the 2025/26 campaign. Two are "
        "needed by default because the trajectory axis compares season on season.",
    )
    args = ap.parse_args()

    logging.disable(logging.INFO)
    _install_league_dict()

    print(f"fetching Understat: {len(LEAGUES)} leagues x {len(args.seasons)} seasons")
    try:
        df = fetch(args.seasons)
    except Exception as exc:  # noqa: BLE001 - any failure must leave data untouched
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("Existing parquet left untouched.", file=sys.stderr)
        return 1

    # Land to a temp path, then swap. Same discipline as the Transfermarkt
    # download: a half-written parquet must never replace a good one.
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(DEST)

    print(f"\nOK -> {DEST}")
    print(
        f"  {len(df):,} player-seasons, {df['league'].nunique()} leagues, "
        f"{df['season'].nunique()} seasons"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
