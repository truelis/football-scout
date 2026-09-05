# Phase 0 — Schema reconciliation against the real dataset

**Date:** 2026-09-05
**Upstream file:** `transfermarkt-datasets.duckdb`, 211 MB, commit `154367dfa6d6eb0b86332e332f9df0a080c7ddce`
**Schema dump:** `docs/real_schemas.txt`
**Status:** blockers 1–4 are **fixed**; `dbt build` is green (`PASS=50 ERROR=0 SKIP=0`).
Findings 5–8 are recorded, not acted on — they belong to Tasks 2 and 4.

The file is downloaded and **already in place** at `data/transfermarkt-datasets.duckdb`. It does not
need fetching again. `dbt deps` has been run and `dbt build` executed against it, so the failure list
below is what dbt actually reported, not an inference.

```
before:  Done. PASS=29 WARN=0 ERROR=2 SKIP=17 NO-OP=0 REUSED=0 TOTAL=48
after:   Done. PASS=50 WARN=0 ERROR=0 SKIP=0  NO-OP=0 REUSED=0 TOTAL=50
```

---

## Summary

The staging models held up better than expected. **Exactly one column does not exist.** Four things
block a clean build; two of them are environment, not schema, and none is in the scoring path.

| # | Severity | What | Blocks |
|---|---|---|---|
| 1 | **Blocker** | `ingest/transfermarkt.py` row floor for `players` rejects a good download | ingest |
| 2 | **Blocker** | `competitions.is_major_national_league` does not exist | `dbt build` |
| 3 | **Blocker** | `dim_player.age` range test fails on 104 retired players | `dbt build` (+17 skips) |
| 4 | **Blocker** | `DBT_PROFILES_DIR` points at `~/.dbt`, which had no `football_scout` entry | every documented command |
| 5 | Correctness | `max(strength_coef)` applies the *best* league's coefficient to combined output | no |
| 6 | Signal bias | 58% of the shortlist are newcomers, all pinned at `minutes_trend_score` 50.0 | no |
| 7 | Coverage | 14 leagues have appearances; the seed has 12. `RU1`, `UKR1` missing | no |
| 8 | Cosmetic | Type drift — `TIMESTAMP` dates, `VARCHAR` ids | no |

---

## 1. The ingest validator rejects a perfectly good file — Blocker

`ingest/transfermarkt.py` requires `players` ≥ 100,000 rows. The real table has **50,149**. The
download completed in full (211/211 MB) and every other table clears its floor comfortably, so this
is a wrong assumption in the guardrail, not a truncated fetch.

| Table | Required | Actual | |
|---|---:|---:|---|
| `players` | 100,000 | **50,149** | ✗ fails |
| `appearances` | 1,000,000 | 1,894,350 | ok |
| `player_valuations` | 100,000 | 656,301 | ok |
| `clubs` | 100 | 796 | ok |
| `competitions` | 10 | 65 | ok |

The fail-loud design is right and worth keeping — it is CLAUDE.md rule 4 and it did exactly what it
was built to do. Only the number is wrong: `players` is scoped to the 14 covered leagues, not all of
Transfermarkt, so ~50k is the correct order of magnitude. A floor of 40,000 still catches a genuinely
truncated download.

## 2. `competitions.is_major_national_league` does not exist — Blocker

The only true schema mismatch in the project.

```
Runtime Error in model stg_tm__competitions
  Binder Error: Referenced column "is_major_national_league" not found in FROM clause!
  Candidate bindings: "country_name", "domestic_league_code", "confederation", "name", "country_id"
```

The real `competitions` table has 11 columns and none is that:

```
competition_id  competition_code  name  sub_type  type  country_id
country_name    domestic_league_code   confederation   total_clubs   url
```

Upstream expresses the same idea through `type` and `sub_type`:

- `type = 'domestic_league'` and `sub_type = 'first_tier'` → 31 rows, all top-flight leagues
- other `type` values: `domestic_cup` (10), `other` (16), `international_cup` (3),
  `national_team_competition` (5)

So the replacement is `type = 'domestic_league' and sub_type = 'first_tier'` — a cleaner filter than
the boolean was.

**This is contained.** `stg_tm__competitions` is a leaf: nothing in intermediate, marts, tests or the
app references it (`stg_tm__clubs` is a leaf too). Fixing the column list is the whole fix.

## 3. `dim_player.age` range test fails on 104 rows — Blocker

