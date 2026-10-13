-- US states of destination with case imports, each at the population-weighted centre of its GeoNames cities. States GeoNames has no cities for (territories under their own country code) are left out.
with states as (
    select distinct state
    from {{ ref('fct_imports_state_monthly') }}
    where state <> 'XX'
)

select
    states.state,
    sum(city.lat * city.population) / sum(city.population) as lat,
    sum(city.lon * city.population) / sum(city.population) as lon,
    sum(city.population) as population,
    count(*) as cities
from states
inner join {{ ref('stg_geonames_cities') }} as city
    on city.country_code = 'US' and city.admin1_code = states.state
where city.population > 0
group by states.state
