-- The price filter is the whole point of the tool. Fail loudly if it slips.
select player_id, current_market_value_eur
from {{ ref('mart_shortlist') }}
where current_market_value_eur > {{ var('max_market_value_eur') }}