`_marts.yml` asserts `age` between 14 and 50 on `dim_player`, which is the **entire 50,149-player
universe including retirees**, not the scored population.

```
FAIL 104 dbt_utils_accepted_range_dim_player_age__50__14
```

- 104 players are over 50 — oldest Patrick Deman at 58.1 (b. 1968). Real historical players, not bad data.
- A further 49 have a null `date_of_birth` (0.1%). These **pass silently** — `accepted_range` does not
  catch nulls — so the test is simultaneously too strict and too loose.

**None of the 153 reach the scored marts**; `max_age: 23` removes them. The test asserts a
scouting-population property against a historical archive.

**This failure is why 17 nodes were skipped.** `dbt build` skips descendants of a failed test, so
`fct_player_season`, `mart_player_scores` and `mart_shortlist` never built. Fixing the test scope
unblocks the whole downstream half of the DAG.

## 4. dbt cannot find the profile — Blocker

```
$ cd transform && uv run dbt build
Runtime Error  Could not find profile named 'football_scout'
```

The documented command in `CLAUDE.md`, `README.md` and `PHASE1.md` fails.

**Cause:** `DBT_PROFILES_DIR` is already set to `/Users/dimitristroulis/.dbt` in the shell, and it
takes precedence over the project directory — so dbt never looks at `transform/profiles.yml`.
Verified: `env -u DBT_PROFILES_DIR dbt parse` resolves the profile fine, so dbt 1.12's project-dir
fallback is intact and this is purely the env var.

That env var is not stray — `~/.dbt/profiles.yml` is the workspace's central profile store, holding
`default`, `dbtlearn`, `dbtlearn2`, `lessons` and `answers` for the sibling dbt projects.
`football_scout` was simply missing from it.

**Fixed** by adding a `football_scout:` block to `~/.dbt/profiles.yml` (absolute paths, so it
resolves from any CWD). This matches the existing convention rather than fighting it, and leaves
`cd transform && uv run dbt build` working verbatim as documented — no flags, no env changes, no
risk to the sibling projects (a global `DBT_PROFILES_DIR` repointed at this repo would have broken
all of them). `transform/profiles.yml` is kept as the portable reference copy; the duplication and
its failure mode are documented in `CLAUDE.md`.

### Environment note — Google Drive `Icon\r` files

`dbt deps` crashed before any of the above with:

```
NotADirectoryError: [Errno 20] Not a directory:
  .venv/lib/python3.13/site-packages/jsonschema_specifications/schemas/Icon\r
```

Google Drive scatters macOS custom-icon files (`Icon` + CR) through synced folders; 430 of them had
landed in `.venv`, and `jsonschema` chokes iterating a directory containing one. Removed with
`find .venv -name 'Icon?' -delete`. **This will recur on every sync** — worth adding `.venv/` to
Drive's ignore list or moving the venv outside the Drive folder.

## 5. `max(strength_coef)` applies the best league's coefficient — correctness, not a build failure

In `mart_player_scores`'s `agg` CTE, a player with rows in more than one competition gets his
**combined** output multiplied by `max(strength_coef)` — the strongest league he appeared in — even
when most of his minutes were played in the weaker one.

Real rows from the build:

```
Omri Gandelman (id 780548)
    BE1  Pro League   tier 2  coef 0.68   min 1428   ga 8      <- most of his minutes
    IT1  Serie A      tier 1  coef 0.93   min  979   ga 3
 -> scored: min=2407  ga=11  ga_per90=0.411  ga_per90_adj=0.383  performance=88.6
```

The minutes-weighted coefficient is 0.78, so the correct adjusted rate is ~0.321. He is credited with
0.383 — **19% inflated** — and lands at performance 88.6. Same pattern for Kenneth Taylor (Eredivisie
1280′ + Serie A 1402′, perf 87.5) and Amir Murillo (Süper Lig 957′ + Ligue 1 988′, perf 85.5).

Scale: 227 players have multi-competition 2025 rows, 177 reach `mart_player_scores`, **89 span
different tiers**, and 7 reach the shortlist.

`max(position_group)` and `max(tier)` in the same CTE are harmless — `position_group` is constant per
player (it comes from `dim_player` via the join) and `max(tier)` is not used in the output.

Separately, `mart_player_scores` **displays** `league_name`/`tier` from `dim_player` (the player's
*current club*) while **scoring** on `fct_player_season` (the league he *played in*). 60 scored
players have a null displayed tier and 4 reach the shortlist with `league_name = NULL`. Gandelman
displays as Serie A despite most minutes in Belgium.

