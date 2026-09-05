-- Full market-value time series per player, for charting in the app.
-- Bounded by as_of_date so the backtest sees a consistent world.
SELECT
    player_id,
    valuation_date,
    market_value_eur,
    competition_id
FROM {{ ref('stg_tm__player_valuations') }}
WHERE valuation_date <= DATE '{{ var("as_of_date") }}'
