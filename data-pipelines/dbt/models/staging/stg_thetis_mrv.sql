-- Per-ship annual fuel consumption and emissions from EMSA THETIS-MRV, current loads only.
select
    m.reporting_year,
    m.report_type,
    m.imo_number,
    m.ship_name,
    m.ship_type,
    m.port_of_registry,
    m.home_port,
    m.ice_class,
    m.doc_issue_date,
    m.doc_expiry_date,
    m.total_fuel_consumption_mt,
    m.total_co2_mt,
    m.total_co2eq_mt,
    m.time_at_sea_hours,
    m.fuel_per_distance_kg_nm,
    m.co2_per_distance_kg_nm,
    m.co2_per_transport_work_mass,
    m.load_id
from {{ source('raw', 'thetis_mrv') }} as m
where m.load_id in ({{ succeeded_loads('thetis_mrv') }})
    and m.report_type = 'full'
