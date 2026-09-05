-- No per-90 rate may exist without minutes behind it.
SELECT
    player_id,
    season,
    competition_id,
    minutes_played,
    ga_per90
FROM {{ ref('int_player_season') }}
WHERE ga_per90 IS NOT NULL AND COALESCE(minutes_played, 0) = 0
