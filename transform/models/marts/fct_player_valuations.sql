-- Full market-value time series per player, for charting in the app.
-- Bounded by as_of_date so the backtest sees a consistent world.
select
    player_id,
    valuation_date,
    market_value_eur,
    competition_id
from {{ ref('stg_tm__player_valuations') }}
where valuation_date <= date '{{ var("as_of_date") }}'
