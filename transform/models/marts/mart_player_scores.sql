-- Three independent axes, each 0-100, plus a composite.
-- EVERY input is retained on the row so the UI can explain a ranking.
-- The SCORING SAMPLE is domestic-league only. Cup and European rows exist in
-- fct_player_season and are deliberately kept there - they are squad-role and
-- level-progression evidence for Phases 2-3 - but they must not be pooled into
-- a per-90 rate, or a player's output would depend on how far his club ran in
-- a cup. This is the one place that choice is made.
WITH ref_season AS (
    SELECT * FROM {{ ref('fct_player_season') }}
    WHERE
        season = {{ var('reference_season') }}
        AND is_domestic_league
),

prev_season AS (
    SELECT
        player_id,
        SUM(minutes_played) AS prev_minutes,
        SUM(goal_contributions) * 90.0
        / NULLIF(SUM(minutes_played), 0) AS prev_ga_per90
    FROM {{ ref('fct_player_season') }}
    WHERE
        season = {{ var('reference_season') }} - 1
        AND is_domestic_league
    GROUP BY 1
),

-- collapse multi-competition rows to one row per player per season
agg AS (
    SELECT
        player_id,
        SUM(minutes_played) AS minutes_played,
        SUM(appearances) AS appearances,
        SUM(substantial_appearances) AS substantial_appearances,
        SUM(goals) AS goals,
        SUM(assists) AS assists,
        SUM(goal_contributions) AS goal_contributions,
        MAX(position_group) AS position_group,
        MAX(tier) AS tier,
        MAX(strength_coef) AS strength_coef,
        SUM(goal_contributions) * 90.0
        / NULLIF(SUM(minutes_played), 0) AS ga_per90,
        SUM(goal_contributions) * 90.0
        / NULLIF(SUM(minutes_played), 0) * MAX(strength_coef) AS ga_per90_adj
    FROM ref_season
    GROUP BY 1
),

eligible AS (
    SELECT
        a.*,
        p.prev_minutes,
        p.prev_ga_per90
    FROM agg AS a
    LEFT JOIN prev_season AS p USING (player_id)
    WHERE a.minutes_played >= {{ var('min_minutes_if_trending') }}
    -- Goalkeepers cannot be scored on attacking output and Phase 1 has no
    -- goalkeeping metrics. Excluding them beats ranking them on noise.
    AND a.position_group != 'Goalkeeper'
),

-- Percentiles are computed WITHIN position group and league tier. A percentile
-- against "all players" is decorative; against the right peer group it is a
-- scouting statement.
pct AS (
    SELECT
        *,
        -- Percentile within POSITION GROUP across all leagues, on the
        -- league-ADJUSTED metric. Partitioning by tier as well would cancel
        -- out strength_coef entirely - a tier-3 player would be measured only
        -- against other tier-3 players and the adjustment would do nothing.
        PERCENT_RANK() OVER (
            PARTITION BY position_group ORDER BY ga_per90_adj
        ) AS pct_output,
        PERCENT_RANK() OVER (
            PARTITION BY position_group ORDER BY minutes_played
        ) AS pct_minutes
    FROM eligible
)

SELECT
    d.player_id,
    d.player_name,
    d.age,
    d.position_group,
    d.sub_position,
    d.current_club_name,
    d.league_name,
    d.tier,
    d.competition_id,
    d.current_market_value_eur,
    d.estimated_fee_eur,
    d.contract_expiration_date,
    d.contract_months_remaining,
    d.contract_status,

    -- ---- raw inputs, retained deliberately ----
    p.minutes_played,
    p.appearances,
    p.substantial_appearances,
    p.goals,
    p.assists,
    p.goal_contributions,
    p.ga_per90,
    p.ga_per90_adj,
    p.prev_minutes,
    p.prev_ga_per90,
    p.pct_output,
    p.pct_minutes,
    v.value_now,
    v.value_growth_12m,
    v.value_cagr_24m,
    v.value_vs_peak,

    -- ---- AXIS 1: performance ----
    ROUND(100 * (0.75 * p.pct_output + 0.25 * p.pct_minutes), 1) AS performance_score,

    -- ---- AXIS 2: trajectory ----
    -- age curve: gaussian around peak_age, so younger-than-peak scores high
    ROUND(100 * EXP(
        -POWER(d.age - {{ var('peak_age') }}, 2)
        / (2 * POWER({{ var('age_curve_width') }}, 2))
    ), 1) AS age_score,
    ROUND(100 * LEAST(1.0, GREATEST(
        0.0,
        0.5 + 0.5 * COALESCE(
            (p.minutes_played - p.prev_minutes) / NULLIF(p.prev_minutes, 0), 0
        )
    )), 1) AS minutes_trend_score,
    ROUND(100 * LEAST(1.0, GREATEST(
        0.0,
        0.5 + COALESCE(v.value_growth_12m, 0)
    )), 1) AS value_trend_score,

    -- ---- AXIS 3: availability ----
    ROUND(100 * CASE
        WHEN d.contract_months_remaining IS NULL THEN 0.40
        WHEN d.contract_months_remaining <= {{ var('contract_bargain_months') }} THEN 1.00
        WHEN d.contract_months_remaining <= {{ var('contract_leverage_months') }} THEN 0.75
        WHEN d.contract_months_remaining <= 30 THEN 0.45
        ELSE 0.25
    END, 1) AS availability_score,

    -- confidence flag: Phase 1 has NO defensive or goalkeeping metrics.
    -- Do not let a tidy number imply we measured something we did not.
    CASE WHEN d.position_group IN ('Attack', 'Midfield') THEN 'medium' ELSE 'low' END
        AS confidence

FROM pct AS p
INNER JOIN {{ ref('dim_player') }} AS d USING (player_id)
LEFT JOIN {{ ref('int_player_value_history') }} AS v USING (player_id)
