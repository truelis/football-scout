-- One row per player per game. Season = year the campaign started (Jul-Jun).
select
    appearance_id,
    game_id,
    player_id,
    player_club_id,
    competition_id,
    date                                        as match_date,
    {{ season_of('date') }}                     as season,
    coalesce(minutes_played, 0)                 as minutes_played,
    coalesce(goals, 0)                          as goals,
    coalesce(assists, 0)                        as assists,
    coalesce(yellow_cards, 0)                   as yellow_cards,
    coalesce(red_cards, 0)                      as red_cards
from {{ source('tm', 'appearances') }}
where player_id is not null
