# Football Scouting App — Build Spec

**Owner:** Dimitris Troulis
**Status:** v1 spec, ready to execute
**Goal:** A locally-run tool that surfaces young, improving footballers available for a realistic fee under ~€6m.

---

## 1. What this is and is not

**It is:** a local data pipeline plus a browsable UI that produces a ranked shortlist of undervalued players, with the ability to drill into any player and see why he scored the way he did.

**It is not:** a live scores app, a betting model, or a replacement for watching football. The output is a shortlist to *investigate*, not a verdict.

**Success criterion for v1:** the top 25 names it produces are plausible to a football watcher, and the backtest (§7) shows the model would have flagged players who subsequently rose in value.

---

## 2. Constraints that shape the design

### 2.1 The free-data landscape as of September 2026

In **January 2026 FBref lost its Opta licence** and removed all advanced statistics. The historical archive remains but no longer updates. Any tutorial, repo, or blog post about football data written before 2026 assumes FBref advanced stats exist. They do not. Do not build on them.

What remains free and current:

| Source | Provides | Coverage | Access |
|---|---|---|---|
| **transfermarkt-datasets** (`dcaribou`) | Market values + history, players, clubs, games, appearances, transfers, lineups, events | **14 domestic leagues** (see §2.1.1) + cups and European competitions | Prepared **DuckDB file**, refreshed weekly |
| **Understat** | xG, xA, npxG, shots, key passes, xGChain, xGBuildup — season and shot level | **Top 5 leagues + Russian Premier League only** | `soccerdata` Python package |
| **Club Elo** | Team strength ratings, continuously updated | All European clubs | `soccerdata` |
| **FBref** | Basic stats (goals, assists, minutes, cards), deep history | 100+ competitions | `soccerdata` — basic only |
| **SoFIFA** | FIFA/EA attribute ratings, potential ratings | Broad | `soccerdata` |

#### 2.1.1 What the Transfermarkt file actually contains

Verified 2026-09-05 against commit `154367d` (211 MB, 13 tables). Full schema dump in
`docs/real_schemas.txt`; the reconciliation write-up is `docs/phase0_reconciliation.md`.

| Table | Rows | | Table | Rows |
|---|---:|---|---|---:|
| `appearances` | 1,894,350 | | `games` | 88,958 |
| `game_lineups` | 3,179,016 | | `transfers` | 175,165 |
| `game_events` | 1,274,469 | | `club_games` | 177,916 |
| `player_valuations` | 656,301 | | `clubs` | 796 |
| `players` | 50,149 | | `countries` / `national_teams` | 124 each |
| | | | `competitions` | 65 |

`players` covers only the 14 leagues below, **not** all of Transfermarkt — 50k is the correct
order of magnitude, and an ingest floor above it will reject a valid download.

`competitions` lists **31 domestic leagues, but appearances exist for only 14.** The other 17
(Austria, Argentina, Brazil, MLS, Japan, Sweden, Norway, Poland, …) are present in the dimension
with zero appearance rows and cannot be scored. The 14 with data, stable across seasons 2022–2025:

```
GB1  ES1  IT1  L1   FR1        top five
PO1  NL1  TR1  BE1              tier 2
SC1  GR1  DK1  RU1  UKR1        tier 3 / other
```

All 14 are seeded in `seeds/league_tiers.csv` as of Task 2; `RU1` and `UKR1` were missing before
that and were being dropped silently.

There is **no `is_major_national_league` column** — an early version of `stg_tm__competitions`
assumed one and failed to build. The equivalent is `type = 'domestic_league'` **and**
`sub_type = 'first_tier'`. Other `type` values: `domestic_cup` (10), `other` (16),
`international_cup` (3), `national_team_competition` (5).

**Four competition_ids in `appearances` have no row in `competitions` at all** — `POCP`
(Taça da Liga), `CGB` (EFL Cup), `KLUB` (Club World Cup) and `UKRS` (Ukrainian Super Cup),
~14k appearances between them. All four are cups, so none belongs in the scoring sample, but the
gap is why the domestic-league filter in `int_player_season` is written **positively**
(`is_first_tier_domestic_league`) rather than as "not a cup" — a negative filter would let these
through. `tests/assert_appearance_competitions_known.sql` watches for new orphans at warn
severity.

Null rates that shape the scoring model: `contract_expiration_date` **37.0%**,
`market_value_in_eur` 17.2%, `current_club_domestic_competition_id` 6.0%, `date_of_birth` 0.1%.
`position` has no nulls but does carry a literal `'Missing'` value (586 players).

