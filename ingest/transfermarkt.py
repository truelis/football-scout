"""Download the prepared transfermarkt-datasets DuckDB file.

We do NOT scrape Transfermarkt. dcaribou/transfermarkt-datasets publishes a
prepared, weekly-refreshed DuckDB file with 12 tables; downloading it is both
faster and kinder than scraping, and it is the project's whole reason for
existing.

Refreshing the data == re-downloading this file. dbt attaches it READ-ONLY.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import duckdb
import httpx

URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/transfermarkt-datasets.duckdb"
DEST = Path(__file__).resolve().parents[1] / "data" / "transfermarkt-datasets.duckdb"

# Tables Phase 1 depends on. If any is missing or short after download, the
# refresh failed and we must not overwrite a known-good file.
#
# Floors are set at roughly half the observed row count as of 2026-09-05
# (commit 154367d): players 50,149 / appearances 1,894,350 / valuations
# 656,301 / clubs 796 / competitions 65. `players` is scoped to the 14 covered
# leagues, NOT all of Transfermarkt - an earlier 100,000 floor here rejected a
# complete, valid download. Keep these below reality but above zero: the point
# is catching a truncated fetch, not asserting the dataset never shrinks.
REQUIRED = {
    "players": 40_000,
    "appearances": 1_000_000,
    "player_valuations": 300_000,
    "clubs": 400,
    "competitions": 30,
}


def validate(path: Path) -> None:
    """Fail loudly. A partial download that silently replaces good data is the
    worst outcome here - dbt would happily build a shortlist from nothing."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        present = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        missing = set(REQUIRED) - present
        if missing:
            raise RuntimeError(f"downloaded file is missing tables: {sorted(missing)}")
        for table, min_rows in REQUIRED.items():
            n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            if n < min_rows:
                raise RuntimeError(
                    f"table {table!r} has {n:,} rows, expected at least {min_rows:,}. "
                    "Refusing to install a likely-truncated download."
                )
            print(f"  {table:20} {n:>12,}")
    finally:
        con.close()


def download(url: str, tmp: Path) -> None:
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = 100 * done / total
                    print(f"\r  downloading… {done/1e6:,.0f}/{total/1e6:,.0f} MB "
                          f"({pct:.0f}%)", end="", flush=True)
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=URL)
    ap.add_argument("--force", action="store_true",
                    help="re-download even if a valid file is already present")
    args = ap.parse_args()

    if DEST.exists() and not args.force:
        print(f"{DEST.name} already present. Use --force to refresh.")
        return 0

    # Land to a temp path, validate, THEN swap. Never clobber good data with a
    # failed fetch.
    tmp = DEST.with_suffix(".duckdb.tmp")
    print(f"fetching {args.url}")
    try:
        download(args.url, tmp)
        print("validating…")
        validate(tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        print(f"\nERROR: refresh failed, existing data left untouched: {exc}",
              file=sys.stderr)
        return 1

    shutil.move(str(tmp), str(DEST))
    print(f"OK -> {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
