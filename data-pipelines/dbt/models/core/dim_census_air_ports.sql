/*
Census ports with air imports of the case HS codes, each placed at an OurAirports airport.

A port whose name names an airport (it contains a word such as AIRPORT or INTL) is matched to the
airport whose name contains, or whose municipality is, the rest of that segment, in the port's state
when the name has one. Any other port is a city port: it is geocoded to its GeoNames city and placed
at the nearest large airport within `air_port_city_radius_km`, in any state, or else the nearest
airport of any size. A city port GeoNames doesn't have (territories, or "NEW YORK", which GeoNames
calls New York City) is matched to an airport in its state whose municipality is the city. Ports
with no match keep null coordinates and are left out of the nodes.
*/
{% set airport_words = "AIRPORT|AIRPRT|ARPT|AIRPT|AIRP|INTERNATIONAL|INTL|INT''L|METRO|CORP" %}

with air as (
    select port_code, sum(weight_t) as air_weight_t
    from {{ ref('fct_imports_port_monthly') }}
    where mode = 'air'
    group by port_code
    having sum(weight_t) > 0
),

parsed as (
    select
        air.port_code,
        air.air_weight_t,
        port.port_name,
        regexp_match(upper(port.port_name), '^(.*?)[,.]\s*([A-Z])\.?([A-Z])\.?\s*(\(.*\))?$') as parts
    from air
    left join {{ ref('dim_port') }} as port using (port_code)
),

ports as (
    select
        port_code,
        air_weight_t,
        port_name,
        parts[2] || parts[3] as state,
        coalesce(parts[1], upper(port_name)) as place
    from parsed
),

segments as (
    select
        ports.port_code,
        ports.state,
        segment ~ '\m({{ airport_words }})\M' as names_airport,
        {{ normalize_place("regexp_replace(segment, '\\m(" ~ airport_words ~ ")\\M', ' ', 'g')") }} as token,
        segment_number = array_length(string_to_array(ports.place, ','), 1) as is_city
    from ports,
        unnest(string_to_array(ports.place, ',')) with ordinality as s (segment, segment_number)
),

named as (
    select distinct on (segments.port_code)
        segments.port_code,
        airport.iata_code
    from segments
    inner join {{ ref('stg_ourairports_airports') }} as airport
        on (segments.state is null or airport.state = segments.state)
        and (
            airport.name_normalized like '%' || segments.token || '%'
            or airport.municipality_normalized = segments.token
        )
    where segments.names_airport and length(segments.token) >= 4
    order by
        segments.port_code,
        airport.municipality_normalized = segments.token desc,
        airport.type = 'large_airport' desc,
        airport.iata_code
),

geocoded as (
    select distinct on (segments.port_code)
        segments.port_code,
        city.lat,
        city.lon
    from segments
    inner join {{ ref('stg_geonames_cities') }} as city
        on city.country_code = 'US'
        and city.admin1_code = segments.state
        and city.name_normalized in (segments.token, split_part(segments.token, ' ', 1))
    where segments.is_city and segments.port_code not in (select port_code from named)
    order by segments.port_code, city.name_normalized = segments.token desc, city.population desc
),

near_city as (
    select
        geocoded.port_code,
        airport.iata_code,
        airport.city_to_airport_km,
        airport.is_large_within_radius
    from geocoded
    cross join lateral (
        select
            candidate.iata_code,
            distance.km as city_to_airport_km,
            candidate.type = 'large_airport'
                and distance.km <= {{ var('air_port_city_radius_km') }} as is_large_within_radius
        from {{ ref('stg_ourairports_airports') }} as candidate
        cross join lateral (
            select {{ dbt_utils.haversine_distance('geocoded.lat', 'geocoded.lon', 'candidate.lat', 'candidate.lon', unit='km') }} as km
        ) as distance
        order by is_large_within_radius desc, distance.km
        limit 1
    ) as airport
),

in_municipality as (
    select distinct on (segments.port_code)
        segments.port_code,
        airport.iata_code
    from segments
    inner join {{ ref('stg_ourairports_airports') }} as airport
        on airport.state = segments.state
        and airport.municipality_normalized = segments.token
    where segments.is_city
        and segments.port_code not in (select port_code from named)
        and segments.port_code not in (select port_code from geocoded)
    order by segments.port_code, airport.type = 'large_airport' desc, airport.iata_code
)

select
    ports.port_code,
    ports.port_name,
    ports.state,
    ports.air_weight_t,
    ports.air_weight_t / sum(ports.air_weight_t) over () as air_weight_share,
    airport.iata_code,
    airport.name as airport_name,
    airport.lat,
    airport.lon,
    case
        when named.port_code is not null then 'airport_name'
        when near_city.is_large_within_radius then 'large_near_city'
        when near_city.port_code is not null then 'nearest_to_city'
        when in_municipality.port_code is not null then 'city_municipality'
        else 'unmatched'
    end as match_method,
    near_city.city_to_airport_km
from ports
left join named using (port_code)
left join near_city using (port_code)
left join in_municipality using (port_code)
left join {{ ref('stg_ourairports_airports') }} as airport
    on airport.iata_code = coalesce(named.iata_code, near_city.iata_code, in_municipality.iata_code)
