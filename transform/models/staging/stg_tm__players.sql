-- Rename and cast only. No business logic.
SELECT
    player_id,
    name AS player_name,
    date_of_birth,
    position AS position_group,
    sub_position,
    foot,
    height_in_cm,
    country_of_citizenship,
    current_club_id,
    current_club_name,
    current_club_domestic_competition_id AS competition_id,
    contract_expiration_date,
    market_value_in_eur AS current_market_value_eur,
    highest_market_value_in_eur AS highest_market_value_eur,
    last_season
FROM {{ source('tm', 'players') }}
WHERE player_id IS NOT NULL
