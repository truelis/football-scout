SELECT
    club_id,
    name AS club_name,
    domestic_competition_id AS competition_id,
    total_market_value AS squad_market_value_eur,
    squad_size,
    average_age
FROM {{ source('tm', 'clubs') }}
