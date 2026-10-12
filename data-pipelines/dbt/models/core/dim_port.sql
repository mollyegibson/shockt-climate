/*
Census ports (Schedule D), plus any port code seen in the trade data but missing from the schedule,
each placed at a point and given a coast region by `coast_region`, the same rule as the Climate
TRACE ports.

A port's point is, in order: its US–Mexico crossing in BTS Border Crossing Entry Data; the
OurAirports airport its name names (a name containing a word such as AIRPORT or INTL, matched on
the rest of that segment, in the port's state when the name has one); its city in GeoNames, in the
port's state; or an airport in its state whose municipality is the city, for cities GeoNames lacks
(territories, or "NEW YORK", which GeoNames calls New York City). A port with no point is
`unknown`. The city and airport matches are kept as columns for `dim_census_air_ports`.
*/
{% set airport_words = "AIRPORT|AIRPRT|ARPT|AIRPT|AIRP|INTERNATIONAL|INTL|INT''L|METRO|CORP" %}

with schedule as (
    select port_code, port_name
    from {{ ref('seed_census_ports') }}
),

seen as (
    select port_code, max(port_name) as port_name
    from (
        select port as port_code, port_name from {{ source('raw', 'census_porths') }}
        union all
        select district_unlading || port_unlading, null from {{ source('raw', 'census_state_port') }}
        union all
        select district_entry || port_entry, null from {{ source('raw', 'census_state_port') }}
        union all
        select depe, null from {{ source('raw', 'bts_transborder') }} where depe is not null
    ) as codes
    where port_code ~ '^[0-9]{4}$'
    group by port_code
),

ports as (
    select
        coalesce(schedule.port_code, seen.port_code) as port_code,
        coalesce(schedule.port_name, seen.port_name) as port_name,
        schedule.port_code is null as missing_from_schedule
    from schedule
    full outer join seen using (port_code)
),

parsed as (
    select
        ports.*,
        regexp_match(upper(ports.port_name), '^(.*?)[,.]\s*([A-Z])\.?([A-Z])\.?\s*(\(.*\))?$') as parts
    from ports
),

named_parts as (
    select
        port_code,
        port_name,
        missing_from_schedule,
        parts[2] || parts[3] as state,
        coalesce(parts[1], upper(port_name)) as place
    from parsed
),

segments as (
    select
        named_parts.port_code,
        named_parts.state,
        segment ~ '\m({{ airport_words }})\M' as names_airport,
        {{ normalize_place("regexp_replace(segment, '\\m(" ~ airport_words ~ ")\\M', ' ', 'g')") }} as token,
        segment_number = array_length(string_to_array(named_parts.place, ','), 1) as is_city
    from named_parts,
        unnest(string_to_array(named_parts.place, ',')) with ordinality as s (segment, segment_number)
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
    where segments.is_city
    order by segments.port_code, city.name_normalized = segments.token desc, city.population desc
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
    order by segments.port_code, airport.type = 'large_airport' desc, airport.iata_code
),

crossings as (
    select distinct on (crossing.port_code)
        crossing.port_code,
        crossing.latitude as lat,
        crossing.longitude as lon
    from {{ source('raw', 'bts_border_crossings') }} as crossing
    where crossing.load_id in ({{ succeeded_loads('bts_border_crossings') }})
        and crossing.latitude is not null
    order by crossing.port_code, crossing.date desc
),

located as (
    select
        named_parts.port_code,
        named_parts.port_name,
        named_parts.state,
        named_parts.missing_from_schedule,
        crossings.port_code is not null as is_border_crossing,
        named.iata_code as named_airport_iata,
        geocoded.lat as city_lat,
        geocoded.lon as city_lon,
        in_municipality.iata_code as municipality_airport_iata,
        coalesce(crossings.lat, named_airport.lat, geocoded.lat, municipality_airport.lat) as lat,
        coalesce(crossings.lon, named_airport.lon, geocoded.lon, municipality_airport.lon) as lon,
        case
            when crossings.port_code is not null then 'border_crossing'
            when named_airport.iata_code is not null then 'airport_name'
            when geocoded.port_code is not null then 'geonames_city'
            when municipality_airport.iata_code is not null then 'airport_municipality'
            else 'unmatched'
        end as location_method
    from named_parts
    left join crossings using (port_code)
    left join named using (port_code)
    left join geocoded using (port_code)
    left join in_municipality using (port_code)
    left join {{ ref('stg_ourairports_airports') }} as named_airport
        on named_airport.iata_code = named.iata_code
    left join {{ ref('stg_ourairports_airports') }} as municipality_airport
        on municipality_airport.iata_code = in_municipality.iata_code
)

select
    port_code,
    port_name,
    left(port_code, 2) as district_code,
    state,
    is_border_crossing,
    lat,
    lon,
    location_method,
    {{ coast_region('lon', 'lat') }} as coast_region,
    named_airport_iata,
    city_lat,
    city_lon,
    municipality_airport_iata,
    missing_from_schedule
from located
