"""Generate a synthetic dataset using the REAL schemas, for CI and local dev.

Lets the whole pipeline build and test without the 211MB download, which is what
makes CI possible at all - data/ is gitignored, so a runner has nothing.

Produces BOTH sources:
  * a transfermarkt-datasets.duckdb with the five tables staging reads
  * an understat_player_season.parquet

The Understat rows deliberately reuse the Transfermarkt player names for the
leagues Understat actually covers. Entity resolution then matches on them, and
assert_understat_match_coverage - which fails the build below 90% - has something
real to check. Random names would make that test fail on the fixture while
passing on live data, which is the worst of both.

  python scripts/make_fixture.py --out data/fixture.duckdb
"""

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

random.seed(7)
TODAY = date(2026, 9, 4)

ap = argparse.ArgumentParser(description=__doc__)
# NOT defaulted to the real filename. An earlier version wrote straight over
# data/transfermarkt-datasets.duckdb, so running it by accident destroyed the
# 211MB download and every later run silently used synthetic data.
ap.add_argument(
    "--out",
    default="data/fixture.duckdb",
    help="output DuckDB path (never the real dataset by default)",
)
ap.add_argument("--understat-out", default="data/raw/understat_player_season.parquet")
args = ap.parse_args()
OUT = args.out
Path(OUT).parent.mkdir(parents=True, exist_ok=True)
Path(args.understat_out).parent.mkdir(parents=True, exist_ok=True)

LEAGUES = {
    "GB1": ("Premier League", "England"),
    "ES1": ("LaLiga", "Spain"),
    "L1": ("Bundesliga", "Germany"),
    "IT1": ("Serie A", "Italy"),
    "FR1": ("Ligue 1", "France"),
    "NL1": ("Eredivisie", "Netherlands"),
    "PO1": ("Liga Portugal", "Portugal"),
    "BE1": ("Pro League", "Belgium"),
    "GR1": ("Super League", "Greece"),
    "DK1": ("Superliga", "Denmark"),
    "TR1": ("Super Lig", "Turkiye"),
    "SC1": ("Premiership", "Scotland"),
    "RU1": ("Premier Liga", "Russia"),
    "UKR1": ("Premier Liga", "Ukraine"),
}

# Exactly the leagues Understat publishes. Anything else has no xG by nature.
UNDERSTAT_LEAGUES = {
    "GB1": "ENG-Premier League",
    "ES1": "ESP-La Liga",
    "IT1": "ITA-Serie A",
    "L1": "GER-Bundesliga",
    "FR1": "FRA-Ligue 1",
    "RU1": "RUS-Premier League",
}
# Names must be ALPHABETIC and distinct. int_player_identity normalises with
# [^a-z\s] -> ' ', so "Player 1001" collapses to "player" and every fixture
# player becomes the same string: entity resolution then matched 6 of 1,728 and
# the coverage test failed on the fixture while passing on live data. Encoding the
# id in letters keeps each name unique after normalisation.
FIRST = [
    "Andreas",
    "Dimitrios",
    "Giorgos",
    "Kostas",
    "Nikos",
    "Petros",
    "Stavros",
    "Vasilis",
    "Yannis",
    "Thanasis",
    "Marios",
    "Christos",
]


def _alpha_id(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n, 26)
        out = chr(97 + r) + out
    return out.capitalize() or "A"


POS = {
    "Attack": ["Centre-Forward", "Left Winger", "Right Winger"],
    "Midfield": ["Central Midfield", "Attacking Midfield", "Defensive Midfield"],
    "Defender": ["Centre-Back", "Left-Back", "Right-Back"],
    "Goalkeeper": ["Goalkeeper"],
}

con = duckdb.connect(OUT)
con.execute("""CREATE OR REPLACE TABLE competitions(
 competition_id VARCHAR, competition_code VARCHAR, name VARCHAR, sub_type VARCHAR,
 type VARCHAR, country_id INTEGER, country_name VARCHAR, domestic_league_code VARCHAR,
 confederation VARCHAR, total_clubs INTEGER, url VARCHAR)""")
