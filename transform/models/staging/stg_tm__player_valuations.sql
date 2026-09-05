SELECT
    player_id,
    date AS valuation_date,
    market_value_in_eur AS market_value_eur,
    current_club_id,
    player_club_domestic_competition_id AS competition_id
FROM {{ source('tm', 'player_valuations') }}
WHERE market_value_in_eur IS NOT NULL
