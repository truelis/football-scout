-- Rename and cast only. No business logic.
select
    player_id,
    name                                        as player_name,
    date_of_birth,
    position                                    as position_group,
    sub_position,
    foot,
    height_in_cm,
    country_of_citizenship,
    current_club_id,
    current_club_name,
    current_club_domestic_competition_id        as competition_id,
    contract_expiration_date,
    market_value_in_eur                         as current_market_value_eur,
    highest_market_value_in_eur                 as highest_market_value_eur,
    last_season
from {{ source('tm', 'players') }}
where player_id is not null
