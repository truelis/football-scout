-- Contract runway as of var('as_of_date'). One of the strongest and cheapest
-- signals in the dataset: under ~18 months, the selling club loses leverage.
select
    player_id,
    contract_expiration_date,
    case when contract_expiration_date is not null
         then datediff('month', date '{{ var("as_of_date") }}', contract_expiration_date)
    end as contract_months_remaining,
    case
        when contract_expiration_date is null then 'unknown'
        when datediff('month', date '{{ var("as_of_date") }}', contract_expiration_date)
             <= {{ var('contract_bargain_months') }} then 'expiring'
        when datediff('month', date '{{ var("as_of_date") }}', contract_expiration_date)
             <= {{ var('contract_leverage_months') }} then 'leverage'
        else 'secure'
    end as contract_status
from {{ ref('stg_tm__players') }}
