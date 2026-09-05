-- The price filter is the whole point of the tool. Fail loudly if it slips.
SELECT
    player_id,
    current_market_value_eur
FROM {{ ref('mart_shortlist') }}
WHERE current_market_value_eur > {{ var('max_market_value_eur') }}
