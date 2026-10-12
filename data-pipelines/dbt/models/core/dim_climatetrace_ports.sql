-- US arrival ports in the Climate TRACE voyages: location, most common name, coast region and voyage counts, from voyages whose end point doesn't contradict their end port.
with arrivals as (
    select end_port_id, end_port, end_lon, end_lat, vessel_type
    from {{ ref('stg_climatetrace_voyages') }}
    where end_iso3 = 'USA' and not end_point_contradicts_end_port
),

names as (
    select distinct on (end_port_id) end_port_id, end_port as port_name
    from arrivals
    where end_port is not null
    group by end_port_id, end_port
    order by end_port_id, count(*) desc, end_port
),

ports as (
    select
        end_port_id,
        percentile_cont(0.5) within group (order by end_lon) as lon,
        percentile_cont(0.5) within group (order by end_lat) as lat,
        count(*) as voyages,
        count(*) filter (where {{ is_container_ship('vessel_type') }}) as container_voyages
    from arrivals
    group by end_port_id
)

select
    ports.end_port_id,
    names.port_name,
    ports.lon,
    ports.lat,
    {{ coast_region('ports.lon', 'ports.lat') }} as coast_region,
    ports.voyages,
    ports.container_voyages
from ports
left join names using (end_port_id)
