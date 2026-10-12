-- EPA Hub Table 8 from the current load: kg CO2, g CH4 and g N2O per unit, with footnote letters removed from vehicle names ("Medium- and Heavy-Duty TruckC").
select
    regexp_replace({{ clean_label('t.vehicle_type') }}, '([a-z]) ?[A-Z]$', '\1') as vehicle_type,
    t.co2_factor as co2_kg,
    t.ch4_factor as ch4_g,
    t.n2o_factor as n2o_g,
    t.units,
    t.load_id
from {{ source('raw', 'epa_ghg_transport_factors') }} as t
where t.load_id in ({{ succeeded_loads('epa_ghg_transport_factors') }})
