"""Run the model as of a past date and check what actually happened next.

This is the part of the project that decides whether it is a scouting tool or an
expensive random number generator. Almost no hobby project in this space does it,
which is exactly why almost none of them are trustworthy (SPEC 7).

The question, in the Panathinaikos framing: PAO spent EUR 30.7m on 11 signings in
25/26 and 20.5m on 8 in 24/25, and have not won the league since 2010. Rebuilt as
of a past date, would this model's shortlist have done better than what they
actually bought?

HOW IT WORKS
    1. Rebuild the whole warehouse at as_of_date into a SEPARATE DuckDB file,
       using dbt's `backtest` target. Every feature is bounded by that date -
       three leaks had to be closed before this was true, see
       tests/assert_market_value_is_as_of.sql.
    2. Snapshot the shortlist as it would have looked then.
    3. Score what happened over the following N months using the FULL current
       data, which is the only place the future may legitimately be read.
    4. Compare against a matched control: same age band, price bracket and
       league, not shortlisted.
    5. Compare against what Panathinaikos actually signed in the same window.

WHAT THIS CANNOT MEASURE, AND WHY IT IS SAID OUT LOUD
    The Transfermarkt dataset has ONE contract expiry column and no history, so
    the availability axis cannot be rebuilt at a past date - a contract renewed
    in 2025 looks like it was always there. Availability is therefore reported
    separately and excluded from the headline comparison. Papering over it would
    make the backtest look stronger and mean nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TRANSFORM = ROOT / "transform"
LIVE_DB = ROOT / "data" / "scout.duckdb"
BACKTEST_DB = ROOT / "data" / "backtest.duckdb"
TM_DB = ROOT / "data" / "transfermarkt-datasets.duckdb"
OUT = ROOT / "docs" / "backtest"

PANATHINAIKOS_CLUB_ID = 265

# as_of date -> the season the model scores on. A January as_of sits mid-season,
# so the reference season is the campaign that started the previous summer.
AS_OF_SEASONS = {
    "2023-01-01": 2022,
    "2024-01-01": 2023,
    "2025-01-01": 2024,
}

# Never tuned against. SPEC 9 lists overfitting to the backtest as a named risk,
# and the only real defence is a date you agree in advance not to look at while
# adjusting weights.
HOLDOUT = "2025-01-01"


@dataclass
class Result:
    as_of: str
    season: int
    horizon_months: int
    shortlist: pd.DataFrame = field(default_factory=pd.DataFrame)
    control: pd.DataFrame = field(default_factory=pd.DataFrame)
    pao: pd.DataFrame = field(default_factory=pd.DataFrame)


def run_dbt(as_of: str, season: int, quiet: bool = True) -> None:
    """Rebuild the warehouse at a past date, into the backtest target."""
    env = os.environ.copy()
    # The project's own profiles.yml must win. A stray DBT_PROFILES_DIR pointing
    # at ~/.dbt silently sends dbt to a different profile - it cost an hour once.
    env.pop("DBT_PROFILES_DIR", None)
    cmd = [
        "dbt",
        "build",
        "--target",
        "backtest",
        "--vars",
        json.dumps({"as_of_date": as_of, "reference_season": season}),
    ]
    print(f"  rebuilding warehouse as of {as_of} (season {season})…", flush=True)
    proc = subprocess.run(cmd, cwd=TRANSFORM, env=env, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = "\n".join(proc.stdout.splitlines()[-25:])
        raise RuntimeError(
            f"dbt build failed for as_of={as_of}. A failing test here is usually a "
            f"LEAK, not a flake - read it before working around it.\n{tail}"
        )
    if not quiet:
        print(proc.stdout)


def snapshot_shortlist() -> pd.DataFrame:
    con = duckdb.connect(str(BACKTEST_DB), read_only=True)
    try:
        return con.execute("""
            SELECT player_id, player_name, age, position_group, league_name, tier,
                   current_market_value_eur AS value_at_as_of, minutes_played,
                   performance_score, trajectory_score, availability_score,
                   composite_score, confidence, has_xg
            FROM mart_shortlist
        """).df()
    finally:
        con.close()


def snapshot_control(shortlist: pd.DataFrame) -> pd.DataFrame:
    """Every scored player who did NOT make the shortlist.

    An earlier version matched on the shortlist's own envelope - age band, price
    cap, minutes floor, league - and produced a control of SEVENTEEN players
    against a shortlist of 284. That is not a coincidence or bad luck, it is
    structural: the shortlist filter admits 284 of the 301 in-bracket players, so
    "shortlist vs control" was measuring the minutes filter rather than the model.

    The pool is therefore left wide here, and the comparison is made
    value-matched downstream instead (see `value_matched`). That controls the
    confound that actually matters - cheap players have far more room to grow in
    PERCENTAGE terms - rather than the one that sounded tidiest.
    """
    con = duckdb.connect(str(BACKTEST_DB), read_only=True)
    try:
        scored = con.execute("""
            SELECT player_id, player_name, age, position_group, league_name, tier,
                   current_market_value_eur AS value_at_as_of, minutes_played
            FROM mart_player_scores
        """).df()
    finally:
        con.close()
    if shortlist.empty or scored.empty:
        return pd.DataFrame()

    pool = scored[~scored["player_id"].isin(shortlist["player_id"])].copy()
    # AGE-MATCH. Without this the control is every scored player of any age, and
    # a 30-year-old's value falls for reasons that have nothing to do with the
    # model. Left unmatched it showed -23% median against the shortlist's +69%,
    # which looks like skill and is mostly just age.
    #
    # The remaining pool is players who cleared the same age cap but failed on
    # price or minutes - genuinely "young players the model did not pick".
    return pool[pool["age"] <= shortlist["age"].max()]


def outcomes(players: pd.DataFrame, as_of: str, horizon: int) -> pd.DataFrame:
    """What happened to each player over the horizon, read from the FULL data.

    Survivorship matters here (SPEC 9): a player with no valuation left at the
    end has usually dropped down or out, which is a BAD outcome, not a missing
    one. Dropping those rows would quietly delete the model's worst calls, so
    their last known value is carried forward and they are flagged instead.
    """
    if players.empty:
        return players
    con = duckdb.connect(str(LIVE_DB), read_only=True)
    try:
        later = con.execute(f"""
            WITH horizon_end AS (
                SELECT DISTINCT ON (player_id)
                    player_id,
                    market_value_eur AS value_after,
                    valuation_date AS value_after_date
                FROM stg_tm__player_valuations
                WHERE valuation_date <= DATE '{as_of}' + INTERVAL {horizon} MONTH
                ORDER BY player_id, valuation_date DESC
            ),
            last_seen AS (
                SELECT player_id, MAX(valuation_date) AS last_valuation
                FROM stg_tm__player_valuations GROUP BY player_id
            )
            SELECT h.player_id, h.value_after, h.value_after_date, l.last_valuation
            FROM horizon_end h LEFT JOIN last_seen l USING (player_id)
        """).df()
    finally:
        con.close()

    df = players.merge(later, on="player_id", how="left")
    df["value_after"] = df["value_after"].fillna(df["value_at_as_of"])
    horizon_end = pd.Timestamp(as_of) + pd.DateOffset(months=horizon)
    # Stale = no new valuation inside the window. Transfermarkt stops revaluing
    # players who drop out of covered football, so this is a real signal.
    df["dropped_out"] = pd.to_datetime(df["value_after_date"]) < pd.Timestamp(as_of)
    df["value_growth"] = df["value_after"] / df["value_at_as_of"].replace(0, pd.NA) - 1
    df["value_delta_eur"] = df["value_after"] - df["value_at_as_of"]
    df["doubled"] = df["value_after"] >= 2 * df["value_at_as_of"]
    df["horizon_end"] = horizon_end
    # Percentage growth is not comparable across price brackets - a EUR 0.3m
    # player doubling gains 0.3m, a EUR 3m player doubling gains 3m, and the
    # cheap one is far likelier to do it. Every group comparison is made WITHIN
    # these buckets for that reason.
    df["value_bucket"] = pd.cut(
        df["value_at_as_of"],
        bins=[0, 5e5, 1e6, 2e6, 4e6, float("inf")],
        labels=["<0.5M", "0.5-1M", "1-2M", "2-4M", ">4M"],
    )
    return df


def pao_signings(as_of: str, horizon: int) -> pd.DataFrame:
    """What Panathinaikos actually bought in the same window, and how it went."""
    con = duckdb.connect(str(TM_DB), read_only=True)
    try:
        sign = con.execute(f"""
            SELECT t.player_id, t.player_name, t.transfer_date, t.transfer_season,
                   t.from_club_name, CAST(t.transfer_fee AS DOUBLE) AS transfer_fee,
                   CAST(t.market_value_in_eur AS DOUBLE) AS value_at_signing
            FROM transfers t
            WHERE t.to_club_id = {PANATHINAIKOS_CLUB_ID}
              AND t.transfer_date >  DATE '{as_of}'
              AND t.transfer_date <= DATE '{as_of}' + INTERVAL {horizon} MONTH
        """).df()
    finally:
        con.close()
    if sign.empty:
        return sign
    con = duckdb.connect(str(LIVE_DB), read_only=True)
    try:
        now = con.execute("""
            SELECT DISTINCT ON (player_id) player_id, market_value_eur AS value_now
            FROM stg_tm__player_valuations ORDER BY player_id, valuation_date DESC
        """).df()
    finally:
        con.close()
    df = sign.merge(now, on="player_id", how="left")
    df["value_at_as_of"] = df["value_at_signing"]
    df["value_after"] = df["value_now"]
    df["value_growth"] = df["value_now"] / df["value_at_signing"].replace(0, pd.NA) - 1
    df["value_delta_eur"] = df["value_now"] - df["value_at_signing"]
    df["doubled"] = df["value_now"] >= 2 * df["value_at_signing"]
    df["value_bucket"] = pd.cut(
        df["value_at_signing"],
        bins=[0, 5e5, 1e6, 2e6, 4e6, float("inf")],
        labels=["<0.5M", "0.5-1M", "1-2M", "2-4M", ">4M"],
    )
    return df


def rank_signal(shortlist: pd.DataFrame) -> pd.DataFrame:
    """THE headline test: does the composite score predict anything?

    Every player here cleared the same hard filters - same age cap, same price
    cap, same minutes rule - so the only thing separating them is the ranking.
    If the top quartile does not outperform the bottom, the score is decoration
    and no amount of comparison against outside groups will rescue it.

    This is the test that a value-bracket confound cannot fake, because the
    quartiles are compared within value buckets as well.
    """
    if shortlist.empty or shortlist["composite_score"].nunique() < 4:
        return pd.DataFrame()
    df = shortlist.copy()
    df["quartile"] = pd.qcut(
        df["composite_score"], 4, labels=["Q1 (worst)", "Q2", "Q3", "Q4 (best)"]
    )
    # Also within value buckets: Q4's median starting value is higher than Q1's,
    # so even a quartile comparison can be read by the price confound unless it
    # is held constant. If the score has signal, Q4 beats Q1 INSIDE a bucket too.
    bucketed = (
        df.groupby(["value_bucket", "quartile"], observed=True)
        .agg(n=("player_id", "size"), median_growth=("value_growth", "median"))
        .reset_index()
    )
    bucketed = bucketed[bucketed["n"] >= 5]
    if not bucketed.empty:
        print("\n  quartile WITHIN value bucket (the confound-proof version):")
        print(bucketed.to_string(index=False))

    out = (
        df.groupby("quartile", observed=True)
        .agg(
            n=("player_id", "size"),
            median_growth=("value_growth", "median"),
            median_delta_eur=("value_delta_eur", "median"),
            pct_doubled=("doubled", "mean"),
            median_value_at_as_of=("value_at_as_of", "median"),
        )
        .reset_index()
    )
    return out


def value_matched(groups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compare groups WITHIN price buckets, so the confound cannot do the work.

    Comparing a EUR 0.8m median shortlist against EUR 2.0m median signings on
    percentage growth would flatter the model badly - and that flattering number
    is exactly the "spectacular and completely fake result" SPEC 7 warns about.
    """
    rows = []
    for label, df in groups.items():
        if df.empty or "value_bucket" not in df:
            continue
        for bucket, g in df.groupby("value_bucket", observed=True):
            if len(g) < 5:  # too few to read anything into
                continue
            rows.append(
                {
                    "bucket": str(bucket),
                    "group": label,
                    "n": len(g),
                    "median_growth": float(g["value_growth"].median()),
                    "median_delta_eur": float(g["value_delta_eur"].median()),
                }
            )
    return pd.DataFrame(rows).sort_values(["bucket", "group"]) if rows else pd.DataFrame()


