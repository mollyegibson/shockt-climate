-- Container-ship voyages from the configured origins to US ports, one row per voyage.
select
    asset_identifier,
    model_source,
    started_at,
    date_trunc('month', started_at)::date as start_month,
    ended_at,
    vessel_name,
    start_port,
    start_iso3,
    end_port,
    end_port_id,
    distance_nm,
    distance_km,
    duration_h,
    co2e_t,
    co2e_t / nullif(distance_km, 0) as co2e_t_per_km,
    load_id
from {{ ref('stg_climatetrace_voyages') }}
where vessel_type in ('container', 'cargo.container')
