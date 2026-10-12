/*
Census ports with air imports of the case HS codes, each placed at an OurAirports airport.

A port whose name names an airport is placed at that airport. Any other port is a city port: it is
placed at the nearest large airport within `air_ports.city_radius_km` (config/transforms.yaml) of
its GeoNames city, in any state, or else the nearest airport of any size. A city port GeoNames
doesn't have is placed at an airport in its state whose municipality is the city. The name, city
and municipality matches come from dim_port. Ports with no match keep null coordinates and are left
out of the nodes.
*/
with air as (
    select port_code, sum(weight_t) as air_weight_t
    from {{ ref('fct_imports_port_monthly') }}
    where mode = 'air'
    group by port_code
    having sum(weight_t) > 0
),

ports as (
    select
        air.port_code,
        air.air_weight_t,
        port.port_name,
        port.state,
        port.named_airport_iata,
        port.city_lat,
        port.city_lon,
        port.municipality_airport_iata
    from air
    left join {{ ref('dim_port') }} as port using (port_code)
),

near_city as (
    select
        ports.port_code,
        airport.iata_code,
        airport.city_to_airport_km,
        airport.is_large_within_radius
    from ports
    cross join lateral (
        select
            candidate.iata_code,
            distance.km as city_to_airport_km,
            candidate.type = 'large_airport'
                and distance.km <= {{ var('air_ports')['city_radius_km'] }} as is_large_within_radius
        from {{ ref('stg_ourairports_airports') }} as candidate
        cross join lateral (
            select {{ dbt_utils.haversine_distance('ports.city_lat', 'ports.city_lon', 'candidate.lat', 'candidate.lon', unit='km') }} as km
        ) as distance
        order by is_large_within_radius desc, distance.km
        limit 1
    ) as airport
    where ports.named_airport_iata is null and ports.city_lat is not null
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
        when ports.named_airport_iata is not null then 'airport_name'
        when near_city.is_large_within_radius then 'large_near_city'
        when near_city.port_code is not null then 'nearest_to_city'
        when ports.municipality_airport_iata is not null then 'city_municipality'
        else 'unmatched'
    end as match_method,
    near_city.city_to_airport_km
from ports
left join near_city using (port_code)
left join {{ ref('stg_ourairports_airports') }} as airport
    on airport.iata_code = coalesce(
        ports.named_airport_iata, near_city.iata_code, ports.municipality_airport_iata
    )
