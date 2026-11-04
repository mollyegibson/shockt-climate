/*
Feeder origins' container voyages to other countries by start month, origin country, start port and
hub (end) port: the first leg of cargo that transships at a hub before sailing to the US (plan
section 5.7.1). `share` is the hub's share of the origin's feeder voyages in the month. A voyage
stands for where the origin's container ships call next, not where their cargo goes on to.
`hub_has_us_voyages` says whether the hub port starts any loaded container voyage to the US, so
the onward leg can be observed rather than modelled.
*/
with feeder as (
    select
        date_trunc('month', started_at)::date as month,
        start_iso3 as origin_iso3,
        start_port_id,
        end_port_id as hub_port_id,
        end_port,
        end_iso3 as hub_iso3,
        distance_km,
        duration_h
    from {{ ref('stg_climatetrace_feeder_voyages') }}
    where {{ is_container_ship('vessel_type') }}
        and start_port_id is not null
        and end_port_id is not null
),

hub_names as (
    select distinct on (hub_port_id) hub_port_id, end_port as hub_port
    from feeder
    where end_port is not null
    group by hub_port_id, end_port
    order by hub_port_id, count(*) desc, end_port
),

us_hubs as (
    select distinct start_port_id as hub_port_id
    from {{ ref('stg_climatetrace_voyages') }}
    where end_iso3 = 'USA' and {{ is_container_ship('vessel_type') }}
),

lanes as (
    select
        month,
        origin_iso3,
        start_port_id,
        hub_port_id,
        hub_iso3,
        count(*) as n_voyages,
        percentile_cont(0.5) within group (order by distance_km) as median_distance_km,
        avg(duration_h) as mean_duration_h
    from feeder
    group by month, origin_iso3, start_port_id, hub_port_id, hub_iso3
)

select
    lanes.month,
    lanes.origin_iso3,
    lanes.start_port_id,
    lanes.hub_port_id,
    hub_names.hub_port,
    lanes.hub_iso3,
    lanes.n_voyages,
    lanes.n_voyages::numeric / sum(lanes.n_voyages) over (partition by lanes.month, lanes.origin_iso3) as share,
    lanes.median_distance_km,
    lanes.mean_duration_h,
    us_hubs.hub_port_id is not null as hub_has_us_voyages
from lanes
left join hub_names using (hub_port_id)
left join us_hubs using (hub_port_id)
