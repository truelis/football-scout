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
        -- ARG_MAX, not MAX: the league he actually played most of the season
        -- in, with tier/name/id all taken from that SAME competition row.
        -- Independent MAX()es would happily mix a tier from one league with a
        -- name from another.
        ARG_MAX(competition_id, minutes_played) AS season_competition_id,
        ARG_MAX(league_name, minutes_played) AS season_league_name,
        ARG_MAX(tier, minutes_played) AS season_tier,
        -- MINUTES-WEIGHTED, not MAX. A player splitting a season across two
        -- leagues used to have his COMBINED output multiplied by the stronger
        -- league's coefficient. Omri Gandelman played 1428' in Belgium (0.68)
        -- and 979' in Serie A (0.93) and was credited at 0.93 - a 19% inflation
        -- on the rate that decides his percentile. 89 players span tiers.
        SUM(minutes_played * strength_coef)
        / NULLIF(SUM(minutes_played), 0) AS strength_coef,
        SUM(goal_contributions) * 90.0
        / NULLIF(SUM(minutes_played), 0) AS ga_per90,
        SUM(goal_contributions) * 90.0
        / NULLIF(SUM(minutes_played), 0)
        * (
            SUM(minutes_played * strength_coef)
            / NULLIF(SUM(minutes_played), 0)
        ) AS ga_per90_adj,
        -- ---- Understat, where it reaches ----
        SUM(COALESCE(understat_minutes, 0)) AS understat_minutes,
        SUM(np_xg) AS np_xg,
        SUM(xa) AS xa,
        SUM(shots) AS shots,
        SUM(key_passes) AS key_passes,
        SUM(xg_chain) AS xg_chain,
        SUM(xg_buildup) AS xg_buildup,
        SUM(np_goals_minus_npxg) AS np_goals_minus_npxg,
        -- Sum the components, then divide. Averaging two per-90 rates would
        -- weight a 200-minute spell as heavily as a 2,000-minute one.
        (SUM(np_xg) + SUM(xa)) * 90.0
        / NULLIF(SUM(understat_minutes), 0) AS npxg_xa_per90,
        (SUM(np_xg) + SUM(xa)) * 90.0
        / NULLIF(SUM(understat_minutes), 0)
        * (
            SUM(minutes_played * strength_coef)
            / NULLIF(SUM(minutes_played), 0)
        ) AS npxg_xa_per90_adj
    FROM ref_season
    GROUP BY 1
),

