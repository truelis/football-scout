-- One row per player per season per competition: the raw production totals.
--
-- DOMESTIC FIRST-TIER LEAGUE APPEARANCES ONLY. Cup and European ties are a
-- different sample - different opposition quality, different squad rotation,
-- wildly different sample sizes - and pooling them into a per-90 rate makes a
-- player's output depend on how far his club ran in a cup. They are excluded
-- here rather than downstream so nothing further along has to remember.
--
-- The filter is deliberately POSITIVE (is_first_tier_domestic_league) rather
-- than "not a cup". Four competition_ids in appearances - POCP (Taça da Liga),
-- CGB (EFL Cup), KLUB (Club World Cup) and UKRS (Ukrainian Super Cup), ~14k
-- appearances between them - have NO row in `competitions` at all, so a
-- negative filter would silently let them through. See the referential
-- integrity test in tests/assert_appearance_competitions_known.sql.
with apps as (
    select * from {{ ref('stg_tm__appearances') }}
),

domestic as (
    select a.*
    from apps a
    join {{ ref('stg_tm__competitions') }} c using (competition_id)
    where c.is_first_tier_domestic_league
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
from domestic
group by 1, 2, 3
