-- Market value time series with trailing deltas, evaluated as of var('as_of_date').
-- Every window is bounded by as_of_date so the Phase 3 backtest can rewind
-- this model without leaking future values.
with vals as (
    select *
    from {{ ref('stg_tm__player_valuations') }}
    where valuation_date <= date '{{ var("as_of_date") }}'
),

ranked as (
    select
        *,
        row_number() over (partition by player_id order by valuation_date desc) as rn
    from vals
),

current_value as (
    select player_id, market_value_eur as value_now, valuation_date as value_now_date
    from ranked where rn = 1
),

value_12m as (
    select distinct on (player_id)
        player_id, market_value_eur as value_12m_ago
    from vals
    where valuation_date <= date '{{ var("as_of_date") }}' - interval 12 month
    order by player_id, valuation_date desc
),

value_24m as (
    select distinct on (player_id)
        player_id, market_value_eur as value_24m_ago
    from vals
    where valuation_date <= date '{{ var("as_of_date") }}' - interval 24 month
    order by player_id, valuation_date desc
),

peak as (
    select player_id, max(market_value_eur) as peak_value
    from vals group by 1
)

select
    c.player_id,
    c.value_now,
    c.value_now_date,
    v12.value_12m_ago,
    v24.value_24m_ago,
    p.peak_value,
    case when v12.value_12m_ago > 0
         then c.value_now / v12.value_12m_ago - 1 end       as value_growth_12m,
    case when v24.value_24m_ago > 0
         then power(c.value_now / v24.value_24m_ago, 0.5) - 1 end as value_cagr_24m,
    case when p.peak_value > 0
         then c.value_now / p.peak_value end                as value_vs_peak
from current_value c
left join value_12m v12 using (player_id)
left join value_24m v24 using (player_id)
left join peak      p   using (player_id)