con.execute("""CREATE OR REPLACE TABLE clubs(
 club_id INTEGER, club_code VARCHAR, name VARCHAR, domestic_competition_id VARCHAR,
 total_market_value DOUBLE, squad_size INTEGER, average_age DOUBLE,
 foreigners_number INTEGER, foreigners_percentage DOUBLE, national_team_players INTEGER,
 stadium_name VARCHAR, stadium_seats INTEGER, net_transfer_record VARCHAR,
 coach_name VARCHAR, last_season INTEGER, url VARCHAR)""")
con.execute("""CREATE OR REPLACE TABLE players(
 player_id INTEGER, first_name VARCHAR, last_name VARCHAR, name VARCHAR,
 last_season INTEGER, current_club_id INTEGER, player_code VARCHAR,
 country_of_birth VARCHAR, city_of_birth VARCHAR, country_of_citizenship VARCHAR,
 date_of_birth DATE, sub_position VARCHAR, position VARCHAR, foot VARCHAR,
 height_in_cm INTEGER, contract_expiration_date DATE, agent_name VARCHAR,
 image_url VARCHAR, url VARCHAR, current_club_domestic_competition_id VARCHAR,
 current_club_name VARCHAR, market_value_in_eur DOUBLE, highest_market_value_in_eur DOUBLE)""")
con.execute("""CREATE OR REPLACE TABLE player_valuations(
 player_id INTEGER, date DATE, market_value_in_eur DOUBLE, current_club_name VARCHAR,
 current_club_id INTEGER, player_club_domestic_competition_id VARCHAR)""")
con.execute("""CREATE OR REPLACE TABLE appearances(
 appearance_id VARCHAR, game_id INTEGER, player_id INTEGER, player_club_id INTEGER,
 player_current_club_id INTEGER, date DATE, player_name VARCHAR, competition_id VARCHAR,
 yellow_cards INTEGER, red_cards INTEGER, goals INTEGER, assists INTEGER,
 minutes_played INTEGER)""")

comps = [
    [
        cid,
        cid.lower(),
        nm,
        "first_tier",
        "domestic_league",
        i,
        ctry,
        cid,
        "europa",
        12,
        f"https://x/{cid}",
    ]
    for i, (cid, (nm, ctry)) in enumerate(LEAGUES.items())
]

clubs, clubs_rows, cid_seq = [], [], 1
for lg in LEAGUES:
    for k in range(12):
        nm = f"{lg} Club {k}"
        clubs.append((cid_seq, lg, nm))
        clubs_rows.append(
            [
                cid_seq,
                f"c{cid_seq}",
                nm,
                lg,
                random.uniform(5e6, 4e8),
                25,
                25.0,
                10,
                40.0,
                2,
                "Stadium",
                30000,
                "+0",
                "Coach",
                2025,
                f"https://x/c{cid_seq}",
            ]
        )
        cid_seq += 1

