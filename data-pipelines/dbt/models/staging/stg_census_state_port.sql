-- Census State/Port Imports from the current loads: quarter, state of destination, ports of unlading and entry, and country, for all goods.
select
    make_date(s.stat_year, 3 * s.time_period::int - 2, 1) as quarter,
    s.state,
    s.district_unlading || s.port_unlading as unlading_port_code,
    s.district_entry || s.port_entry as entry_port_code,
    s.country as census_cty_code,
    s.value as general_value_usd,
    s.air_val as air_value_usd,
    s.air_swt as air_weight_kg,
    s.ves_val as vessel_value_usd,
    s.ves_swt as vessel_weight_kg,
    s.cnt_val as containerized_value_usd,
    s.cnt_swt as containerized_weight_kg,
    s.load_id
from {{ source('raw', 'census_state_port') }} as s
where s.load_id in ({{ succeeded_loads('census_state_port') }})
