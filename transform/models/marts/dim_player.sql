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
    -- AS-OF value from the valuation time series, NOT players.market_value_in_eur.
    -- That column is a current snapshot: identical to this at today's as_of_date,
    -- and silently wrong at every past one. See
    -- tests/assert_market_value_is_as_of.sql.
    v.value_now AS current_market_value_eur,
    -- Peak value AS OF the date too - players.highest_market_value_in_eur is a
    -- lifetime maximum that can sit in the future.
    v.peak_value AS highest_market_value_eur,
    v.value_now * {{ var('fee_multiplier') }} AS estimated_fee_eur
FROM {{ ref('stg_tm__players') }} AS p
LEFT JOIN {{ ref('int_contract_status') }} AS c USING (player_id)
LEFT JOIN {{ ref('int_player_value_history') }} AS v USING (player_id)
LEFT JOIN {{ ref('league_tiers') }} AS lt ON p.competition_id = lt.competition_id