players, vals, apps, pid = [], [], [], 1000
for club_id, lg, club_name in clubs:
    for _ in range(24):
        pid += 1
        age = random.uniform(17, 34)
        dob = TODAY - timedelta(days=int(age * 365.25))
        pos = random.choice(list(POS))
        q = random.random()
        base = max(25_000, (10 ** random.uniform(4.7, 7.6)) * (1.6 - abs(age - 25) / 18))
        full_name = f"{random.choice(FIRST)} {_alpha_id(pid)}"
        players.append(
            [
                pid,
                full_name.split()[0],
                full_name.split()[1],
                full_name,
                2025,
                club_id,
                f"p{pid}",
                "X",
                "Y",
                "X",
                dob,
                random.choice(POS[pos]),
                pos,
                random.choice(["right", "left", "both"]),
                180,
                TODAY + timedelta(days=random.choice([120, 240, 300, 400, 700, 1100])),
                "Agent",
                None,
                f"https://x/p{pid}",
                lg,
                club_name,
                base,
                base * 1.2,
            ]
        )
        for qi in range(12, -1, -1):
            d = TODAY - timedelta(days=qi * 90)
            drift = 1 + (q - 0.45) * 0.06 * (12 - qi)
            vals.append([pid, d, round(base * max(0.25, drift), -3), club_name, club_id, lg])
        for so, ss in enumerate([date(2023, 8, 1), date(2024, 8, 1), date(2025, 8, 1)]):
            n = min(int(random.triangular(0, 34, 10 + q * 20 + so * 3)), 34)
            for g in range(n):
                gd = ss + timedelta(days=g * 8)
                if gd > TODAY:
                    break
                apps.append(
                    [
                        f"{pid}_{so}_{g}",
                        so * 10000 + g,
                        pid,
                        club_id,
                        club_id,
                        gd,
                        full_name,
                        lg,
                        random.randint(0, 1),
                        0,
                        1 if random.random() < q * 0.35 else 0,
                        1 if random.random() < q * 0.25 else 0,
                        random.choice([90, 90, 75, 60, 20, 8]),
                    ]
                )

COLS = {
    t: [d[0] for d in con.execute(f"DESCRIBE {t}").fetchall()]
    for t in ["competitions", "clubs", "players", "player_valuations", "appearances"]
}
for tbl, rows in [
    ("competitions", comps),
    ("clubs", clubs_rows),
    ("players", players),
    ("player_valuations", vals),
    ("appearances", apps),
]:
    df = pd.DataFrame(rows, columns=COLS[tbl])
    con.execute(f"INSERT INTO {tbl} SELECT * FROM df")
    print(f"{tbl:20} {len(rows):>8,}")

# ---- Understat, for the leagues it actually covers -------------------------
# Names are reused from the Transfermarkt rows above so entity resolution has
# something to resolve; see the module docstring.
tm_players = pd.DataFrame(players, columns=COLS["players"])
us_rows = []
for comp_id, us_league in UNDERSTAT_LEAGUES.items():
    pool = tm_players[tm_players["current_club_domestic_competition_id"] == comp_id]
    for season_key, season_id in (("2425", 2024), ("2526", 2025)):
        for r in pool.itertuples():
            mins = random.randint(300, 3000)
            npxg = round(random.uniform(0, 0.55) * mins / 90, 3)
            xa = round(random.uniform(0, 0.35) * mins / 90, 3)
            us_rows.append(
                {
                    "league": us_league,
                    "season": season_key,
                    "team": r.current_club_name,
                    "player": r.name,
                    "league_id": comp_id,
                    "season_id": season_id,
                    "team_id": int(r.current_club_id),
                    "player_id": int(r.player_id),
                    "position": "F S",
                    "matches": max(1, mins // 75),
                    "minutes": mins,
                    "goals": int(npxg * random.uniform(0.6, 1.4)),
                    "xg": npxg + round(random.uniform(0, 0.4), 3),
                    "np_goals": int(npxg * random.uniform(0.6, 1.4)),
                    "np_xg": npxg,
                    "assists": int(xa * random.uniform(0.5, 1.5)),
                    "xa": xa,
                    "shots": random.randint(0, 90),
                    "key_passes": random.randint(0, 70),
                    "yellow_cards": random.randint(0, 8),
                    "red_cards": 0,
                    "xg_chain": round(npxg + xa + random.uniform(0, 3), 3),
                    "xg_buildup": round(random.uniform(0, 4), 3),
                }
            )
us = pd.DataFrame(us_rows)
us.to_parquet(args.understat_out, index=False)
print(f"{'understat (parquet)':20} {len(us):>8,}")

con.close()
print(f"fixture written: {OUT}")
print(f"understat written: {args.understat_out}")
