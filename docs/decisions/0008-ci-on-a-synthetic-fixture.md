# ADR-0008: CI runs against a synthetic fixture, not real data

**Date:** 2026-09-12
**Status:** Accepted

## Context
`data/` is gitignored — it holds a 211MB Transfermarkt download and scraped
Understat parquet, neither of which belongs in git. So a CI runner starts with
nothing, and the pipeline cannot run.

Three options: commit a sample of real data, have CI download it, or generate it.

## Decision
Generate it. `scripts/make_fixture.py` produces **both** sources with the real
schemas — a DuckDB file with the five tables staging reads, and an Understat
parquet.

CI then runs four jobs: lint (ruff + sqlfluff), `dbt build` against the fixture,
a **rebuild at a past `as_of_date`** to exercise the leakage guards, and an
Airflow DagBag import check.

## Consequences
- CI is fast, offline, and deterministic. It cannot be broken by Club Elo
  returning 502, which it did for days.
- CI verifies the thing that actually breaks: models and tests against the
  *shapes* they will meet. It cannot verify *values* — a real schema change
  upstream still only surfaces on a live run.
- The fixture is a second thing to maintain. Every schema change now has to be
  made twice, and a stale fixture gives false confidence.

## The fixture has to be realistic in the ways the tests measure

Two bugs proved this, both found by running CI rather than by reading it.

**Names.** The fixture used `"Player 1001"`. `int_player_identity` normalises
with `[^a-z\s] -> ' '`, so every name collapsed to `"player"` and entity
resolution matched **6 of 1,728**. `assert_understat_match_coverage` failed on
the fixture while passing at 97.5% on live data. Names are now alphabetic and
unique.

**Shared identity across sources.** Understat fixture rows reuse the
Transfermarkt player names, because the coverage test measures agreement
*between* the sources. Independently random names would make that test
permanently red.

The general point: a fixture only needs to be realistic along the dimensions
the tests actually measure — but along *those* dimensions it has to be right, or
it inverts CI's purpose and reports failure for healthy code.

## Alternatives rejected
- **Commit a sample of real data.** Simplest, and it puts scraped Transfermarkt
  and Understat data into a public repo. CLAUDE.md rule 7 says never redistribute
  scraped data; this would breach it for convenience.
- **Download the real dataset in CI.** 211MB per run, dependent on an upstream
  host, and it makes every PR wait on a scraper. It would also have been red for
  the days Club Elo was down.
- **Skip CI on data models, lint only.** Cheap, and it would not have caught the
  three leaks or the fixture bugs above — which is most of CI's value here.