PHASE1.md Task 4 flags multi-club seasons as an open question — this is the specific mechanism.

## 6. Newcomers are 58% of the shortlist and structurally penalised — signal bias

PHASE1.md Task 4 predicted `minutes_trend_score` would misbehave with no prior season. The magnitude
is larger than "a default that matters":

| group | n | `minutes_trend_score` | composite avg |
|---|---:|---|---:|
| newcomer (no 2024 row) | **125 (57.9%)** | 50.0 for every one — min 50.0, max 50.0 | 48.3 |
| returning | 91 | avg 89.1, range 35.5–100.0 | 54.4 |

Every newcomer gets exactly the 0.5 default, worth 30% of the trajectory axis, so they sit ~39 points
below returning players on that component. They are 24.1% of scored players but 57.9% of the shortlist
(the `max_age: 23` filter selects for them) — so the default governs the majority of the output.

There is a second-order effect in the eligibility filter. The "or trending" branch is:

```sql
minutes_played >= 600 and minutes_played > coalesce(prev_minutes, 0)
```

For a newcomer `coalesce(prev_minutes, 0)` makes that `minutes_played > 0` — always true. So the
600-minute floor is the *only* gate for newcomers, and 48 of them enter on 600–899 minutes without any
trend evidence, against 24 returning players who cleared a genuine rise. Plausibly the intent (youth
graduates are the target profile), but it is not what "or trending" implies.

## 7. League coverage — 14 leagues have appearances, the seed has 12

`competitions` lists 31 domestic leagues, but **appearances exist for only 14**. The other 17 (A1,
ARG1, BRA1, MLS1, JAP1, SE1, NO1, PL1, …) carry zero appearance rows and cannot be scored regardless
of the seed.

Season 2025 volume, against `seeds/league_tiers.csv`:

| in seed | competition | apps | players |
|---|---|---:|---:|
| ✓ | ES1 LaLiga | 11,953 | 600 |
| ✓ | IT1 Serie A | 11,926 | 585 |
| ✓ | GB1 Premier League | 11,492 | 537 |
| ✓ | L1 Bundesliga | 9,552 | 497 |
| ✓ | PO1 Liga Portugal | 9,493 | 560 |
| ✓ | NL1 Eredivisie | 9,448 | 530 |
| ✓ | TR1 Süper Lig | 9,434 | 568 |
| ✓ | FR1 Ligue 1 | 9,379 | 547 |
| **✗** | **UKR1 Ukraine Premier Liga** | **7,349** | **498** |
| ✓ | BE1 Pro League | 7,332 | 454 |
| **✗** | **RU1 Russian Premier Liga** | **7,322** | **470** |
| ✓ | SC1 Scottish Premiership | 6,113 | 369 |
| ✓ | GR1 Super League Greece | 5,660 | 432 |
| ✓ | DK1 Danish Superliga | 4,112 | 333 |

Every seeded id exists upstream with real volume — no dead entries. Two live leagues are unseeded and
therefore silently dropped by `fct_player_season`'s `where lt.competition_id is not null`. Task 2 work,
recorded here because it changes what Task 3 will see.

**The league set is stable across seasons.** The same 14 appear in 2022, 2023, 2024 and 2025 at
consistent volume, so `prev_season` is not missing whole leagues and the newcomer effect in §6 is a
genuine player-level property rather than a coverage artefact.

Also for Task 2: cups and European competitions are currently excluded only *implicitly*, because the
seed happens to contain domestic leagues only. PHASE1.md wants that filter explicit in `int_player_season`.

### Season macro caveat

`season_of()` (Jul–Jun) agrees with upstream `games.season` on **97.8%** of 88,958 games. Disagreements
concentrate in calendar-year leagues — Brazil (264), MLS (219), Norway (146), Sweden (142), Japan (138)
— where a Jul–Jun boundary splits one campaign across two seasons. **None of those leagues have
appearances**, so this is harmless today; it becomes real in Phase 5 if coverage extends to them.
Residual disagreements in IT1 (98), GB1 (66), ES1 (57) are fixtures rescheduled across the boundary.

## 8. Type drift — nothing breaks, worth knowing

| Column | Model assumes | Actual |
|---|---|---|
| `players.date_of_birth` | date | `TIMESTAMP` |
| `players.contract_expiration_date` | date | `TIMESTAMP` |
| `players.last_season` | integer-ish | `VARCHAR` |
| `players.current_club_id` | integer | `VARCHAR` |
| `clubs.club_id` | integer | `VARCHAR` |
| `appearances.player_club_id` | — | `INTEGER` |
| `player_valuations.current_club_id` | — | `INTEGER` |

