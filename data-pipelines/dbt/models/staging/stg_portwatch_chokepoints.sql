-- Daily chokepoint transits from current PortWatch loads; capacity is estimated trade volume in metric tons.
select
    p.date,
    p.portid as chokepoint_id,
    p.portname as chokepoint_name,
    p.n_container,
    p.n_dry_bulk,
    p.n_general_cargo,
    p.n_roro,
    p.n_tanker,
    p.n_cargo,
    p.n_total,
    p.capacity_container as container_t,
    p.capacity_dry_bulk as dry_bulk_t,
    p.capacity_general_cargo as general_cargo_t,
    p.capacity_roro as roro_t,
    p.capacity_tanker as tanker_t,
    p.capacity_cargo as cargo_t,
    p.capacity as total_t,
    p.load_id
from {{ source('raw', 'portwatch_chokepoints') }} as p
where p.load_id in ({{ succeeded_loads('portwatch_chokepoints') }})
