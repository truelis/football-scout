# Phase 1 — what the model actually produces

**Date:** 2026-09-05 · **as_of:** 2026-09-04 · **reference season:** 2025 (Jul 2025 – Jun 2026)
**Filters:** TM value ≤ €4m · age ≤ 23 · ≥900 min, or ≥600 rising
**Output:** 271 players — 105 defenders, 86 attackers, 80 midfielders

Per PHASE1.md: **nothing has been tuned.** This reports what the model does. Raw output in
`/tmp` is regenerable from the queries described here.

---

## Headline

The list is populated by plausible players and it is not obviously broken — but three things
distort it, and one of them is a genuine bug rather than a tuning question.

| | Finding | Severity |
|---|---|---|
| 1 | **The age curve is backwards** — it rewards being *older*, inside an ≤23 filter | **Bug** |
| 2 | Performance dominates the composite (r=0.85) despite a 0.45 weight | Structural |
| 3 | Trajectory and Availability are near-degenerate — 2 values cover 85% and 45% | Structural |
| 4 | 39% of the list are defenders scored on attacking output they don't produce | Known, worse than expected |
| 5 | The top 5 leagues supply 19 of 271 (7%) — the opposite of SPEC §2.2's plan | Design tension |

---

## 1. The age curve rewards being older — this is a bug

`mart_player_scores` computes a Gaussian centred on `peak_age = 25.5`:

```sql
100 * exp(-power(age - 25.5, 2) / (2 * power(6.0, 2)))
```

Inside a shortlist capped at 23, every player is on the **rising** side of that curve, so the score
increases monotonically with age. Measured on the actual output:

| age | n | mean age_score | mean composite |
|---:|---:|---:|---:|
| 18 | 4 | 46.4 | 32.7 |
| 19 | 7 | 56.9 | 36.4 |
| 20 | 29 | 66.0 | 47.1 |
| 21 | 64 | 75.7 | 48.2 |
| 22 | 112 | 84.3 | 53.3 |
| **23** | **55** | **89.7** | **55.8** |

An 18-year-old is penalised 43 points against a 23-year-old *for being younger*. Composite tracks
it: median age on the list is 21.8, and the mass sits at 22–23 (167 of 271).

This directly contradicts SPEC §5.3, which specifies "**Reward 18–23**, neutral 24–25, penalise
26+". A curve peaking at 25.5 encodes "who is closest to their prime", which is the right shape for
valuing a squad and the wrong shape for finding prospects to buy early. Age is also weighted 0.5
within Trajectory — the largest single component of that axis — so the error propagates.

Not tuning it, per the brief. But this is not a weight to be tuned; the functional form is wrong for
the question being asked, and Phase 3's backtest will be calibrating against a distorted signal if
it goes in unchanged.

## 2. Performance dominates, whatever the weights say

Correlation of each axis with the composite:

```
performance_score    0.854
trajectory_score     0.476
availability_score   0.353
age_score            0.341
minutes_trend_score  0.258
```

Configured weights are 0.45 / 0.35 / 0.20. The realised influence is far more lopsided, because the
axes have wildly different spreads:

| axis | min | median | max | sd | distinct values |
|---|---:|---:|---:|---:|---:|
| performance | 0.0 | 36.0 | 89.5 | **23.4** | 225 |
| trajectory | 45.7 | 77.3 | 95.6 | 10.7 | 193 |
| availability | 25.0 | 40.0 | 100.0 | 26.7 | **5** |

A weight only matters in proportion to the variance behind it. Trajectory is compressed into a
narrow band (45.7–95.6), so its 0.35 weight moves rankings much less than performance's 0.45.
Composite is, in effect, a performance ranking with mild adjustment.

## 3. Trajectory and Availability are close to categorical

**`availability_score` has 5 distinct values across 271 players** — it is the contract bucket,
nothing more:

```
25.0 → 121 players (45%)    45.0 → 82     100.0 → 47     40.0 → 19     75.0 → 2
```

**`minutes_trend_score`: 146 players (54%) sit at exactly 50.0** — the no-prior-season default —
and 83 more at exactly 100.0, where the ratio caps. **85% of the list holds one of two values.**

**`value_trend_score`: 152 (56%) at exactly 100.0**, also capped.

So two of the three Trajectory inputs are saturated at their ceilings or pinned at a default. What
is left doing the work inside Trajectory is age — see §1.

## 4. Defenders are 39% of the list and the metric does not measure them

105 defenders, and **42 of them have zero goal contributions**. `ga_per90` is the only performance
input in Phase 1, so for those players the performance axis is measuring the absence of something
they are not paid to do. They are flagged `confidence = low` and ranked within position, but they
still occupy the largest share of the output.

