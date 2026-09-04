-- No per-90 rate may exist without minutes behind it.
select player_id, season, competition_id, minutes_played, ga_per90
from {{ ref('int_player_season') }}
where ga_per90 is not null and coalesce(minutes_played, 0) = 0
