# ADR-0001: DuckDB and dbt, not Postgres and Airflow-managed SQL

**Date:** 2026-09-05 (recorded retrospectively 2026-09-12)
**Status:** Accepted

## Context
The project needs a warehouse for ~2M appearance rows, 656k market valuations and 50k players,
queried interactively from a Streamlit app on a single laptop. No budget, no server, no cloud.

## Decision
DuckDB as the warehouse — a single file, no process to run — with dbt-core plus dbt-duckdb for
transformation.

## Consequences
- The whole warehouse is one gitignored file; `rm data/scout.duckdb && dbt build` is a full reset.
- DuckDB reads Parquet and remote CSV natively, so the ingest layer can land Parquet and stop.
- dbt gives staging/intermediate/marts discipline, lineage and a test framework for free — the part
  an interviewer actually looks for.
- **Cost:** no concurrency. One writer at a time, which is why Airflow tasks must not run dbt in
  parallel with the app holding a connection. Read-only connections in the app mitigate this.
- **Cost:** dbt-duckdb is a smaller ecosystem than dbt-postgres or dbt-snowflake; some adapter
  behaviour (Python models, external sources) needed verifying rather than assuming.

## Alternatives rejected
- **Postgres in Docker.** Realistic, and closer to production shops — but it means a running
  service for a single-user analytical workload with no concurrent writes. All cost, no benefit
  here, and it slows every local iteration.
- **Snowflake / BigQuery free tier.** Adds credentials, network latency and an expiry date to a
  project meant to still run in two years. Also makes the repo unrunnable for anyone who clones it.
- **Pandas only, no dbt.** Would work at this volume, but throws away lineage, tests and the
  layered modelling discipline — which is most of what this project is meant to demonstrate.
