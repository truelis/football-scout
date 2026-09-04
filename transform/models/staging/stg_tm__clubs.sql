select
    club_id,
    name                                        as club_name,
    domestic_competition_id                     as competition_id,
    total_market_value                          as squad_market_value_eur,
    squad_size,
    average_age
from {{ source('tm', 'clubs') }}
