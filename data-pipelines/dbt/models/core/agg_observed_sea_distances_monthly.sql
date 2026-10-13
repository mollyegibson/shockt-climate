/*
Observed sea distance by month, origin country and US arrival seaport: the container voyages from
the origin whose end point lies within `arrival_ports.voyage_radius_km` (config/transforms.yaml) of
the Census port's point, by start month. A voyage can count for two nearby ports, such as Los
Angeles and Long Beach, which then get nearly the same distance. Ports with no such voyage get no
row; their distance falls back to `searoute`.
*/
with voyages as (
    select
        date_trunc('month', v.started_at)::date as month,
        v.start_iso3 as origin_iso3,
        v.end_lat,
        v.end_lon,
        v.distance_km,
        v.duration_h
    from {{ ref('stg_climatetrace_voyages') }} as v
    inner join {{ ref('dim_departure_ports') }} using (start_port_id)
    where v.end_iso3 = 'USA'
        and {{ is_container_ship('v.vessel_type') }}
        and not v.end_point_contradicts_end_port
        and v.end_lat is not null
),

ports as (
    select node_id, lat, lon
    from {{ ref('dim_nodes') }}
    where kind = 'arrival_seaport'
)

select
    voyages.month,
    voyages.origin_iso3,
    ports.node_id as arrival_node_id,
    count(*) as n_voyages,
    percentile_cont(0.5) within group (order by voyages.distance_km) as median_distance_km,
    avg(voyages.duration_h) as mean_duration_h
from voyages
inner join ports
    on {{ dbt_utils.haversine_distance('voyages.end_lat', 'voyages.end_lon', 'ports.lat', 'ports.lon', unit='km') }}
        <= {{ var('arrival_ports')['voyage_radius_km'] }}
group by voyages.month, voyages.origin_iso3, ports.node_id
