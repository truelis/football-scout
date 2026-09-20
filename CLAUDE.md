# CLAUDE.md — football-scout

Working agreement for Claude Code on this repo. Read `SPEC.md` before doing anything substantive.

## What this project is

**A data engineering portfolio project with a real question behind it.**

Panathinaikos have not won the Greek league since 2010 — 16 years as of 2026 — and have done
nothing meaningful in Europe in that time. They are not poor: they spent **€30.7m on 11 signings in
25/26** and €20.5m the season before. The question this project answers is therefore not "who is
cheap" but: **could a disciplined, data-driven process have spent that money better?**

That question is checkable, which is the point. The backtest (SPEC §7) runs the model as of a past
date and compares what it would have recommended against what Panathinaikos actually signed.

It ingests free football data with Python, models it with dbt in DuckDB, orchestrates the refresh
with Airflow, ships through CI, and presents the result in Streamlit.

Two audiences, and both matter:
1. **The owner**, who supports the club and wants the answer.
2. **An interviewer**, who wants to see whether this person can build a pipeline, justify its
   design, and be honest about what it cannot do.

The second audience is why `docs/decisions/` exists and why the honest limitations in
`docs/phase1_findings.md` stay in the repo rather than being tidied away.

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
| Orchestration | **Airflow** (Docker Compose) | Weekly refresh: ingest → dbt build → test |
| CI/CD | **GitHub Actions** | Lint, dbt build against a fixture, tests, on every push |
| Code quality | **sqlfluff + ruff + pre-commit** | Enforced, not debated |

No Postgres, no cloud warehouse, no web framework. If a task seems to need one, stop and ask.

**On Airflow, be honest.** A weekly refresh on one laptop does not need it — `cron` would do. It is
here because (a) the owner wants to learn it and (b) orchestration is what a data engineering
portfolio is judged on. *Say this plainly in interviews*: "I know cron would suffice; I chose
Airflow for retries, backfill and dependency management across a multi-source pipeline, and because
it is what I wanted to learn." Pretending it was technically required is a worse answer than the
truth. See `docs/decisions/0005-airflow-over-cron.md`.

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

## Decision records

Every non-obvious choice gets an ADR in `docs/decisions/`, numbered, in the format the existing
ones use. Write it **when the decision is made**, not retrospectively at the end.

An ADR is worth writing when a reasonable engineer would ask "why did you do it that way?" — which
is exactly the interview question. Record what was rejected and why, not just what was chosen; the
rejected option is usually the more interesting half.

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
uv run python ingest/transfermarkt.py    # download the Transfermarkt DuckDB file
cd transform && uv run dbt deps          # once, installs dbt_utils
cd transform && uv run dbt build         # transform + test
uv run streamlit run app/Home.py         # launch the UI
uv run python scoring/backtest.py --as-of 2024-01-01
```

### dbt profile — lives in the repo, no per-laptop setup

`transform/profiles.yml` is the project's profile and the only copy. dbt resolves profiles in the
order `--profiles-dir` > `DBT_PROFILES_DIR` > **current directory** > `~/.dbt`, and because dbt is
run from `transform/`, the third rule finds it. A fresh clone needs no `~/.dbt` setup.

This only works with `DBT_PROFILES_DIR` **unset**. It used to be exported from `~/.zshrc`, which
silently overrode the repo copy and sent dbt to `~/.dbt` — the symptom was
`Could not find profile named 'football_scout'`. It was redundant (dbt already falls back to
`~/.dbt` unaided, so the workspace's other dbt projects resolve fine without it) and has been
removed. **Don't re-add it**; if a sibling project ever needs a different profiles dir, pass
`--profiles-dir` on that project's commands rather than exporting a global.

### Code style — enforced, not debated

SQL is formatted by **sqlfluff** (`.sqlfluff`), Python by **ruff** (`[tool.ruff]` in
`pyproject.toml`), both wired into **pre-commit**. Keywords upper case, identifiers
`lower_snake`, no alias padding.

```bash
uv run pre-commit install        # once per clone
uv run pre-commit run --all-files
```

**`sqlfluff fix` is not safe to trust blindly.** It rewrote one `USING (player_id)` to
`ON a.x = b.x` while leaving the other joins in the same query as `USING`, which made the column
ambiguous and broke `int_player_value_history` at runtime. Lint passing is not proof the SQL is
still correct - **always run `dbt build` after a fix pass**, and check row counts.

### Stop the Airflow stack when you are not using it

```bash
cd airflow && docker compose up -d    # start
cd airflow && docker compose down     # STOP WHEN DONE
```

Left running it costs **~87% of a CPU core continuously**, for a pipeline that
runs once a week. Idle polling is now tuned down hard, which cut container CPU
from ~38% to ~13% — but the Docker VM still burns ~77% on its own, bridging the
Google Drive FUSE mount into Linux. That part cannot be tuned away; only stopping
the containers fixes it (VM drops to ~0%). See ADR-0007, addendum 2.

### Google Drive `Icon\r` files break the venv

macOS stores a folder's custom icon in a file literally named `Icon` + carriage return, with the
image in a resource fork. Google Drive sets a custom icon on every folder it syncs, so one appears
in **every directory** — 77 of them here, 15 of which had been committed (git sees a 0-byte file).

There is no Drive setting to stop this. It is handled instead:

- `.gitignore` and `~/.gitignore_global` carry the literal `Icon\r` pattern, so they can never be
  committed again.
- `.vscode/settings.json` hides them via `files.exclude`.
- **The venv lives outside Drive** at `~/venvs/football-scout`, symlinked as `.venv`. This is the
  one that actually mattered: `jsonschema` crashes iterating a directory containing an `Icon\r`,
  so `dbt deps` died with `NotADirectoryError` until the venv moved out.

To clear them again after a sync: `find . -name 'Icon?' -delete`
