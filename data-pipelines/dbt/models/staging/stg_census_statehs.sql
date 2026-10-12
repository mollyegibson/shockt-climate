-- Imports by state of destination at HS-6, detail rows only (no country groups or totals).
select
    to_date(s.time, 'YYYY-MM') as month,
    s.i_commodity as hs6,
    s.cty_code as census_cty_code,
    s.state,
    s.gen_val_mo as general_value_usd,
    s.con_val_mo as consumption_value_usd,
    s.air_val_mo as air_value_usd,
    s.air_wgt_mo as air_weight_kg,
    s.ves_val_mo as vessel_value_usd,
    s.ves_wgt_mo as vessel_weight_kg,
    s.cnt_val_mo as containerized_value_usd,
    s.cnt_wgt_mo as containerized_weight_kg,
    s.load_id
from {{ source('raw', 'census_statehs') }} as s
where s.load_id in ({{ current_census_loads('census_statehs') }})
    and s.summary_lvl = 'DET'
    and s.cty_code <> '-'
