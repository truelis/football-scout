-- Player x season production, joined to league context. The grain the
-- scoring model reads from.
select
    s.player_id,
    s.season,
    s.competition_id,
    lt.league_name,
    lt.tier,
    lt.strength_coef,
    d.position_group,
    d.age - (date_part('year', date '{{ var("as_of_date") }}') - s.season) as age_in_season,
    s.appearances,
    s.substantial_appearances,
    s.minutes_played,
    s.goals,
    s.assists,
    s.goal_contributions,
    s.goals_per90,
    s.assists_per90,
    s.ga_per90,
    -- league-adjusted output: the core Phase 1 comparability fix
    s.ga_per90 * lt.strength_coef as ga_per90_adj
from {{ ref('int_player_season') }} s
left join {{ ref('league_tiers') }} lt on s.competition_id = lt.competition_id
left join {{ ref('dim_player') }} d using (player_id)
where lt.competition_id is not null   -- domestic leagues we have tiers for
