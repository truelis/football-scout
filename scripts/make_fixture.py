"""Generate a synthetic transfermarkt-datasets.duckdb using the REAL schemas.

Lets you build and test the whole pipeline without downloading the full dataset,
and serves as the CI fixture. Schemas mirror the curated models in
dcaribou/transfermarkt-datasets exactly. Swap in the real file for real results.
"""
import random
from datetime import date, timedelta
import duckdb
import pandas as pd

random.seed(7)
OUT = "data/transfermarkt-datasets.duckdb"
TODAY = date(2026, 9, 4)

LEAGUES = {
    "GB1": ("Premier League", "England"), "ES1": ("LaLiga", "Spain"),
    "L1": ("Bundesliga", "Germany"), "IT1": ("Serie A", "Italy"),
    "FR1": ("Ligue 1", "France"), "NL1": ("Eredivisie", "Netherlands"),
    "PO1": ("Liga Portugal", "Portugal"), "BE1": ("Pro League", "Belgium"),
    "GR1": ("Super League", "Greece"), "DK1": ("Superliga", "Denmark"),
    "TR1": ("Super Lig", "Turkiye"), "SC1": ("Premiership", "Scotland"),
}
POS = {"Attack": ["Centre-Forward", "Left Winger", "Right Winger"],
       "Midfield": ["Central Midfield", "Attacking Midfield", "Defensive Midfield"],
       "Defender": ["Centre-Back", "Left-Back", "Right-Back"],
       "Goalkeeper": ["Goalkeeper"]}

con = duckdb.connect(OUT)
con.execute("""CREATE OR REPLACE TABLE competitions(
 competition_id VARCHAR, competition_code VARCHAR, name VARCHAR, sub_type VARCHAR,
 type VARCHAR, country_id INTEGER, country_name VARCHAR, domestic_league_code VARCHAR,
 confederation VARCHAR, url VARCHAR, is_major_national_league BOOLEAN)""")
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

comps = [[cid, cid.lower(), nm, "first_tier", "domestic_league", i, ctry, cid,
          "europa", f"https://x/{cid}", True]
         for i, (cid, (nm, ctry)) in enumerate(LEAGUES.items())]

clubs, clubs_rows, cid_seq = [], [], 1
for lg in LEAGUES:
    for k in range(12):
        nm = f"{lg} Club {k}"
        clubs.append((cid_seq, lg, nm))
        clubs_rows.append([cid_seq, f"c{cid_seq}", nm, lg, random.uniform(5e6, 4e8),
                           25, 25.0, 10, 40.0, 2, "Stadium", 30000, "+0", "Coach",
                           2025, f"https://x/c{cid_seq}"])
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
        players.append([pid, "F", f"L{pid}", f"Player {pid}", 2025, club_id, f"p{pid}",
                        "X", "Y", "X", dob, random.choice(POS[pos]), pos,
                        random.choice(["right", "left", "both"]), 180,
                        TODAY + timedelta(days=random.choice([120,240,300,400,700,1100])),
                        "Agent", None, f"https://x/p{pid}", lg, club_name, base, base*1.2])
        for qi in range(12, -1, -1):
            d = TODAY - timedelta(days=qi * 90)
            drift = 1 + (q - 0.45) * 0.06 * (12 - qi)
            vals.append([pid, d, round(base * max(0.25, drift), -3), club_name, club_id, lg])
        for so, ss in enumerate([date(2023,8,1), date(2024,8,1), date(2025,8,1)]):
            n = min(int(random.triangular(0, 34, 10 + q*20 + so*3)), 34)
            for g in range(n):
                gd = ss + timedelta(days=g*8)
                if gd > TODAY: break
                apps.append([f"{pid}_{so}_{g}", so*10000+g, pid, club_id, club_id, gd,
                             f"Player {pid}", lg, random.randint(0,1), 0,
                             1 if random.random() < q*0.35 else 0,
                             1 if random.random() < q*0.25 else 0,
                             random.choice([90,90,75,60,20,8])])

COLS = {t: [d[0] for d in con.execute(f"DESCRIBE {t}").fetchall()]
        for t in ["competitions", "clubs", "players", "player_valuations", "appearances"]}
for tbl, rows in [("competitions", comps), ("clubs", clubs_rows), ("players", players),
                  ("player_valuations", vals), ("appearances", apps)]:
    df = pd.DataFrame(rows, columns=COLS[tbl])  # noqa: F841 - referenced by DuckDB
    con.execute(f"INSERT INTO {tbl} SELECT * FROM df")
    print(f"{tbl:20} {len(rows):>8,}")
con.close()
print(f"fixture written: {OUT}")
