/*
Ports the main sea leg to the US starts from: Climate TRACE start ports in the origin countries that
container ships sailed from to the US (`is_us_departure`), each at the median start point of those
voyages, and the hub ports the feeder origins' container ships sail to (`is_feeder_hub`), each at
the median end point of the feeder voyages. A port can be both, and is then placed by its US
departures. Only US voyages whose end point doesn't contradict their end port count, the same as
`fct_voyages`.
*/
with origin_countries as (
    select distinct iso3
    from {{ ref('dim_country') }}
    where region <> 'other' and iso3 is not null
),

departures as (
    select v.start_port_id as port_id, v.start_port as port, v.start_iso3 as iso3, v.start_lon as lon, v.start_lat as lat
    from {{ ref('stg_climatetrace_voyages') }} as v
    inner join origin_countries on origin_countries.iso3 = v.start_iso3
    where v.end_iso3 = 'USA'
        and {{ is_container_ship('v.vessel_type') }}
        and not v.end_point_contradicts_end_port
        and v.start_lon is not null
),

hubs as (
    select v.end_port_id as port_id, v.end_port as port, v.end_iso3 as iso3, v.end_lon as lon, v.end_lat as lat
    from {{ ref('stg_climatetrace_feeder_voyages') }} as v
    where {{ is_container_ship('v.vessel_type') }}
        and v.end_port_id is not null
        and v.end_lon is not null
),

ports as (
    select 'departure' as role, * from departures
    union all
    select 'hub' as role, * from hubs
),

names as (
    select distinct on (port_id) port_id, port as port_name
    from ports
    where port is not null
    group by port_id, port
    order by port_id, bool_or(role = 'departure') desc, count(*) desc, port
),

placed as (
    select
        port_id,
        bool_or(role = 'departure') as is_us_departure,
        bool_or(role = 'hub') as is_feeder_hub,
        min(iso3) as iso3,
        count(*) filter (where role = 'departure') as container_voyages,
        count(*) filter (where role = 'hub') as feeder_voyages,
        coalesce(
            percentile_cont(0.5) within group (order by lon) filter (where role = 'departure'),
            percentile_cont(0.5) within group (order by lon)
        ) as lon,
        coalesce(
            percentile_cont(0.5) within group (order by lat) filter (where role = 'departure'),
            percentile_cont(0.5) within group (order by lat)
        ) as lat
    from ports
    group by port_id
)

select
    placed.port_id as start_port_id,
    names.port_name,
    placed.iso3,
    placed.lon,
    placed.lat,
    placed.container_voyages,
    placed.feeder_voyages,
    placed.is_us_departure,
    placed.is_feeder_hub
from placed
left join names using (port_id)
