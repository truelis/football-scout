# Phase 1 — Work Order

**For:** Claude Code
**Read first:** `SPEC.md` (full design), `CLAUDE.md` (working agreement)

Phase 1 produces a working end-to-end pipeline on **Transfermarkt data only** — no xG yet. The goal is something on screen you can argue with, not a finished model.

---

## Status: scaffolding is built and tested

The repo already contains a **complete, running Phase 1 pipeline**. It was developed and verified against a synthetic fixture with the real schemas: `dbt build` passes 48/48 (7 models + tests), and the Streamlit app serves.

**It has never been run against the real dataset.** That is your first job.

### What exists

```
ingest/transfermarkt.py           download + validate the prepared DuckDB file
scripts/explore_schema.py         Phase 0: dump real schemas
scripts/make_fixture.py           synthetic fixture (real schemas, fake data)
transform/                        dbt project — 5 staging, 3 intermediate, 5 marts
  dbt_project.yml                 ALL tunable parameters live here under vars:
  profiles.yml                    attaches the TM file read-only as `tm`
  seeds/league_tiers.csv          PLACEHOLDER league coefficients
  tests/                          3 singular tests incl. the leakage guard
app/Home.py                       shortlist with filters
app/pages/1_Player.py             drill-down: score decomposition, value history
scoring/config.yml                app + backtest settings
```

### Design decisions already made (do not silently reverse)

1. **Staging is materialised as tables, not views.** Deliberate. Staging reads an *attached read-only* database, so views over it break for any consumer that hasn't attached `tm` — including the Streamlit app. Materialising makes `data/scout.duckdb` fully self-contained. This is a justified deviation from dbt convention; the reason is in a comment in `dbt_project.yml`.
2. **The app reads marts only, never staging.** `fct_player_valuations` exists specifically so the value chart doesn't reach into staging.
3. **All tunables live in `transform/dbt_project.yml` under `vars:`** — not in `scoring/config.yml`, which now covers only app and backtest settings. This differs from `CLAUDE.md`'s original wording; `vars:` is dbt's idiomatic home and keeping them in two places invites drift.
4. **Goalkeepers are excluded from scoring**, not ranked badly. Phase 1 has no goalkeeping metrics.
5. **Percentiles partition by position group only, not by tier.** Partitioning by tier as well would cancel out the league-strength coefficient entirely — a tier-3 player would only ever be compared to other tier-3 players. This was a real bug caught in testing; don't reintroduce it.

---

## Your tasks, in order

### Task 1 — Phase 0 reconciliation (do this before anything else)

```bash
uv sync
uv run python ingest/transfermarkt.py
uv run python scripts/explore_schema.py > docs/real_schemas.txt
```

Then **reconcile `docs/real_schemas.txt` against every staging model**. The staging models were written from the curated dbt models published in `dcaribou/transfermarkt-datasets`, which is accurate but evolves.

- Fix any column that doesn't match.
- **Update `SPEC.md` in the same commit** with what you found.
- If a column the scoring model depends on is missing (`contract_expiration_date`, `date_of_birth`, `market_value_in_eur`), stop and report rather than working around it.

**Acceptance:** `dbt build` completes against the real file with 0 errors.

### Task 2 — Competition coverage

The upstream project covers far more than the top 5 leagues. Its `competition_codes` list includes:

```
GB1 ES1 L1 IT1 FR1   NL1 PO1 BE1 TR1 GR1 DK1 SC1 RU1 UKR1
plus cups and European competitions (CL, EL, ECLQ, ...)
```

- Query `competitions` for what's actually present with usable volume.
- Extend `seeds/league_tiers.csv` to every domestic league you keep.
- **Domestic league appearances only** for scoring — cup and European games are a different sample and shouldn't be pooled in. Add the filter explicitly in `int_player_season` and note it.

**Acceptance:** `fct_player_season` covers every league in the seed; no competition in the fact table lacks a tier.

### Task 3 — Sanity-check the output, then report back

This is the real deliverable of Phase 1, and it is a judgement task, not a coding task.

```bash
uv run streamlit run app/Home.py
```

Produce a short written report in `docs/phase1_findings.md` covering:

- The top 25 attackers and top 25 midfielders, with their key numbers
- Which names are recognisable, and whether the unrecognisable ones look plausible
- Score distributions — is anything degenerate? (all clustered, all 100, one signal dominating)
- How many players survive the filters per league — if a league contributes zero, find out why
- Any player who looks obviously wrong, and your diagnosis of which signal caused it

**Do not tune the weights to make the list look better.** Report what it does first. Tuning without the Phase 3 backtest is just fitting to intuition, and it will feel like progress while being none.

### Task 4 — Fix what Task 3 exposes

Likely candidates, based on how the synthetic run behaved:

- **Availability score is close to binary.** Contract buckets are coarse; most players land in one. Consider a continuous decay on months remaining.
- **`minutes_trend_score` breaks for players with no prior season** — currently defaults to 0.5. Youth-team graduates and new signings are exactly the target profile, so this default matters more than it looks.
- **Defenders rank on attacking output.** They're flagged low confidence and ranked within position, but consider whether they belong in Phase 1 at all.
- **Multi-club seasons** — a player transferring mid-season has rows under two clubs. `mart_player_scores` sums them; confirm that's what you want.

---

## Definition of done

- [ ] `dbt build` passes against real data, 0 errors, all tests green
- [ ] `league_tiers.csv` covers every scored competition
- [ ] Shortlist returns a sane number of players (expect hundreds, not 5 or 50,000)
- [ ] Streamlit shortlist and drill-down both work against real data
- [ ] `docs/phase1_findings.md` written, with the top-25 lists and your read on them
- [ ] `SPEC.md` updated with real schemas and anything else that turned out differently
- [ ] Committed in logical steps

## Out of scope for Phase 1

Understat, xG, entity resolution, Club Elo, the backtest, percentile bars, comparables. Those are Phases 2–4. If Phase 1 tempts you into them, that's a sign it's working — write it down and stay put.
