-- Imports by port of unlading at HS-6, detail rows only (no country groups or totals).
select
    to_date(p.time, 'YYYY-MM') as month,
    p.i_commodity as hs6,
    p.cty_code as census_cty_code,
    p.port as port_code,
    p.gen_val_mo as general_value_usd,
    p.air_val_mo as air_value_usd,
    p.air_wgt_mo as air_weight_kg,
    p.ves_val_mo as vessel_value_usd,
    p.ves_wgt_mo as vessel_weight_kg,
    p.cnt_val_mo as containerized_value_usd,
    p.cnt_wgt_mo as containerized_weight_kg,
    p.load_id
from {{ source('raw', 'census_porths') }} as p
where p.load_id in ({{ current_census_loads('census_porths') }})
    and p.summary_lvl = 'DET'
    and p.cty_code <> '-'
    and p.port <> '-'
