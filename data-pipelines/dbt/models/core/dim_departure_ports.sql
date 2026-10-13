/*
Ports in the origin countries that container ships sailed from to the US: Climate TRACE start
ports, each at the median start point of its voyages, with its most common name. Only voyages whose
end point doesn't contradict their end port count, the same as `fct_voyages`.
*/
with origin_countries as (
    select distinct iso3
    from {{ ref('dim_country') }}
    where region <> 'other' and iso3 is not null
),

departures as (
    select v.start_port_id, v.start_port, v.start_iso3, v.start_lon, v.start_lat
    from {{ ref('stg_climatetrace_voyages') }} as v
    inner join origin_countries on origin_countries.iso3 = v.start_iso3
    where v.end_iso3 = 'USA'
        and {{ is_container_ship('v.vessel_type') }}
        and not v.end_point_contradicts_end_port
        and v.start_lon is not null
),

names as (
    select distinct on (start_port_id) start_port_id, start_port as port_name
    from departures
    where start_port is not null
    group by start_port_id, start_port
    order by start_port_id, count(*) desc, start_port
)

select
    departures.start_port_id,
    names.port_name,
    min(departures.start_iso3) as iso3,
    percentile_cont(0.5) within group (order by departures.start_lon) as lon,
    percentile_cont(0.5) within group (order by departures.start_lat) as lat,
    count(*) as container_voyages
from departures
left join names using (start_port_id)
group by departures.start_port_id, names.port_name