def summarise(label: str, df: pd.DataFrame) -> dict:
    if df.empty:
        return {"group": label, "n": 0}
    g = df["value_growth"].dropna()
    return {
        "group": label,
        "n": len(df),
        "median_growth": float(g.median()) if len(g) else None,
        "mean_growth": float(g.mean()) if len(g) else None,
        "pct_doubled": float(df["doubled"].mean()) if "doubled" in df else None,
        "pct_dropped_out": float(df["dropped_out"].mean()) if "dropped_out" in df else None,
        "median_value_at_as_of": float(df["value_at_as_of"].median())
        if "value_at_as_of" in df
        else None,
    }


def run_one(as_of: str, season: int, horizon: int, skip_build: bool) -> Result:
    print(f"\n=== as of {as_of} · season {season} · horizon {horizon}m ===")
    if not skip_build:
        run_dbt(as_of, season)
    r = Result(as_of=as_of, season=season, horizon_months=horizon)
    sl = snapshot_shortlist()
    ctrl = snapshot_control(sl)
    print(f"  shortlist {len(sl)} · matched control {len(ctrl)}")
    r.shortlist = outcomes(sl, as_of, horizon)
    r.control = outcomes(ctrl, as_of, horizon)
    r.pao = pao_signings(as_of, horizon)
    print(f"  Panathinaikos signings in window: {len(r.pao)}")
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--as-of",
        nargs="*",
        default=list(AS_OF_SEASONS),
        help="as-of dates to evaluate (default: all configured)",
    )
    ap.add_argument("--horizon-months", type=int, default=24)
    ap.add_argument(
        "--skip-build",
        action="store_true",
        help="reuse the existing backtest warehouse; only valid for a single date",
    )
    ap.add_argument(
        "--include-holdout",
        action="store_true",
        help=f"also evaluate {HOLDOUT}, the holdout date reserved from tuning",
    )
    args = ap.parse_args()

    dates = [d for d in args.as_of if d != HOLDOUT or args.include_holdout]
    if not dates:
        print("nothing to run", file=sys.stderr)
        return 1

    rows, results = [], []
    for d in dates:
        season = AS_OF_SEASONS.get(d)
        if season is None:
            print(f"unknown as-of date {d}; configure it in AS_OF_SEASONS", file=sys.stderr)
            return 1
        res = run_one(d, season, args.horizon_months, args.skip_build)
        results.append(res)
        for label, df in (("shortlist", res.shortlist), ("control_u23", res.control)):
            rows.append({"as_of": d, **summarise(label, df)})
        if not res.pao.empty:
            g = res.pao["value_growth"].dropna()
            rows.append(
                {
                    "as_of": d,
                    "group": "panathinaikos_signings",
                    "n": len(res.pao),
                    "median_growth": float(g.median()) if len(g) else None,
                    "mean_growth": float(g.mean()) if len(g) else None,
                    "total_fees_eur": float(res.pao["transfer_fee"].fillna(0).sum()),
                }
            )

    summary = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT / "summary.csv", index=False)
    for res in results:
        res.shortlist.to_csv(OUT / f"shortlist_{res.as_of}.csv", index=False)
        if not res.pao.empty:
            res.pao.to_csv(OUT / f"pao_signings_{res.as_of}.csv", index=False)

    print("\n" + "=" * 78)
    print("RAW GROUP MEDIANS - do not read these on their own, see below")
    print("=" * 78)
    print(summary.to_string(index=False))

    for res in results:
        rs = rank_signal(res.shortlist)
        if not rs.empty:
            print(
                f"\n--- {res.as_of}: DOES THE SCORE PREDICT? (quartiles of the "
                "same shortlist, same filters) ---"
            )
            print(rs.to_string(index=False))
            rs.to_csv(OUT / f"rank_signal_{res.as_of}.csv", index=False)

        vm = value_matched(
            {
                "shortlist": res.shortlist,
                "not_shortlisted_u23": res.control,
                "pao_signings": res.pao,
            }
        )
        if not vm.empty:
            print(
                f"\n--- {res.as_of}: VALUE-MATCHED (percentage growth is not "
                "comparable across price brackets) ---"
            )
            print(vm.to_string(index=False))
            vm.to_csv(OUT / f"value_matched_{res.as_of}.csv", index=False)
    print("=" * 78)
    print(f"\nwritten to {OUT}")
    print(
        "\nREAD THIS BEFORE BELIEVING ANY OF IT:\n"
        "  * The availability axis cannot be backtested - the dataset holds one\n"
        "    contract expiry per player with no history, so a renewal signed in\n"
        "    2025 looks like it was always there. Treat availability numbers as\n"
        "    contaminated, and the composite as partly so.\n"
        f"  * {HOLDOUT} is the holdout. Do not tune against it.\n"
        "  * Market value is the market's opinion, not ground truth. A shortlist\n"
        "    that beats its control on value growth has predicted the CROWD, which\n"
        "    is a weaker claim than predicting football."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
