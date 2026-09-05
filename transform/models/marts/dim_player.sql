SELECT
    p.player_id,
    p.player_name,
    p.date_of_birth,
    DATEDIFF('day', p.date_of_birth, DATE '{{ var("as_of_date") }}') / 365.25 AS age,
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
    p.current_market_value_eur * {{ var('fee_multiplier') }} AS estimated_fee_eur
FROM {{ ref('stg_tm__players') }} AS p
LEFT JOIN {{ ref('int_contract_status') }} AS c USING (player_id)
LEFT JOIN {{ ref('league_tiers') }} AS lt ON p.competition_id = lt.competition_id
