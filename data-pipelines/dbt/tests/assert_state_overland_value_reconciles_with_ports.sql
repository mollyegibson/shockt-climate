-- Overland (`other`) value summed over states of destination should match the same value summed
-- over ports, for the same month, HS-6 and country, within 1% or $1. The two Census endpoints report
-- the same imports, so a gap means one of them was loaded or modeled wrong. Only months loaded for
-- both endpoints are compared.
with states as (
    select month, hs6, census_cty_code, sum(value_usd) as state_value_usd
    from {{ ref('fct_imports_state_monthly') }}
    where mode = 'other'
    group by 1, 2, 3
),

ports as (
    select month, hs6, census_cty_code, sum(value_usd) as port_value_usd
    from {{ ref('fct_imports_port_monthly') }}
    where mode = 'other'
    group by 1, 2, 3
),

shared_months as (
    select distinct month from {{ ref('fct_imports_state_monthly') }}
    intersect
    select distinct month from {{ ref('fct_imports_port_monthly') }}
)

select
    month,
    hs6,
    census_cty_code,
    coalesce(states.state_value_usd, 0) as state_value_usd,
    coalesce(ports.port_value_usd, 0) as port_value_usd
from states
full join ports using (month, hs6, census_cty_code)
join shared_months using (month)
where census_cty_code in (
        select census_cty_code from {{ ref('dim_country') }} where region <> 'other'
    )
    and abs(coalesce(states.state_value_usd, 0) - coalesce(ports.port_value_usd, 0))
        > greatest(1, 0.01 * greatest(states.state_value_usd, ports.port_value_usd))
