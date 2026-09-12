# Backtest — does this actually work?

**Method:** rebuild the entire warehouse as of a past date into a separate DuckDB file, snapshot the
shortlist as it would have looked then, and score what happened over the following 24 months using
the full current data. Run `uv run python scoring/backtest.py`.

**Dates evaluated:** 2023-01-01 (season 2022) and 2024-01-01 (season 2023).
**Held out and never tuned against:** 2025-01-01.

---

## The short version

**The ranking has real signal, and Panathinaikos would have done better following it.** Both claims
survive the confound checks below. Neither is spectacular, which is the point — a spectacular
backtest result in this domain almost always means a leak.

---

## 1. Three leaks had to be closed before any of this meant anything

CLAUDE.md rule 3 says write the leakage test before the backtest. Doing so found three, each
invisible at today's as-of date:

| leak | why it was fatal |
|---|---|
| `market_value_in_eur` was a **current snapshot** | Rebuilt at 2023 it filtered on 2026 values. Players whose value later collapsed would be *included* — the model would "find" them by knowing their future. |
| The **player universe was unbounded** | 286 players aged under 14 at 2023-01-01 — future professionals who had not debuted, inflating every percentile pool. |
| Players with **no date of birth** were scored | Age carries half the trajectory axis; scoring them means inventing it. |

Two singular tests now run on **every** build, live and backtest:
`assert_market_value_is_as_of` and `assert_player_universe_is_as_of`. The market-value fix was
verified by rebuilding at two dates and confirming 43.5% of players differ — Lamine Yamal €60M in
2024 against €200M now. A 0% difference would have meant it was still frozen.

## 2. The first result was fake, and here is how

The first run produced **shortlist +69% vs control −14%**. Both numbers were worthless:

- **The control was 17 players.** The shortlist filter admits 284 of the 301 in-bracket players, so
  "shortlist vs control" was measuring the minutes filter, not the model.
- **Percentage growth is not comparable across price brackets.** Shortlist median €0.80M against
  PAO's €2.00M — a cheap player has far more room to double.
- **The widened control was every age.** A 30-year-old's value falls for reasons that have nothing
  to do with the model. Unmatched it showed −23% against the shortlist's +69%, which looks like
  skill and is mostly just age.

Every comparison below is therefore **age-matched and made within value buckets**.

## 3. Does the score predict? — quartiles of the same shortlist

Every player here cleared identical hard filters, so the only thing separating the quartiles is the
ranking. This is the test a price confound cannot fake.

**2024-01-01 — monotonic:**

| quartile | n | median value growth | median Δ |
|---|---:|---:|---:|
| Q1 (worst) | 80 | +29% | +€0.10M |
| Q2 | 80 | +56% | +€0.38M |
| Q3 | 78 | +71% | +€0.50M |
| **Q4 (best)** | 79 | **+75%** | **+€1.00M** |

Within value buckets at 2024, **Q4 beats Q1 in all four**: <0.5M (+100% vs +48%), 0.5–1M (+85% vs
+14%), 1–2M (+108% vs +58%), 2–4M (+43% vs −20%).

**2023-01-01 — weaker and non-monotonic.** Aggregate quartiles run +69%, +25%, +67%, +150%: Q4 is
clearly best but the middle ordering is noise. Within buckets Q4 beats Q1 in **three of four**; in
the cheapest bucket the ordering reverses (Q1 +129% vs Q4 +89%).

**Read:** the score orders players usefully at the top of the distribution, and the reversal in the
cheapest 2023 bucket did not repeat in 2024, so it is most likely noise rather than a structural
flaw. Sub-€500k players are the thinnest samples in the dataset and the least reliable either way.

## 4. Against what Panathinaikos actually signed

Value-matched, over 24 months:

| bucket | shortlist | PAO signings |
|---|---:|---:|
| **2023-01-01** | | |
| <0.5M | **+100%** | 0% |
| 1–2M | **+96%** | −70% |
| 2–4M | **+45%** | −30% |
| >4M | — | −42% |
| **2024-01-01** | | |
| <0.5M | **+70%** | 0% |
| 2–4M | **+43%** | −20% |
| >4M | — | −13% |

**PAO's signings lost value in every bucket at both dates.** They spent €29.6M in the 2023 window
across 40 incoming transfers. The model's shortlist appreciated in every bucket it occupied.

This is the project's headline claim, and it is the one to state carefully — see the limits below.

## 5. What this does not show

- **Market value is the market's opinion, not ground truth.** A shortlist that beats its control on
  value growth has predicted *the crowd*, which is a weaker claim than predicting football. A player
  can appreciate because he got hyped.
- **There is no clean control for the filter itself.** Young + cheap + playing is almost entirely
  shortlisted, and the U23 players who were *not* shortlisted are mostly the expensive ones (median
  €12M) — different players, not a control. So the backtest tests the **ranking**, not whether the
  hard filters are well chosen.
- **The availability axis cannot be backtested at all.** The dataset carries one contract expiry per
  player with no history, so a renewal signed in 2025 looks like it was always there. Availability
  numbers are contaminated, and the composite is partly so.
- **PAO's signings are not age-matched.** They sign whoever they need; the shortlist is U23 only.
  Some of the gap is that older signings depreciate.
- **Two dates is not many.** 2025-01-01 is held out precisely so there is something left to check
  against once weights are tuned.

## 6. What this changes

The ranking earns its place, so the next tuning pass has something to tune *against* rather than
tuning to intuition. Specifically:

1. Re-check the sub-€500k band once a third date is available — if the 2023 reversal repeats, a
   minimum-value floor may be justified.
2. The availability axis needs either a historical contract source or removal from the composite.
   It currently cannot be validated at all.
3. Weights remain untouched until they can be tuned against 2023 and 2024 and then checked once
   against the holdout.
