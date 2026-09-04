select
    player_id,
    date                                        as valuation_date,
    market_value_in_eur                         as market_value_eur,
    current_club_id,
    player_club_domestic_competition_id         as competition_id
from {{ source('tm', 'player_valuations') }}
where market_value_in_eur is not null
