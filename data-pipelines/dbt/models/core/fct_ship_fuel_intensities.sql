-- Per-ship annual fuel intensity from THETIS-MRV, joined to Climate TRACE container-ship voyages by IMO number.
with mrv as (
    select
        m.imo_number,
        m.reporting_year,
        m.ship_name,
        m.ship_type,
        m.port_of_registry,
        m.total_fuel_consumption_mt,
        m.total_co2_mt,
        m.total_co2eq_mt,
        m.time_at_sea_hours,
        m.fuel_per_distance_kg_nm,
        m.co2_per_distance_kg_nm,
        m.co2_per_transport_work_mass,
        m.load_id
    from {{ ref('stg_thetis_mrv') }} as m
),

voyage_ships as (
    select distinct
        split_part(v.asset_identifier, '-imo-', 2) as imo_number
    from {{ ref('fct_voyages') }} as v
    where split_part(v.asset_identifier, '-imo-', 2) <> ''
)

select
    mrv.*,
    voyage_ships.imo_number is not null as in_voyage_data
from mrv
left join voyage_ships using (imo_number)