The two players with `performance_score = 0.0` (Jacob Devaney, 600 min, composite 26.9; Vladyslav
Zakharchenko, 600 min, 25.7) are on the list purely on trajectory and availability.

PHASE1.md asks whether defenders belong in Phase 1 at all. On this evidence: the ranking *within*
defenders is close to meaningless, and their presence dilutes a list meant to be scanned. Worth
excluding until there is a defensive metric, the same way goalkeepers already are.

## 5. Per-league survival — nobody is at zero, but the shape is inverted

| id | league | tier | coef | ≥600 min | scored | shortlist | % |
|---|---|---:|---:|---:|---:|---:|---:|
| NL1 | Eredivisie | 2 | 0.72 | 316 | 288 | **42** | 13.3 |
| BE1 | Pro League | 2 | 0.68 | 279 | 258 | **39** | 14.0 |
| UKR1 | Ukrainian Premier League | 3 | 0.60 | 288 | 268 | **31** | 10.8 |
| SC1 | Scottish Premiership | 3 | 0.58 | 228 | 206 | **31** | 13.6 |
| DK1 | Danish Superliga | 3 | 0.57 | 176 | 157 | **30** | **17.0** |
| PO1 | Liga Portugal | 2 | 0.74 | 346 | 305 | 28 | 8.1 |
| RU1 | Russian Premier Liga | 2 | 0.66 | 277 | 250 | 22 | 7.9 |
| TR1 | Süper Lig | 2 | 0.70 | 345 | 303 | 12 | 3.5 |
| GR1 | Super League Greece | 3 | 0.62 | 239 | 218 | 12 | 5.0 |
| ES1 | LaLiga | 1 | 0.95 | 398 | 365 | 7 | 1.8 |
| FR1 | Ligue 1 | 1 | 0.86 | 337 | 317 | 4 | 1.2 |
| L1 | Bundesliga | 1 | 0.92 | 328 | 295 | 4 | 1.2 |
| IT1 | Serie A | 1 | 0.93 | 396 | 357 | 3 | 0.8 |
| GB1 | Premier League | 1 | 1.00 | 380 | 356 | **1** | **0.3** |

No league contributes zero, and the eligible→scored step loses only ~10% everywhere, so nothing is
being dropped structurally. But **the top five leagues supply 19 of 271 players (7%)**, and the
Premier League supplies one.

That is the €4m cap, not a modelling fault — under-23s worth ≤€4m barely exist in the Premier
League. It is worth stating plainly because **SPEC §2.2 chose to build v1 on the top 5 "where the
data is complete and the model can be validated"**, and the price filter has quietly relocated the
tool to tier 2/3. Phase 3's backtest will therefore be validating on Eredivisie/Belgium/Scotland,
not on the leagues the spec assumed.

Related: **Ukraine and Russia together supply 53 players (20%)**, on placeholder coefficients
(0.60, 0.66) that cannot be calibrated against European results — neither league plays in UEFA
competition normally. Those two guesses are load-bearing for a fifth of the output.

## 6. The names

**Recognisable, and they look right:** Mateo Joseph (Mallorca, England U21), Joe Hugill (Man Utd
academy, at Kilmarnock), Noah Mbamba (ex-Leverkusen/Club Brugge, at Dender), Edan Diop (ex-Monaco,
at Cercle Brugge), Tygo Land (ex-PSV, at Groningen), Adedire Mebude, Tristan Degreef (Anderlecht),
Igor Dmitriev (Spartak Moskva). These are exactly the profile the tool is for — young, real
pedigree, currently cheap.

**The unrecognisable ones are plausible rather than random.** Jochem Ritmeester van de Kamp (top
midfielder, 81.6) is a 22-year-old at Telstar with 2,045 minutes and 8 G+A — an unglamorous club
in a mid-tier league, which is precisely where the design says bargains hide. Same for Amar Fatah
(Dundee United), Charly Nouck (Viborg), Prosper Obah (LNZ Cherkasy, 14 G+A in 1,575 min).

**Thin samples flatter a few.** Dimitrios Chatsidis has the highest rate on the list (0.84 G+A/90)
off **644 minutes** — 6 contributions. Joe Hugill ranks 4th among attackers on **652 minutes**.
Farouck Adekami is 2nd among midfielders on **703**. The 600-minute floor is doing real work here,
and the UI shows minutes, but a rate from 7 league games is not evidence.

**Five players show no league** — their current club sits outside the seeded 14 (Sturm Graz,
Independiente, Rosenborg, Molde, Pardubice) though they were scored on minutes inside them. They
are transfers that have already happened; the shortlist is describing a player who has moved on.

