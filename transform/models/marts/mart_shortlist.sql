-- The filtered, ranked output. This is what the app opens on.
with scored as (
    select
        *,
        round((0.5 * age_score + 0.3 * minutes_trend_score + 0.2 * value_trend_score), 1)
            as trajectory_score
    from {{ ref('mart_player_scores') }}
),

composite as (
    select
        *,
        round((
              {{ var('w_performance') }}  * performance_score
            + {{ var('w_trajectory') }}   * trajectory_score
            + {{ var('w_availability') }} * availability_score
        ) / ({{ var('w_performance') }} + {{ var('w_trajectory') }}
             + {{ var('w_availability') }}), 1) as composite_score
    from scored
),

filtered as (
    select * from composite
    where current_market_value_eur <= {{ var('max_market_value_eur') }}
      and age <= {{ var('max_age') }}
      and (
            minutes_played >= {{ var('min_minutes') }}
         or (minutes_played >= {{ var('min_minutes_if_trending') }}
             and minutes_played > coalesce(prev_minutes, 0))
      )
)

select
    row_number() over (order by composite_score desc)                    as rank,
    -- Defenders score on attacking output only in Phase 1, so a global rank
    -- flatters attackers. Rank within position group too; the app defaults
    -- to this one.
    row_number() over (partition by position_group
                       order by composite_score desc)                    as rank_in_position,
    *
from filtered
order by composite_score desc
