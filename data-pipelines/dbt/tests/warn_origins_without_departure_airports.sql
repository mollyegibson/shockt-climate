-- Origin countries with case air tonnage but no placed departure airport in T-100, so their air legs have no start and are left out.
{{ config(severity='warn') }}

select country.iso3, sum(air.weight_t) as air_weight_t
from {{ ref('fct_imports_monthly') }} as air
inner join {{ ref('dim_country') }} as country using (census_cty_code)
where air.mode = 'air'
    and air.weight_t > 0
    and country.region <> 'other'
    and country.iso3 not in (select iso3 from {{ ref('dim_departure_airports') }} where lat is not null)
group by country.iso3