## 7. Blind spots worth naming

- **No injury, disciplinary or off-field data.** Nothing in the free dataset covers availability in
  the medical sense, or anything that would make a club decline a signing. A name near the top of
  this list can be unsignable for reasons the model cannot see. Treat the output as "worth
  investigating", never "worth buying" — which is SPEC §1's stated intent.
- **No xG.** Goal contributions are the whole performance signal; finishing variance is unmodelled
  noise. Phase 2 addresses this for the top 5 leagues only — i.e. for 7% of this list.
- **Multi-league players are inflated** (see `docs/phase0_reconciliation.md` §5): 89 players who
  crossed tiers get the *better* league's coefficient on combined output.

---

## Recommended order for Task 4

1. **Fix the age curve.** Not a weight change — the functional form is wrong for the question. A
   monotonically decreasing penalty above ~21, or a plateau across 18–23, matches SPEC §5.3.
2. **Decide on defenders.** Excluding them until a defensive metric exists is the honest call and
   removes 39% of the noise.
3. **Give availability a continuous decay** on contract months, as PHASE1.md predicted.
4. **Give newcomers a real minutes-trend treatment** — 54% of the list sits on the default.
5. Leave the weights alone until Phase 3's backtest can arbitrate. Changing them now is fitting to
   intuition, and 1–4 will move the rankings more than any weight will.

---

# Task 4 — what was changed, and what it did

All five items above were implemented. **No weights were touched** — those wait for Phase 3's
backtest, per PHASE1.md. Every new parameter lives in `transform/dbt_project.yml` under `vars:`.

`dbt build`: PASS=53, WARN=1 (the orphan-competition watchdog), ERROR=0.
Shortlist **271 → 166**; the entire difference is the 105 excluded defenders.

## 1. Age curve — fixed, and it now points the right way

Gaussian around `peak_age` replaced with a logistic decay (`age_midpoint: 24.5`,
`age_steepness: 1.5`).

| age | n | age_score before | age_score after |
|---:|---:|---:|---:|
| 18 | 2 | 46.4 | **98.7** |
| 20 | 23 | 66.0 | 95.1 |
| 22 | 69 | 84.3 | 83.7 |
| 23 | 30 | 89.7 | **76.9** |

The signal is now monotonically decreasing in age, as SPEC §5.3 specifies. Note that mean
*composite* still rises gently with age (41.7 at 18 → 52.0 at 22) — that is not the age term any
more, it is older players having more minutes and more output. That is legitimate, and it is what
the age term is supposed to be counterweighting rather than reinforcing.

## 2. Availability — continuous, no longer categorical

Four-bucket `CASE` replaced with a logistic decay on contract months
(`contract_midpoint_months: 24.0`, `contract_steepness_months: 8.0`,
`contract_unknown_score: 0.40`).

**5 distinct values → 14**, range 1.6–93.2, sd 27.7. Granularity is now limited only by the
integer month input rather than by hand-drawn buckets, and the shape is unchanged in spirit —
short runway scores high, midpoint at two years.

## 3. Minutes trend — the 54% pile-up is gone

Players with no prior domestic season were all pinned at exactly 50.0. They now score on
`pct_minutes` — how much they actually played — which is genuine evidence of the manager's
opinion even without a baseline.

**43 distinct values → 106.** The single largest cluster is now 52 players at 100.0 (a real
ceiling: minutes more than doubled), against 146 identical values before.

A new `minutes_trend_basis` column (`prior_season` / `no_prior_season`) is carried on the row and
surfaced in both UI pages, so the two measurements are never presented as the same thing.

**Worth flagging:** newcomers now average 35.4 against 90.0 for returning players — a wider gap
than the old flat 50.0 gave them. That is honest (a first-season player who played little has weak
evidence of a rising role) but it is a real ranking effect, and `pct_minutes` already feeds
`performance_score` at 0.25, so minutes are counted twice for these players. Worth revisiting in
Phase 3 against the backtest rather than by intuition now.

## 4. Multi-league coefficient — now minutes-weighted

`MAX(strength_coef)` replaced with `SUM(minutes * coef) / SUM(minutes)`.

| player | old coef | new coef | old adj | new adj |
|---|---:|---:|---:|---:|
| Omri Gandelman | 0.930 | **0.782** | 0.383 | **0.322** |
| Kenneth Taylor | 0.930 | **0.830** | 0.343 | **0.306** |

Gandelman played 1,428′ in Belgium (0.68) and 979′ in Serie A (0.93) and was being credited at
Serie A's coefficient on his combined output — a 19% inflation of the rate that sets his
percentile. The new value matches the hand-computed truth exactly.

