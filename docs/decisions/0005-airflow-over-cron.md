# ADR-0005: Orchestrate with Airflow, knowing cron would be sufficient

**Date:** 2026-09-12
**Status:** Accepted

## Context
The pipeline is: download the Transfermarkt file → fetch Understat → fetch Club Elo → `dbt build` →
publish. It runs weekly, on one laptop, for one user. The upstream data refreshes weekly.

A `cron` line and a shell script would run this correctly.

The project has a second purpose, though: it is a data engineering portfolio piece, and the owner
wants to learn orchestration. `CLAUDE.md` originally said "no Airflow"; this ADR supersedes that.

## Decision
Orchestrate with Airflow, running locally under Docker Compose.

**And state the trade-off openly rather than dressing it up.** The honest framing, for a README or
an interview, is: *"cron would suffice for a weekly single-machine job. I used Airflow for retries,
backfill, dependency management across three independent sources, and visible task-level failure —
and because orchestration is what I wanted to learn."*

That is a stronger answer than claiming necessity, because the claim is inspectable: an interviewer
who knows Airflow will see immediately that a weekly single-box job does not require it, and
pretending otherwise costs more credibility than the admission.

## Consequences
- Contradicts the original "no Docker, no Airflow" rule in `CLAUDE.md`, now updated.
- Real capability gained: per-task retries around flaky scrapers (Club Elo returned HTTP 502 for
  days during Phase 2, exactly the failure Airflow handles well); backfill for the backtest's
  multiple as-of dates; a DAG that documents the pipeline's shape better than a shell script.
- Real cost: a Docker Compose stack, a scheduler and a metadata database to run a job that takes
  minutes. Local development gets heavier.
- DuckDB permits one writer, so `dbt build` tasks must not run concurrently — the DAG has to
  serialise them deliberately rather than fanning out.

## Alternatives rejected
- **cron.** Sufficient, and genuinely the right engineering choice for the workload. Rejected only
  because it demonstrates and teaches nothing the project is meant to demonstrate and teach.
- **Prefect / Dagster.** Both lighter and arguably better suited to this shape of job — Dagster's
  asset model fits a dbt project particularly well. Rejected because Airflow is what interviews ask
  about and what the owner is already studying in `airflow-zero-to-hero/`.
- **GitHub Actions on a schedule.** Free, no local stack, and already in use for CI. Rejected as
  the *primary* orchestrator because the 211MB download and DuckDB file would have to live
  somewhere between runs, which means cloud storage and a real architecture change.
