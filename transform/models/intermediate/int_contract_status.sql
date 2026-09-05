-- Contract runway as of var('as_of_date'). One of the strongest and cheapest
-- signals in the dataset: under ~18 months, the selling club loses leverage.
SELECT
    player_id,
    contract_expiration_date,
    CASE
        WHEN contract_expiration_date IS NOT NULL
            THEN DATEDIFF('month', DATE '{{ var("as_of_date") }}', contract_expiration_date)
    END AS contract_months_remaining,
    CASE
        WHEN contract_expiration_date IS NULL THEN 'unknown'
        WHEN
            DATEDIFF('month', DATE '{{ var("as_of_date") }}', contract_expiration_date)
            <= {{ var('contract_bargain_months') }} THEN 'expiring'
        WHEN
            DATEDIFF('month', DATE '{{ var("as_of_date") }}', contract_expiration_date)
            <= {{ var('contract_leverage_months') }} THEN 'leverage'
        ELSE 'secure'
    END AS contract_status
FROM {{ ref('stg_tm__players') }}
