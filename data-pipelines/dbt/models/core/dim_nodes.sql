/*
Every place a leg starts or ends, one row per node, from the location models: departure ports and
airports in the origin countries, US arrival seaports, air gateways and border crossings, the
Mexican plants crossings' legs start at, and US destination states. `node_id` is the kind and the
key in the source it came from. Only nodes with coordinates are kept.
*/
with vessel_ports as (
    select distinct port_code
    from {{ ref('fct_imports_port_monthly') }}
    where mode = 'vessel' and weight_t > 0
),

crossings as (
    select distinct port_code
    from {{ ref('fct_mexico_overland_monthly') }}
    where weight_t > 0
),

nodes as (
    select
        'departure_port' as kind,
        start_port_id as source_key,
        port_name as name,
        iso3,
        lat,
        lon,
        null::text as coast_region,
        'median_voyage_start' as location_method
    from {{ ref('dim_departure_ports') }}

    union all

    select
        'departure_airport',
        iata_code,
        airport_name,
        iso3,
        lat,
        lon,
        null,
        'ourairports'
    from {{ ref('dim_departure_airports') }}

    union all

    select
        'arrival_seaport',
        port.port_code,
        port.port_name,
        'USA',
        port.lat,
        port.lon,
        port.coast_region,
        port.location_method
    from {{ ref('dim_port') }} as port
    inner join vessel_ports using (port_code)
    where not port.is_border_crossing

    union all

    select
        'air_gateway',
        gateway.port_code,
        gateway.airport_name,
        'USA',
        gateway.lat,
        gateway.lon,
        port.coast_region,
        gateway.match_method
    from {{ ref('dim_census_air_ports') }} as gateway
    left join {{ ref('dim_port') }} as port using (port_code)

    union all

    select
        'border_crossing',
        port.port_code,
        port.port_name,
        'USA',
        port.lat,
        port.lon,
        port.coast_region,
        port.location_method
    from {{ ref('dim_port') }} as port
    inner join crossings using (port_code)
    where port.is_border_crossing

    union all

    select
        'mexico_plant',
        plant.plant_id::text,
        plant.name,
        'MEX',
        plant.lat,
        plant.lon,
        null,
        'denue'
    from {{ ref('dim_mexico_plants') }} as plant
    where plant.plant_id in (select plant_id from {{ ref('map_crossing_plant') }})

    union all

    select
        'destination_state',
        state,
        state || ' (' || town || ')',
        'USA',
        lat,
        lon,
        {{ coast_region('lon', 'lat') }},
        'geonames_town_nearest_population_centre'
    from {{ ref('dim_destination_states') }}
)

select
    kind || ':' || source_key as node_id,
    kind,
    name,
    iso3,
    lat,
    lon,
    coast_region,
    location_method,
    source_key
from nodes
where lat is not null and lon is not null
