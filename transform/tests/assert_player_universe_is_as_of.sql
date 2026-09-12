-- LEAKAGE GUARD. No player may be scored who had not yet played a professional
-- match at as_of_date.
--
-- players is a dimension of everyone the dataset currently knows about,
-- including people who were children at a past as_of_date. Rebuilt at 2023-01-01
-- this admitted 286 players aged under 14 - future professionals the model could
-- not possibly have been looking at, inflating every percentile pool they enter.
--
-- The check is on the SCORED population rather than dim_player: dim_player is
-- deliberately the full historical universe (see its description), and it is
-- being scored that matters.
SELECT
    s.player_id,
    MIN(a.match_date) AS first_appearance
FROM {{ ref('mart_player_scores') }} AS s
LEFT JOIN {{ ref('stg_tm__appearances') }} AS a ON s.player_id = a.player_id
GROUP BY s.player_id
HAVING
    MIN(a.match_date) > DATE '{{ var("as_of_date") }}'
    OR MIN(a.match_date) IS NULL
