-- Vessel and air weight summed over states of destination should match the country-level total for
-- the same month, HS-6 and country, within 1% or 1 tonne. Only month × HS-prefix partitions loaded
-- for both endpoints are compared. An all-states total row left in the state data doubles the sum and fails this test.
with states as (
    select month, hs6, census_cty_code, mode, sum(weight_t) as state_weight_t
    from {{ ref('fct_imports_state_monthly') }}
    where mode in ('air', 'vessel')
    group by 1, 2, 3, 4
),

countries as (
    select month, hs6, census_cty_code, mode, sum(weight_t) as country_weight_t
    from {{ ref('fct_imports_monthly') }}
    where mode in ('air', 'vessel')
    group by 1, 2, 3, 4
),

shared_partitions as (
    {{ shared_census_partitions('census_hs', 'census_statehs') }}
)

select
    countries.*,
    coalesce(states.state_weight_t, 0) as state_weight_t
from countries
left join states using (month, hs6, census_cty_code, mode)
where countries.census_cty_code in (
        select census_cty_code from {{ ref('dim_country') }} where region <> 'other'
    )
    and exists (
        select 1
        from shared_partitions as shared
        where shared.month = countries.month and countries.hs6 like shared.hs_prefix || '%'
    )
    and abs(countries.country_weight_t - coalesce(states.state_weight_t, 0))
        > greatest(1, 0.01 * countries.country_weight_t)
