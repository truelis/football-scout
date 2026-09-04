select
    competition_id,
    name                                        as competition_name,
    country_name,
    type                                        as competition_type,
    sub_type,
    is_major_national_league
from {{ source('tm', 'competitions') }}
