-- Vessel and air weight summed over ports should match the country-level total for the same month,
-- HS-6 and country, within 1% or 1 tonne. Only months loaded for both endpoints are compared.
{{ config(severity='warn') }}

with ports as (
    select month, hs6, census_cty_code, mode, sum(weight_t) as port_weight_t
    from {{ ref('fct_imports_port_monthly') }}
    where mode in ('air', 'vessel')
    group by 1, 2, 3, 4
),

countries as (
    select month, hs6, census_cty_code, mode, sum(weight_t) as country_weight_t
    from {{ ref('fct_imports_monthly') }}
    where mode in ('air', 'vessel')
    group by 1, 2, 3, 4
),

shared_months as (
    select distinct month from {{ ref('fct_imports_monthly') }}
    intersect
    select distinct month from {{ ref('fct_imports_port_monthly') }}
)

select
    countries.*,
    coalesce(ports.port_weight_t, 0) as port_weight_t
from countries
join shared_months using (month)
left join ports using (month, hs6, census_cty_code, mode)
where countries.census_cty_code in (
        select census_cty_code from {{ ref('dim_country') }} where region in ('asia', 'mexico')
    )
    and abs(countries.country_weight_t - coalesce(ports.port_weight_t, 0))
        > greatest(1, 0.01 * countries.country_weight_t)