Type notes: `date_of_birth` and `contract_expiration_date` are `TIMESTAMP`, not `DATE`;
`last_season` and `clubs.club_id` are `VARCHAR` while `appearances.player_club_id` is `INTEGER`.
That id-type split costs nothing in Phase 1 (no model joins `clubs`) but must be cast in staging
before Phase 2 wires up team strength.

### 2.2 The coverage paradox

Bargains under €6m mostly live *outside* the top 5 leagues — Eredivisie, Belgium, Portugal, the Championship, Denmark, Austria, Croatia, Serbia, South America. Those are precisely the leagues with **no free advanced data**.

**Resolution:** build v1 on the top 5 leagues, where the data is complete and the model can be validated. There are genuinely plenty of sub-€6m targets there, especially in Ligue 1, Serie A's lower half, and La Liga's lower half. Once the model is proven, extend to secondary leagues using a reduced signal set (§8, Phase 5) — coarser, but still legitimate.

This is the opposite of the intuitive order, and it is deliberate: validate where you can measure, then extend to where you can't.

### 2.3 Market value is not a transfer fee

Transfermarkt values are crowd-sourced estimates. For young players with buzz, actual fees routinely land **1.5–2.5×** above TM value. Two implications:

- The price filter should target **TM value ≤ €4m** to realistically land a fee under €6m. Make the multiplier a configurable parameter, not a hard-coded number.
- TM values already incorporate public perception of performance. A model that regresses value on performance will largely recover the market's own opinion. Do not expect large, clean residuals — see §5 for why the design avoids that trap.

---

## 3. Architecture

Three layers, local-first, zero running cost.

```
Ingest (Python)  →  DuckDB  →  dbt models  →  Streamlit
```

**DuckDB** is the warehouse — a single file, no server, fast on this data volume, and it reads Parquet and remote CSV natively. **dbt-duckdb** gives you the staging/intermediate/marts discipline, tests, and lineage. **Streamlit** gives a shortlist table plus per-player drill-down for far less effort than a real front end.

### 3.1 Repo layout

```
football-scout/
├── CLAUDE.md                    # working agreement for Claude Code
├── SPEC.md                      # this file
├── README.md
├── pyproject.toml               # uv or poetry
├── .env.example
├── ingest/
│   ├── transfermarkt.py         # download + land the prepared DuckDB/CSVs
│   ├── understat.py             # soccerdata → parquet
│   ├── clubelo.py               # soccerdata → parquet
│   ├── sofifa.py                # soccerdata → parquet (Phase 4)
│   └── run.py                   # orchestrator, idempotent, incremental
├── data/
│   ├── raw/                     # parquet landing zone, gitignored
│   └── scout.duckdb             # the warehouse, gitignored
├── transform/                   # dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   ├── seeds/
│   └── tests/
├── scoring/
│   ├── config.yml               # all weights and thresholds live here
│   └── backtest.py
├── app/
│   ├── Home.py                  # shortlist
│   └── pages/1_Player.py        # drill-down
└── tests/
```

**Rule:** no scoring weight, age threshold, or price cap is hard-coded in SQL or Python. All of it lives in `scoring/config.yml` and `transform/seeds/`. You will tune these dozens of times.

---

## 4. Data model

### 4.1 Staging (`stg_*`) — one model per source table, renaming and typing only

As built in Phase 1 (five models — the names below are the real ones):

```
stg_tm__players            stg_tm__appearances       stg_tm__player_valuations
stg_tm__clubs              stg_tm__competitions
```

Phases 2+ add:

```
stg_tm__games              stg_tm__transfers
stg_understat__player_season
stg_clubelo__ratings
```

`stg_tm__clubs` and `stg_tm__competitions` are currently **leaf models** — built and tested, but
nothing downstream reads them yet. They earn their place in Phase 2 (team strength, explicit
competition-type filtering).

### 4.2 Intermediate (`int_*`) — the hard parts

| Model | Purpose |
|---|---|
| `int_player_identity` | **Entity resolution.** Match Transfermarkt players to Understat players. This is the single most annoying part of the project — budget real time for it. |
| `int_league_strength` | League coefficient derived from Club Elo: mean/median Elo of clubs per league per season, normalised to the strongest league = 1.0. |
| `int_team_strength` | Club Elo per club per season, used to adjust a player's output for the quality of the team around him. |
| `int_player_season` | One row per player per season: minutes, appearances, starts, goals, assists, cards, plus Understat metrics where matched. |
| `int_player_value_history` | Market value time series per player, with deltas, CAGR, and value at each season boundary. |
| `int_contract_status` | Months remaining on contract at a given as-of date. |

