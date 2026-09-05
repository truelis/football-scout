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
