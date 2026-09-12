# ADR-0006: Frame the project around Panathinaikos, not generic scouting

**Date:** 2026-09-12
**Status:** Accepted

## Context
The tool worked as a general "find under-23 players under €4m" shortlist across 14 leagues. It
produced 166 plausible names. But a generic bargain-finder has no falsifiable claim attached to it:
there is no way to be wrong, so there is no reason to believe it.

The owner supports Panathinaikos, who have not won the Greek league since 2010 and have achieved
nothing significant in Europe since. They are not short of money — €30.7m on 11 signings in 25/26,
€20.5m on 8 in 24/25, €8.0m in 23/24 — and all of it is in the dataset, with fees.

## Decision
Make the project's question: **could a disciplined data-driven process have spent Panathinaikos'
transfer budget better than they did?**

The shortlist becomes a means to that end rather than the deliverable. The backtest compares the
model's recommendations as of a past date against the players Panathinaikos actually signed, and
against a matched control.

## Consequences
- The project acquires a claim that can be **wrong**, which is what makes it worth reading. If the
  model's picks underperform PAO's real signings, that is a finding and it goes in the README.
- The backtest stops being an optional Phase 3 nicety and becomes the centre of the project.
- Price caps and league weighting become PAO-specific: their real budget, and a Greek club's
  realistic recruitment market, rather than an arbitrary €4m.
- **Cost:** narrows the tool. A general audience gets less out of it.
- **Cost:** a sample of one club's signings is small. The backtest must also report against a
  matched control, or "the model beat PAO" could easily be noise.

## Alternatives rejected
- **Story in the README only.** Cheapest, and the story would be visibly disconnected from the
  product — an interviewer reading the README then the code would notice immediately.
- **A different, better-run club.** Testing against a club that recruits well would be a harder
  benchmark and a duller story. The point is the 16-year gap.
- **Stay fully general.** Keeps the tool broader but leaves it unfalsifiable, which is the exact
  weakness that makes most hobby projects in this space untrustworthy (SPEC §7).