DuckDB handles `datediff` on `TIMESTAMP` without complaint, so age and contract maths are correct
today. The id-type inconsistency (`clubs.club_id` VARCHAR vs `appearances.player_club_id` INTEGER)
costs nothing now because **no model joins to `clubs`** — but it will bite in Phase 2 when team
strength needs that join. Casting in staging is the cheap fix.

### Data quality to carry into Task 3

| Column | Null rate | Consequence |
|---|---|---|
| `contract_expiration_date` | **37.0%** | Availability axis defaults to 0.40 for over a third of players |
| `market_value_in_eur` | 17.2% | Silently dropped by the price filter (`NULL <= 4m` is NULL) |
| `current_club_domestic_competition_id` | 6.0% | Null league on the shortlist |
| `date_of_birth` | 0.1% | 49 players, null age |

`players.position` has no nulls but does carry a literal **`'Missing'`** value (586 players). The
goalkeeper exclusion is `position_group != 'Goalkeeper'`, so `'Missing'` passes through; none currently
clear the minutes threshold, but the guard is narrower than intended.

---

## What the pipeline produces

`dbt build` stopped at the `dim_player` test, so the marts did not materialise. Simulating the full
chain with current `vars` (staging → marts, ref/var rendered by hand) predicts:

```
stg_tm__players              50,149     int_contract_status         50,149
stg_tm__appearances       1,894,350     int_player_season          193,537
stg_tm__player_valuations   656,301     int_player_value_history    41,528
stg_tm__clubs                   796     dim_player                  50,149
stg_tm__competitions          FAIL      fct_player_season           81,326
                                        fct_player_valuations      656,301
                                        mart_player_scores           3,478
                                        mart_shortlist                 216
```

**216 shortlisted players** — inside PHASE1.md's "hundreds, not 5 or 50,000". Every test passes bar
`dim_player.age`. Composite scores spread 24.1 / 41.7 / 50.6 / 60.5 / 84.9 (min/p25/median/p75/max,
sd 12.4) — not degenerate.

Two things the Task 3 read should expect:

- **The shortlist is a tier-2/3 list.** Eredivisie 42, Pro League 39, Scottish 31, Danish 30, Liga
  Portugal 28 — against 1 Premier League and 3 Ligue 1. That is the €4m cap doing its job, but it
  means the placeholder `strength_coef` values carry almost the whole ranking, and `_seeds.yml`
  already warns they are guesses.
- **Availability is coarse, as predicted.** 93 players at 25.0 and 67 at 45.0 — 74% in two buckets,
  plus 16 at 40.0 (the unknown-contract default).

---

## Recommended order

Task 1 close-out — **done**:

- [x] Lowered the `players` floor in `ingest/transfermarkt.py` to 40,000, and every other floor to
      roughly half the observed count, with the reasoning in a comment.
- [x] Rewrote `stg_tm__competitions` against the real column list, exposing
      `is_first_tier_domestic_league` derived from `type` + `sub_type` (31 of 65 rows true).
- [x] Moved the age ceiling off `dim_player` onto `mart_player_scores`; `dim_player` keeps a floor
      only, since a ceiling there rots as `as_of_date` advances.
- [x] Added `football_scout:` to `~/.dbt/profiles.yml`; documented the duplication in `CLAUDE.md`.
- [x] `dbt build` green: **PASS=50, ERROR=0, SKIP=0**. `mart_shortlist` = 216 rows, matching the
      simulation exactly. **Task 1 closed.**
- [x] `SPEC.md` updated — new §2.1.1 with the real table inventory, the 14-league reality, the
      `type`/`sub_type` replacement, null rates and type notes; §4.1 corrected (it listed
      `stg_tm__valuations`, `stg_tm__games` and `stg_tm__transfers`, none of which exist, and omitted
      `stg_tm__competitions`).

Deferred, recorded not acted on: §5 (minutes-weight the coefficient) and §6 (newcomer default) are
Task 4; §7 (`RU1`/`UKR1`, explicit domestic-league filter) is Task 2.

Also minor: dbt emits 8 `MissingArgumentsPropertyInGenericTestDeprecation` warnings — generic test
args in the `.yml` files should nest under `arguments:`. Cosmetic in 1.12, will break eventually.
