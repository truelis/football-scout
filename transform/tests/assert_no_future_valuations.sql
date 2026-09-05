-- Leakage guard. The value history model must never see past as_of_date.
-- Phase 3's backtest depends entirely on this holding.
SELECT
    player_id,
    value_now_date
FROM {{ ref('int_player_value_history') }}
WHERE value_now_date > DATE '{{ var("as_of_date") }}'