`season_strength_coef` is now retained on `mart_player_scores`, per CLAUDE.md's rule that marts
keep their inputs, so the UI can explain the league adjustment rather than asking to be trusted.

## 5. Defenders — excluded, and configurably so

`excluded_position_groups: ['Goalkeeper', 'Defender']`. This also removes the hard-coded
`'Goalkeeper'` string that was sitting in the SQL against CLAUDE.md rule 1.

They are excluded, not ranked badly — the same treatment goalkeepers already had, and for the same
reason: 42 of 105 had zero goal contributions, and `ga_per90` was the only performance input.
Dropping `'Defender'` from that list scores them again.

Every scored player is now `confidence = medium`. The `low` branch is retained for when Phase 2
brings in position groups that are measurable but weakly so.

## Still open, deliberately

- **Weights untouched.** Performance still correlates hardest with the composite; that is a
  variance-spread property, not a weight error, and Phase 3 should arbitrate it.
- **Placeholder league coefficients.** Ukraine and Russia still carry uncalibratable guesses.
- **Displayed league still comes from the current club**, so a player who moved mid-season shows
  his new league next to scores earned in his old one. `season_strength_coef` now exposes the
  discrepancy; reconciling the display is a UI task.
- **No xG, no injury or off-field data.** Unchanged, and unchangeable in Phase 1.

---

# Phase 2 (part 1) — Understat and entity resolution

Club Elo was chosen to go first, but **`api.clubelo.com` was returning HTTP 502 on every
endpoint and date** when Phase 2 began — SPEC §9's "scrapers break without warning", on day one.
The main site still responded, so this is an upstream outage rather than a block on the approach.
`ingest/clubelo.py` and the league/team-strength models are the remaining Phase 2 work and will
run when the API returns; Understat was built first because it was up.

## Entity resolution: 97.49% top-5 coverage

| pass | matched | note |
|---|---:|---|
| exact normalised name, within league+season | 3,812 | |
| fuzzy `token_set_ratio` ≥ 90, within league+season | 283 | |
| fuzzy name + birth year, league ignored | 4 | mid-season league changes |
| manual overrides seed | 0 | empty is the correct starting state |

Every league-season is ≥95.5%, against SPEC §4.2's 90% floor, which
`assert_understat_match_coverage` now enforces as a build failure.

**1:1 is enforced.** 17 Transfermarkt players were initially claimed by more than one Understat
player — genuine namesakes, three separate Roberto Fernández in La Liga. The best-scoring claim
wins and the rest are left *unmatched*: an unmatched player simply has no xG, whereas a wrong match
silently attributes another man's.

An independent check that the matching is real: for matched players, Understat minutes track
Transfermarkt minutes closely (1048/1028, 1704/1707, 2141/2150). Those are separate sources
counting the same appearances.

## What xG changes

23 of the 166 shortlisted players are in Understat's coverage (`confidence = high`); the other 143
are still scored on goal contributions (`confidence = medium`). The gap is the coverage paradox,
not a defect — the €4m cap puts most of the list outside the top five.

**Where it does reach, it is doing real work.** Pathé Mboup (Ligue 1) has a G+A/90 of 0.09 but an
npxG+xA/90 of **0.438**, finishing 2.55 goals below npxG. Phase 1's metric called him poor; xG says
he is creating chances and not converting. That is precisely the distinction the axis exists to
draw.

**The two metrics are percentiled in separate pools**, partitioned by `has_xg` alongside position.
Ranking npxG+xA and goal contributions in one pool would put two different metrics on one scale and
call the result a percentile. Each player is ranked against peers measured the same way, and
`performance_basis` says which — surfaced in both UI pages. Both pools span 0–100 with similar
means (48.7 and 51.0), so neither is systematically advantaged.

A player is only scored on xG when Understat covers at least `xg_minutes_coverage_min` (0.5) of his
domestic minutes; below that the rate describes a fragment of his season rather than the player
being ranked.

**Finishing vs npxG is retained and never scored.** SPEC §5.2 calls it noise over a single season.
It appears in the drill-down because it explains a gap between goals and chance quality, and it is
kept out of every score.

## Still open

- **Club Elo** — blocked on the upstream 502. League and team strength still use the placeholder
  seed coefficients, which Task 3 found are carrying most of the ranking.
- **Position-specific metric weighting.** SPEC §5.2 wants different inputs for attackers
  (npxG/90, shots, key passes) and midfielders (xGBuildup, xGChain). All are retained on the row;
  the weighting between them is a tuning decision that belongs after Phase 3's backtest, not before.
