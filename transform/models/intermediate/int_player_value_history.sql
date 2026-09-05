-- Market value time series with trailing deltas, evaluated as of var('as_of_date').
-- Every window is bounded by as_of_date so the Phase 3 backtest can rewind
-- this model without leaking future values.
WITH vals AS (
    SELECT *
    FROM {{ ref('stg_tm__player_valuations') }}
    WHERE valuation_date <= DATE '{{ var("as_of_date") }}'
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY valuation_date DESC) AS rn
    FROM vals
),

current_value AS (
    SELECT
        player_id,
        market_value_eur AS value_now,
        valuation_date AS value_now_date
    FROM ranked
    WHERE rn = 1
),

value_12m AS (
    SELECT DISTINCT ON (player_id)
        player_id,
        market_value_eur AS value_12m_ago
    FROM vals
    WHERE valuation_date <= DATE '{{ var("as_of_date") }}' - INTERVAL 12 MONTH
    ORDER BY player_id ASC, valuation_date DESC
),

value_24m AS (
    SELECT DISTINCT ON (player_id)
        player_id,
        market_value_eur AS value_24m_ago
    FROM vals
    WHERE valuation_date <= DATE '{{ var("as_of_date") }}' - INTERVAL 24 MONTH
    ORDER BY player_id ASC, valuation_date DESC
),

peak AS (
    SELECT
        player_id,
        MAX(market_value_eur) AS peak_value
    FROM vals
    GROUP BY player_id
)

SELECT
    c.player_id,
    c.value_now,
    c.value_now_date,
    v12.value_12m_ago,
    v24.value_24m_ago,
    p.peak_value,
    CASE
        WHEN v12.value_12m_ago > 0
            THEN c.value_now / v12.value_12m_ago - 1
    END AS value_growth_12m,
    CASE
        WHEN v24.value_24m_ago > 0
            THEN POWER(c.value_now / v24.value_24m_ago, 0.5) - 1
    END AS value_cagr_24m,
    CASE
        WHEN p.peak_value > 0
            THEN c.value_now / p.peak_value
    END AS value_vs_peak
FROM current_value AS c
LEFT JOIN value_12m AS v12 USING (player_id)
LEFT JOIN value_24m AS v24 USING (player_id)
LEFT JOIN peak AS p USING (player_id)
