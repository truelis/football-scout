-- Leakage guard. The value history model must never see past as_of_date.
-- Phase 3's backtest depends entirely on this holding.
select player_id, value_now_date
from {{ ref('int_player_value_history') }}
where value_now_date > date '{{ var("as_of_date") }}'
