-- Three independent axes, each 0-100, plus a composite.
-- EVERY input is retained on the row so the UI can explain a ranking.
with ref_season as (
    select * from {{ ref('fct_player_season') }}
    where season = {{ var('reference_season') }}
),

prev_season as (
    select player_id,
           sum(minutes_played) as prev_minutes,
           sum(goal_contributions) * 90.0
             / nullif(sum(minutes_played), 0) as prev_ga_per90
    from {{ ref('fct_player_season') }}
    where season = {{ var('reference_season') }} - 1
    group by 1
),

-- collapse multi-competition rows to one row per player per season
agg as (
    select
        player_id,
        sum(minutes_played)                                as minutes_played,
        sum(appearances)                                   as appearances,
        sum(substantial_appearances)                       as substantial_appearances,
        sum(goals)                                         as goals,
        sum(assists)                                       as assists,
        sum(goal_contributions)                            as goal_contributions,
        max(position_group)                                as position_group,
        max(tier)                                          as tier,
        max(strength_coef)                                 as strength_coef,
        sum(goal_contributions) * 90.0
          / nullif(sum(minutes_played), 0)                 as ga_per90,
        sum(goal_contributions) * 90.0
          / nullif(sum(minutes_played), 0) * max(strength_coef) as ga_per90_adj
    from ref_season
    group by 1
),

eligible as (
    select a.*, p.prev_minutes, p.prev_ga_per90
    from agg a
    left join prev_season p using (player_id)
    where a.minutes_played >= {{ var('min_minutes_if_trending') }}
      -- Goalkeepers cannot be scored on attacking output and Phase 1 has no
      -- goalkeeping metrics. Excluding them beats ranking them on noise.
      and a.position_group != 'Goalkeeper'
),

-- Percentiles are computed WITHIN position group and league tier. A percentile
-- against "all players" is decorative; against the right peer group it is a
-- scouting statement.
pct as (
    select
        *,
        -- Percentile within POSITION GROUP across all leagues, on the
        -- league-ADJUSTED metric. Partitioning by tier as well would cancel
        -- out strength_coef entirely - a tier-3 player would be measured only
        -- against other tier-3 players and the adjustment would do nothing.
        percent_rank() over (
            partition by position_group order by ga_per90_adj
        ) as pct_output,
        percent_rank() over (
            partition by position_group order by minutes_played
        ) as pct_minutes
    from eligible
)

select
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
    round(100 * (0.75 * p.pct_output + 0.25 * p.pct_minutes), 1) as performance_score,

    -- ---- AXIS 2: trajectory ----
    -- age curve: gaussian around peak_age, so younger-than-peak scores high
    round(100 * exp(-power(d.age - {{ var('peak_age') }}, 2)
                    / (2 * power({{ var('age_curve_width') }}, 2))), 1) as age_score,
    round(100 * least(1.0, greatest(0.0,
        0.5 + 0.5 * coalesce(
            (p.minutes_played - p.prev_minutes) / nullif(p.prev_minutes, 0), 0)
    )), 1) as minutes_trend_score,
    round(100 * least(1.0, greatest(0.0,
        0.5 + coalesce(v.value_growth_12m, 0)
    )), 1) as value_trend_score,

    -- ---- AXIS 3: availability ----
    round(100 * case
        when d.contract_months_remaining is null then 0.40
        when d.contract_months_remaining <= {{ var('contract_bargain_months') }} then 1.00
        when d.contract_months_remaining <= {{ var('contract_leverage_months') }} then 0.75
        when d.contract_months_remaining <= 30 then 0.45
        else 0.25
    end, 1) as availability_score,

    -- confidence flag: Phase 1 has NO defensive or goalkeeping metrics.
    -- Do not let a tidy number imply we measured something we did not.
    case when d.position_group in ('Attack', 'Midfield') then 'medium' else 'low' end
        as confidence

from pct p
join {{ ref('dim_player') }} d using (player_id)
left join {{ ref('int_player_value_history') }} v using (player_id)
