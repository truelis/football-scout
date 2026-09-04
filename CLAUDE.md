# CLAUDE.md — football-scout

Working agreement for Claude Code on this repo. Read `SPEC.md` before doing anything substantive.

## What this project is

A local football scouting tool. It ingests free football data into DuckDB, transforms it with dbt, scores players on performance / trajectory / availability, and serves a ranked shortlist of under-€6m targets through Streamlit, with per-player drill-down.

Personal project, runs on one laptop, no cloud, no server, no auth.

## Stack — do not substitute without asking

| Layer | Tool | Why |
|---|---|---|
| Warehouse | **DuckDB** | Single file, no server, reads Parquet and remote CSV natively |
| Transform | **dbt-core + dbt-duckdb** | The owner is an analytics engineer; this is deliberate, not incidental |
| Ingest | **Python + soccerdata + httpx** | `soccerdata` wraps Understat, Club Elo, FBref, SoFIFA |
| UI | **Streamlit** | Fastest path to a filterable table plus drill-down |
| Charts | **Plotly** | Interactive, works well in Streamlit |
| Env | **uv** | Fast, lockfile-based |
| Fuzzy matching | **rapidfuzz** | Entity resolution |

No Postgres, no Docker, no Airflow, no cloud warehouse, no web framework. If a task seems to need one, stop and ask.

## Hard rules

1. **Never hard-code scoring weights, thresholds, age curves, or price caps in SQL or Python.** They live in `transform/dbt_project.yml` under `vars:` (dbt's idiomatic home for tunables) and in `transform/seeds/` for per-league tables. `scoring/config.yml` covers app and backtest settings only. They will be tuned dozens of times.
2. **Every model in `marts/` retains its input metrics**, not just the composite score. The UI must be able to explain a ranking.
3. **Backtest features must be filtered to `as_of_date`.** Any join to current market values inside backtest code is a bug, however tempting. Write the leakage test before the backtest.
4. **Ingest is idempotent and incremental.** Re-running must never duplicate rows or partially clobber a good dataset on a failed fetch. Land to a temp path, validate, then swap.
5. **Fail loudly.** A scraper returning zero rows must raise, not silently write an empty parquet and let dbt build a shortlist from nothing.
6. **No FBref advanced stats.** They were removed in January 2026. If you find code or docs referencing xG from FBref, they are stale. Understat is the free xG source, and it covers the top 5 leagues plus Russia only.
7. **Rate-limit and cache all scraping.** Personal use. Never redistribute scraped data.
8. `data/` is gitignored. Never commit the DuckDB file or raw parquet.

## dbt conventions

- Layers: `staging/` → `intermediate/` → `marts/`. No skipping layers, no mart reading raw.
- Naming: `stg_<source>__<entity>`, `int_<concept>`, `dim_*` / `fct_* `/ `mart_*`
- Staging models rename and cast only. No business logic.
- Every model gets a `.yml` entry with a description and at least a uniqueness and not-null test on its key.
- Materialisation: **staging as tables**, intermediate and marts as tables. Staging reads an ATTACHED read-only database, so views over it break for consumers that haven't attached `tm` - including the Streamlit app. Materialising keeps `data/scout.duckdb` self-contained. This is a deliberate deviation from convention.
- **The app reads marts only, never staging or intermediate.**
- Use `ref()` everywhere; `source()` only in staging.

## Testing expectations

- `int_player_identity` must have a coverage test that **fails the build** if top-5-league Transfermarkt↔Understat match rate drops below 90%.
- Backtest code has a leakage test asserting no feature references data after `as_of_date`.
- Per-90 metrics have a minutes-threshold test — no rates computed on trivial samples.
- Run `dbt build` (not just `dbt run`) before declaring a phase complete.

## Working style

- **Build in the phases from `SPEC.md` §8, in order.** Phase 1 must render something on screen before Phase 2 starts. Do not build the full scoring model before anything is visible.
- Small commits, one logical change each.
- When a data source's real schema differs from what `SPEC.md` assumes, **update `SPEC.md`** in the same commit. The spec is a living document, not a historical artefact.
- Before adding a dependency, ask.
- **Percentiles partition by position group, never also by tier** - partitioning by tier cancels out the league-strength coefficient entirely.
- **Goalkeepers are excluded from scoring**, not ranked badly. There are no goalkeeping metrics in the free data.
- When something can't be measured well with free data (defensive actions, goalkeepers), say so in the code and surface it in the UI. Do not paper over a weak metric with a confident-looking number.

## Domain notes that will save you time

- **Transfermarkt market value ≠ transfer fee.** Fees for young prospects run roughly 1.5–2.5× TM value. The fee multiplier is a config parameter.
- **Contract expiry is one of the strongest signals in the dataset** and is nearly free to compute. Under 18 months remaining materially changes what a player costs.
- **Team quality adjustment matters more than it sounds.** Good output in a weak side is where bargains actually are; the same output in a strong side is usually already priced.
- **Percentiles are only meaningful against the right peer group** — position, age band, price bracket, league tier. Percentiles against "all players" are decorative.
- Finishing over/underperformance vs npxG is mostly noise over a single season. Treat it as noise, not skill.

## Commands

```bash
uv sync                                  # install
uv run python ingest/run.py              # refresh raw data
cd transform && uv run dbt build         # transform + test
uv run streamlit run app/Home.py         # launch the UI
uv run python scoring/backtest.py --as-of 2024-01-01
```