eligible AS (
    SELECT
        a.*,
        p.prev_minutes,
        p.prev_ga_per90,
        -- Scored on xG only when Understat covers enough of the season to make
        -- the rate describe the player being ranked, not a fragment of him.
        a.npxg_xa_per90_adj IS NOT NULL
        AND a.understat_minutes
        >= {{ var('xg_minutes_coverage_min') }} * a.minutes_played AS has_xg
    FROM agg AS a
    LEFT JOIN prev_season AS p USING (player_id)
    WHERE a.minutes_played >= {{ var('min_minutes_if_trending') }}
    -- Excluded position groups come from dbt_project.yml, never hard-coded.
    -- Goalkeepers have no metrics at all in the free data; defenders have no
    -- DEFENSIVE ones, so ranking them on goal contributions measures the
    -- absence of something they are not paid to do.
    AND a.position_group NOT IN (
        {%- for g in var('excluded_position_groups') %}
        '{{ g }}'{{ "," if not loop.last }}
        {%- endfor %}
    )
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
        -- Partitioned by has_xg as well as position, deliberately. Half these
        -- players are measured on npxG+xA and half on goal contributions;
        -- ranking both in one pool would put two different metrics on one
        -- scale and call the result a percentile. Each player is ranked
        -- against peers measured the same way, and performance_basis says
        -- which. Tier is still NOT in the partition - that would cancel out
        -- the league coefficient entirely.
        PERCENT_RANK() OVER (
            PARTITION BY position_group, has_xg
            ORDER BY COALESCE(npxg_xa_per90_adj, ga_per90_adj)
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
    -- The league he was SCORED in, i.e. where he played the most minutes.
    -- dim_player's league describes his CURRENT club, which for anyone who has
    -- since transferred is a different competition entirely - 5 shortlisted
    -- players had a null league here purely because their new club sits outside
    -- the seeded 14, while their scores came from inside them. Both are kept:
    -- the scored league is the honest label for a score, the current one is
    -- what matters for actually signing him.
    p.season_league_name AS league_name,
    p.season_tier AS tier,
    p.season_competition_id AS competition_id,
    d.league_name AS current_club_league_name,
    d.tier AS current_club_tier,
    d.competition_id AS current_club_competition_id,
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
    p.has_xg,
    p.understat_minutes,
    p.np_xg,
    p.xa,
    p.shots,
    p.key_passes,
    p.xg_chain,
    p.xg_buildup,
    p.npxg_xa_per90,
    p.npxg_xa_per90_adj,
    -- Finishing over/underperformance. SPEC 5.2: NOISE over one season, not
    -- skill. Shown in the drill-down, never fed into a score.
    p.np_goals_minus_npxg,
    CASE
        WHEN p.has_xg THEN 'npxg_xa_per90'
        ELSE 'goal_contributions_per90'
    END AS performance_basis,
    -- The minutes-weighted league coefficient actually applied to this player,
    -- retained so the UI can explain the league adjustment instead of the user
    -- having to trust it. Differs from dim_player's tier for anyone who moved
    -- mid-season - that one describes his CURRENT club, this one what he played.
    p.strength_coef AS season_strength_coef,
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
    -- Age: logistic DECAY, high and flat through the teens, falling away past
    -- the midpoint. Replaces a gaussian centred on 25.5, which - inside an
    -- age<=23 shortlist - put every player on its rising slope and so rewarded
    -- being OLDER: 18-year-olds averaged 46.4 against 89.7 for 23-year-olds.
    ROUND(100 / (1 + EXP(
        (d.age - {{ var('age_midpoint') }}) / {{ var('age_steepness') }}
    )), 1) AS age_score,
    -- Minutes trend. A player with no prior domestic season has no trend to
    -- measure, and a flat 0.5 put 54% of the shortlist on one value - while
    -- youth graduates and new signings are exactly the target profile. They are
    -- scored instead on how much they actually played, which is real evidence
    -- of the manager's opinion even without a baseline. Basis is exposed below
    -- so the UI never presents the two as the same measurement.
    ROUND(100 * CASE
        WHEN p.prev_minutes IS NULL OR p.prev_minutes = 0 THEN p.pct_minutes
        ELSE LEAST(1.0, GREATEST(
            0.0, 0.5 + 0.5 * (p.minutes_played - p.prev_minutes) / p.prev_minutes
        ))
    END, 1) AS minutes_trend_score,
    CASE
        WHEN p.prev_minutes IS NULL OR p.prev_minutes = 0 THEN 'no_prior_season'
        ELSE 'prior_season'
    END AS minutes_trend_basis,
    ROUND(100 * LEAST(1.0, GREATEST(
        0.0,
        0.5 + COALESCE(v.value_growth_12m, 0)
    )), 1) AS value_trend_score,

    -- ---- AXIS 3: availability ----
    -- Contract runway as a continuous logistic decay. The previous four-bucket
    -- CASE produced just FIVE distinct values across 271 players, 45% of them
    -- identical - a categorical axis wearing a 0-100 costume. Shape is
    -- unchanged in spirit: short runway scores high, and the midpoint sits at
    -- two years. Unknown expiry keeps its own explicit default rather than
    -- silently scoring as though the contract were long.
    ROUND(100 * CASE
        WHEN d.contract_months_remaining IS NULL
            THEN {{ var('contract_unknown_score') }}
        ELSE 1 / (1 + EXP(
            (d.contract_months_remaining - {{ var('contract_midpoint_months') }})
            / {{ var('contract_steepness_months') }}
        ))
    END, 1) AS availability_score,

    -- confidence flag: Phase 1 has NO defensive or goalkeeping metrics.
    -- Do not let a tidy number imply we measured something we did not.
    -- Confidence now tracks what was actually MEASURED, not just position.
    -- A player scored on npxG+xA is on a genuine shot-quality metric; one
    -- scored on goal contributions is on a coarse proxy, because Understat
    -- does not cover his league at all.
    CASE
        WHEN d.position_group NOT IN ('Attack', 'Midfield') THEN 'low'
        WHEN p.has_xg THEN 'high'
        ELSE 'medium'
    END AS confidence

FROM pct AS p
INNER JOIN {{ ref('dim_player') }} AS d USING (player_id)
LEFT JOIN {{ ref('int_player_value_history') }} AS v USING (player_id)
