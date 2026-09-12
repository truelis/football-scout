-- LEAKAGE GUARD. dim_player's market value must come from the valuation time
-- series as it stood at as_of_date, never from players.market_value_in_eur.
--
-- That source column is a CURRENT snapshot. At today's as_of_date it agrees with
-- the time series exactly, so the leak is invisible in normal running - and then
-- ruins any backtest silently. Rebuilt at 2023, it would filter on a player's
-- 2026 value: anyone who has since become expensive is excluded, and anyone
-- whose value has since collapsed is included. The second case is fatal, because
-- the model would appear to "find" players by knowing their future.
--
-- CLAUDE.md rule 3: write the leakage test before the backtest.
WITH as_of_value AS (
    SELECT DISTINCT ON (player_id)
        player_id,
        market_value_eur
    FROM {{ ref('stg_tm__player_valuations') }}
    WHERE valuation_date <= DATE '{{ var("as_of_date") }}'
    ORDER BY player_id ASC, valuation_date DESC
)

SELECT
    d.player_id,
    d.player_name,
    d.current_market_value_eur AS used_by_model,
    v.market_value_eur AS correct_as_of_value
FROM {{ ref('dim_player') }} AS d
INNER JOIN as_of_value AS v ON d.player_id = v.player_id
WHERE d.current_market_value_eur IS DISTINCT FROM v.market_value_eur
