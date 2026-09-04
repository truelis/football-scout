-- One row per player per season per competition: the raw production totals.
with apps as (
    select * from {{ ref('stg_tm__appearances') }}
)

select
    player_id,
    season,
    competition_id,
    count(*)                                        as appearances,
    sum(minutes_played)                             as minutes_played,
    sum(goals)                                      as goals,
    sum(assists)                                    as assists,
    sum(goals) + sum(assists)                       as goal_contributions,
    sum(yellow_cards)                               as yellow_cards,
    sum(red_cards)                                  as red_cards,
    count(*) filter (where minutes_played >= 60)    as substantial_appearances,
    -- per-90 rates. Guarded: null rather than divide-by-zero, and the
    -- minutes threshold is applied downstream, not hidden here.
    case when sum(minutes_played) > 0
         then sum(goals) * 90.0 / sum(minutes_played) end   as goals_per90,
    case when sum(minutes_played) > 0
         then sum(assists) * 90.0 / sum(minutes_played) end as assists_per90,
    case when sum(minutes_played) > 0
         then (sum(goals) + sum(assists)) * 90.0 / sum(minutes_played) end as ga_per90
from apps
group by 1, 2, 3
