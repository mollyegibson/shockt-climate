-- Country-level imports at HS-10, detail rows only (no country groups or all-countries total).
select
    to_date(h.time, 'YYYY-MM') as month,
    h.i_commodity as hs10,
    left(h.i_commodity, 6) as hs6,
    h.i_commodity_sdesc as hs10_description,
    h.cty_code as census_cty_code,
    h.gen_val_mo as general_value_usd,
    h.con_val_mo as consumption_value_usd,
    h.air_val_mo as air_value_usd,
    h.air_wgt_mo as air_weight_kg,
    h.ves_val_mo as vessel_value_usd,
    h.ves_wgt_mo as vessel_weight_kg,
    h.cnt_val_mo as containerized_value_usd,
    h.cnt_wgt_mo as containerized_weight_kg,
    h.gen_cha_mo as general_charges_usd,
    h.air_cha_mo as air_charges_usd,
    h.ves_cha_mo as vessel_charges_usd,
    h.cnt_cha_mo as containerized_charges_usd,
    h.dut_val_mo as dutiable_value_usd,
    h.cal_dut_mo as calculated_duty_usd,
    h.gen_qy1_mo as quantity_1,
    nullif(h.unit_qy1, '-') as quantity_1_unit,
    h.gen_qy2_mo as quantity_2,
    nullif(h.unit_qy2, '-') as quantity_2_unit,
    h.load_id
from {{ source('raw', 'census_hs') }} as h
where h.load_id in ({{ current_census_loads('census_hs') }})
    and h.summary_lvl = 'DET'
    and h.cty_code <> '-'