**Entity resolution approach** (`int_player_identity`):
1. Exact match on normalised name + club + season.
2. Fuzzy name match (rapidfuzz, token_set_ratio ≥ 90) constrained to same club + season.
3. Fuzzy name + birth year where club differs (mid-season transfers).
4. A `seeds/player_id_overrides.csv` for manual fixes.
5. A **dbt test that fails if match coverage for the top 5 leagues drops below 90%.** Coverage is the health metric for this layer; without the test it silently rots.

### 4.3 Marts

| Model | Grain | Purpose |
|---|---|---|
| `dim_player` | player | Current profile: name, DOB, age, position, sub-position, foot, height, nationality, current club, current value, contract expiry |
| `fct_player_season` | player × season | All performance and context metrics, league- and team-adjusted |
| `mart_player_scores` | player × as_of_date | Component scores and composite score, with every input retained so the UI can explain the ranking |
| `mart_shortlist` | player | Filtered, ranked output — what the app opens on |

**`mart_player_scores` must retain its inputs.** The drill-down UI exists to answer "why is he ranked 7th", and it cannot do that from a single composite number.

---

## 5. The scoring model

### 5.1 Design principle

Avoid the residual trap. A model that predicts market value from performance and flags negative residuals mostly rediscovers what the crowd already thinks, with extra noise. Instead, score two independent axes and filter on price:

```
Shortlist = players where price ≤ cap
            ranked by (Performance × Trajectory × Availability)
```

Each axis is interpretable on its own, which is what makes the output arguable rather than mystical — and being arguable is the point, because you'll be arguing with it.

### 5.2 Axis 1 — Performance (how good is he now)

Position-aware, computed per 90 minutes, then converted to a **percentile within position group and season**, then multiplied by the league strength coefficient.

**Attackers / wingers:** npxG/90, xA/90, shots/90, key passes/90, xGChain/90, goal contribution vs npxG+xA (finishing over/underperformance, treated as noise not skill), dribble volume.

**Midfielders:** xGBuildup/90, xGChain/90, key passes/90, xA/90, progressive involvement.

**Defenders:** with free data this is genuinely weak — Understat carries no defensive actions. Use minutes share, team defensive record adjusted for team Elo, and SoFIFA attributes as a stopgap. **Be honest in the UI that defender scoring is lower confidence than attacker scoring.** Do not let a pretty number hide a thin metric.

**Goalkeepers:** out of scope for v1. Say so rather than scoring them badly.

Two adjustments applied to every position:

- **League strength** — from `int_league_strength`. 15 goals in Ligue 1 ≠ 15 in the Championship.
- **Team quality** — from Club Elo. Good output in a weak side is a stronger signal than the same output in a strong one. This is where genuine bargains hide.

**Minutes threshold:** require ≥ 900 minutes in the reference season, or ≥ 600 with a strongly rising trend. Below that, per-90 rates are noise. Make it a config parameter and *display* the sample size in the UI so you can see when you're looking at 700 minutes.

### 5.3 Axis 2 — Trajectory (is he getting better)

| Signal | Rationale |
|---|---|
| Age | Peak is ~25–27. Reward 18–23, neutral 24–25, penalise 26+. Use a smooth curve, not buckets. |
| Minutes trend | Season-over-season minutes growth — the manager's own revealed opinion, and a very strong signal. |
| Output trend | Season-over-season change in the position's core per-90 metrics. |
| Value trend | Market value CAGR over 24 months. Rising value confirms; but note it also means you're no longer early. |
| Level progression | Has he moved up a league tier or into European competition? |

### 5.4 Axis 3 — Availability (can you actually get him)

This is where the real edge is, and it's cheap to compute from data you already have.

| Signal | Weight |
|---|---|
| **Contract months remaining** | Heavily weighted. Under 18 months = leverage. Under 12 = a discount the market is slow to price. |
| Squad role | Rotation players at big clubs are gettable; nailed-on starters are not. |
| Club financial pressure | Recently relegated, or a selling club by history — derive from `transfers`. |
| Value trajectory shape | Recently *fallen* value plus intact underlying performance is the classic buy-low. |

### 5.5 Composition

Do not build one opaque weighted sum and stop. Produce:
- Three component scores, each 0–100 and independently readable
- One composite, with weights in `config.yml`
- **Every input metric retained on the row**

