-- Container-ship voyages from the configured origins to US ports, one row per voyage.
with origin_regions as (
    select distinct iso3, region
    from {{ ref('dim_country') }}
    where iso3 is not null
)

select
    v.asset_identifier,
    v.model_source,
    v.started_at,
    date_trunc('month', v.started_at)::date as start_month,
    v.ended_at,
    v.vessel_name,
    v.start_port,
    v.start_iso3,
    origin_regions.region as origin_region,
    v.end_port,
    v.end_port_id,
    ports.coast_region as end_coast_region,
    v.distance_nm,
    v.distance_km,
    v.duration_h,
    v.co2e_t,
    v.co2e_t / nullif(v.distance_km, 0) as co2e_t_per_km,
    v.load_id
from {{ ref('stg_climatetrace_voyages') }} as v
left join origin_regions on origin_regions.iso3 = v.start_iso3
left join {{ ref('dim_climatetrace_ports') }} as ports on ports.end_port_id = v.end_port_id
where {{ is_container_ship('v.vessel_type') }}
