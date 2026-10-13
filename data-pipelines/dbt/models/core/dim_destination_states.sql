/*
US states of destination with case imports, each placed at the GeoNames town nearest the
population-weighted centre of its cities. The centre alone can land far from any road where a
state has two population centres (Nevada's between Las Vegas and Reno), so the town keeps every
state on the road and rail networks. States GeoNames has no cities for (territories under their own
country code) are left out.
*/
with states as (
    select distinct state
    from {{ ref('fct_imports_state_monthly') }}
    where state <> 'XX'
),

cities as (
    select city.admin1_code as state, city.name, city.lat, city.lon, city.population
    from {{ ref('stg_geonames_cities') }} as city
    inner join states on states.state = city.admin1_code
    where city.country_code = 'US' and city.population > 0
),

centres as (
    select
        state,
        sum(lat * population) / sum(population) as centre_lat,
        sum(lon * population) / sum(population) as centre_lon,
        sum(population) as population,
        count(*) as cities
    from cities
    group by state
)

select
    centres.state,
    town.name as town,
    town.lat,
    town.lon,
    centres.centre_lat,
    centres.centre_lon,
    town.km as centre_to_town_km,
    centres.population,
    centres.cities
from centres
cross join lateral (
    select cities.name, cities.lat, cities.lon, distance.km
    from cities
    cross join lateral (
        select {{ dbt_utils.haversine_distance('centres.centre_lat', 'centres.centre_lon', 'cities.lat', 'cities.lon', unit='km') }} as km
    ) as distance
    where cities.state = centres.state
    order by distance.km, cities.name
    limit 1
) as town
