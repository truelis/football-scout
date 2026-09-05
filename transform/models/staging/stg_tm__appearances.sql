-- One row per player per game. Season = year the campaign started (Jul-Jun).
SELECT
    appearance_id,
    game_id,
    player_id,
    player_club_id,
    competition_id,
    date AS match_date,
    {{ season_of('date') }} AS season,
    COALESCE(minutes_played, 0) AS minutes_played,
    COALESCE(goals, 0) AS goals,
    COALESCE(assists, 0) AS assists,
    COALESCE(yellow_cards, 0) AS yellow_cards,
    COALESCE(red_cards, 0) AS red_cards
FROM {{ source('tm', 'appearances') }}
WHERE player_id IS NOT NULL
