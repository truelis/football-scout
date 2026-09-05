# football-scout

A local tool for finding young, improving footballers available for a realistic fee under ~€6m.

Not a live-scores app and not a transfer oracle: it produces a ranked shortlist to *investigate*, built from free data, with every score traceable back to its inputs.

## Stack

DuckDB (warehouse) · dbt-duckdb (transform) · Streamlit (UI) · Python (ingest)

Runs entirely on one machine. No server, no cloud, no cost.

## Quickstart

```bash
uv sync
uv run pre-commit install                # sqlfluff + ruff on commit

# 1. download the prepared Transfermarkt dataset (~weekly refreshed upstream)
uv run python ingest/transfermarkt.py
uv run python ingest/understat.py        # xG, top 5 leagues + Russia
uv run python ingest/clubelo.py          # team strength (upstream 502 as of 2026-09-05)

# 2. inspect the real schemas before trusting the staging models
uv run python scripts/explore_schema.py

# 3. build the warehouse
cd transform && uv run dbt deps && uv run dbt build && cd ..

# 4. browse
uv run streamlit run app/Home.py
```

To develop without downloading the real dataset:

```bash
uv run python scripts/make_fixture.py    # synthetic data, real schemas
```

## Tuning

Every parameter — price cap, age limit, minutes threshold, axis weights, age curve — lives in `transform/dbt_project.yml` under `vars:`.

```bash
dbt build --vars '{max_market_value_eur: 3000000, max_age: 21}'
```

## Data

| Source | Provides | Coverage |
|---|---|---|
| [transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets) | values + history, appearances, contracts, transfers | broad, weekly refresh |
| [Understat](https://understat.com) | xG, xA, npxG, xGChain, xGBuildup | top 5 leagues + Russia only |
| Club Elo *(pending — upstream outage)* | team strength → league coefficients | European clubs |

FBref lost its Opta licence in January 2026 and no longer carries advanced stats. Anything written before then that suggests otherwise is stale.

## Status

**Phase 1 complete** — Transfermarkt shortlist, running against the real dataset.
**Phase 2 part-built** — Understat xG ingested and wired into scoring, with Transfermarkt↔Understat
entity resolution at 97.5% top-5 coverage. Club Elo is outstanding: `api.clubelo.com` has been
returning HTTP 502, so league strength still uses the placeholder coefficients in
`seeds/league_tiers.csv`. Run `ingest/clubelo.py` to check whether it has recovered.

Findings and the reasoning behind the scoring choices are in `docs/phase1_findings.md`;
`docs/phase0_reconciliation.md` records how the real schemas differed from what the spec assumed.

See `SPEC.md` for the full design, `PHASE1.md` for the Phase 1 work order, and `CLAUDE.md` for the
working agreement.