Start deterministic — SQL and config, no ML. Only reach for a model once the deterministic version works and you understand its failure modes. If you can't explain why a player ranks where he does, the tool is useless for its actual purpose, which is starting a conversation about a player.

---

## 6. The UI

**Page 1 — Shortlist** (`app/Home.py`)
- Sidebar filters: position group, age range, max market value, min minutes, league, contract months remaining, season
- Main table: rank, name, age, club, league, market value, contract expiry, composite score, three component scores
- Sortable, exportable to CSV
- A one-line plain-English tag per player: *"21, rising minutes, 14 months left, outperforming a weak side"*

**Page 2 — Player drill-down** (`app/pages/1_Player.py`)
- Header: photo-less profile block — age, position, club, value, contract
- **Percentile bars** vs positional peers in the same price bracket and league tier — the peer group matters more than the metric
- **Market value history** line chart
- **Minutes and output trend** by season
- Score decomposition: what each axis contributed
- Comparable players: nearest neighbours on the performance vector

Percentiles against the right peer group are the whole game. A striker in the 80th percentile "among all strikers" is meaningless; "among strikers aged ≤23 valued under €6m in tier-2 leagues" is a scouting statement.

---

## 7. The backtest — build this, it is the highest-value component

`player_valuations` is a full historical time series. That means you can run the model **as of a past date** and check what happened next.

```
1. Rebuild all features using only data available as of 2024-01-01
2. Generate the shortlist as it would have looked then
3. Measure over the following 24 months:
   - median market value change of the shortlist vs a matched control
     (same age band, same price bracket, same league, not shortlisted)
   - proportion who transferred to a higher-tier league or club
   - hit rate: proportion whose value more than doubled
4. Repeat across several as-of dates (2022, 2023, 2024) to check stability
```

**Guard against leakage rigorously.** Every feature must be filtered to `as_of_date`. A single unfiltered join to current values will produce a spectacular and completely fake result. Write a dedicated test for this.

Almost no hobby project in this space does a backtest, which is exactly why almost none of them are trustworthy. It is what tells you whether you've built a scouting tool or an expensive random number generator — and it's what would make this a genuinely strong portfolio piece.

---

## 8. Build phases

| Phase | Deliverable | Rough effort |
|---|---|---|
| **0** | Download the Transfermarkt DuckDB, explore all 12 tables, document actual schemas in `README.md`. Confirm which leagues and seasons are usable. | One evening |
| **1** | `ingest/transfermarkt.py` + staging models + a naive shortlist from Transfermarkt alone (age, value, minutes, goal contribution, contract). Bare Streamlit table. **Ship something that runs.** | One weekend |
| **2** | Understat + Club Elo ingest, `int_player_identity` with coverage test, league and team strength adjustment, the real three-axis scoring model. | One weekend |
| **3** | Backtest harness, leakage tests, tune weights against backtest results. | One weekend |
| **4** | Player drill-down page, percentile bars, comparables, SoFIFA attributes. | One weekend |
| **5** | Extend to secondary leagues on the reduced signal set. Flag confidence level per player based on which sources matched. | Ongoing |

Phase 1 exists to get something on screen fast. Resist building the full model before anything renders — the naive shortlist will teach you more about the data than another week of design.

---

## 9. Known risks

| Risk | Mitigation |
|---|---|
| Scrapers break without warning | Prefer the prepared Transfermarkt dataset over live scraping. Pin `soccerdata`. Fail loudly with clear messages, never silently produce a partial refresh. |
| Entity resolution rot | Coverage test in dbt; fail the build below threshold. |
| Backtest leakage | Dedicated test asserting no feature references data after `as_of_date`. |
| Defender scoring is weak | Label confidence in the UI. Don't pretend. |
| Survivorship in the backtest | Include players who *left* the dataset (retired, dropped down) in the control group, not just survivors. |
| Overfitting to the backtest | Hold out one as-of date entirely and never tune against it. |
| TM value ≠ fee | Configurable fee multiplier; show both estimated fee and TM value. |
| Scraping terms of service | Rate-limit politely, cache aggressively, personal use only. Don't redistribute scraped data. |

---

## 10. Open questions for later

- Should the price bracket be a hard filter or part of the score? (Start hard, it's clearer.)
- Is SoFIFA "potential" rating a legitimate signal or circular hype? Test it in the backtest before trusting it.
- Positional versatility — worth a bonus? Clubs pay for it.
- Injury history from the Transfermarkt data as a risk discount.
- Do you want a "similar to player X" search as an entry point rather than filters?
