select
    p.player_id,
    p.player_name,
    p.date_of_birth,
    datediff('day', p.date_of_birth, date '{{ var("as_of_date") }}') / 365.25 as age,
    p.position_group,
    p.sub_position,
    p.foot,
    p.height_in_cm,
    p.country_of_citizenship,
    p.current_club_id,
    p.current_club_name,
    p.competition_id,
    lt.league_name,
    lt.tier,
    lt.strength_coef,
    c.contract_expiration_date,
    c.contract_months_remaining,
    c.contract_status,
    p.current_market_value_eur,
    p.highest_market_value_eur,
    p.current_market_value_eur * {{ var('fee_multiplier') }} as estimated_fee_eur
from {{ ref('stg_tm__players') }} p
left join {{ ref('int_contract_status') }} c using (player_id)
left join {{ ref('league_tiers') }} lt on p.competition_id = lt.competition_id
