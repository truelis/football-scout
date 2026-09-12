# ADR-0002: Use the prepared Transfermarkt dataset, do not scrape Transfermarkt

**Date:** 2026-09-05 (recorded retrospectively 2026-09-12)
**Status:** Accepted

## Context
The project needs market values, contracts, appearances and transfers. Transfermarkt has all of it
behind a site that forbids scraping and rate-limits aggressively.

## Decision
Download the prepared DuckDB file published weekly by `dcaribou/transfermarkt-datasets`. Scrape
nothing from Transfermarkt directly.

## Consequences
- One 211MB HTTP GET replaces thousands of page requests. Refreshing the data *is* re-downloading
  the file, which makes the ingest trivially idempotent.
- We inherit that project's schema and its changes. This bit immediately: `competitions` has no
  `is_major_national_league` column, and our staging model assumed one and failed to build. See
  `docs/phase0_reconciliation.md`.
- We inherit its coverage: 14 domestic leagues with appearance data, not the 31 in its
  `competitions` table.
- Freshness is bounded by their weekly run, which is fine for a transfer-market tool.

## Alternatives rejected
- **Scraping Transfermarkt.** Against their terms, fragile, slow, and ethically the wrong call for
  a portfolio piece. "I scraped a site that asked me not to" is a bad interview answer.
- **A paid API (Opta, Wyscout).** Correct for a real club, unavailable at this budget.
- **FBref for everything.** FBref lost its Opta licence in January 2026 and removed all advanced
  statistics. Any tutorial written before then assumes stats that no longer exist.
