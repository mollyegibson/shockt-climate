/*
Every freight emission factor per tonne-km in the UK government conversion factors and the EPA
GHG Emission Factors Hub, in kg CO2e: tank-to-wheel (fuel burned), well-to-tank (producing and
delivering the fuel) and their sum, well-to-wheel.

A UK factor is a `Freighting goods` row with a published value (the UK leaves some blank, such as
0%-laden HGVs per tonne-km), paired with its well-to-tank row, which the UK file keeps
under `WTT- delivery vehs & freight` with the same labels and `WTT- ` before Level 2. An EPA factor
is a Table 8 short ton-mile row with CH4 and N2O weighted by the Table 11 GWPs; EPA covers
combustion only, so its well-to-tank is tank-to-wheel times the UK well-to-tank to combustion ratio,
per litre, of the fuel `epa_vehicle_fuel` assigns.
*/
{% set tonne_km_per_short_ton_mile = 0.90718474 * 1.609344 %}

with uk as (
    select *
    from {{ ref('stg_uk_ghg_conversion_factors') }}
    where ghg_unit = 'kg CO2e'
),

uk_factors as (
    select
        'uk_desnz' as source,
        ttw.id as source_row_id,
        {{ freight_mode('ttw.level_2') }} as mode,
        concat_ws(' / ', ttw.level_2, ttw.level_3, ttw.level_4, ttw.column_text) as variant,
        {{ uk_vehicle_type('ttw.level_2', 'ttw.level_3') }} as vehicle_type,
        {{ uk_size_class('ttw.level_2', 'ttw.level_4') }} as size_class,
        {{ uk_haul('ttw.level_2', 'ttw.level_3') }} as haul,
        {{ uk_radiative_forcing('ttw.level_2', 'ttw.column_text') }} as radiative_forcing,
        null::text as fuel,
        ttw.factor as ttw_kg_co2e_per_tkm,
        wtt.factor as wtt_kg_co2e_per_tkm,
        'uk_wtt_row' as wtt_method,
        wtt.id as wtt_source_row_ids,
        null::double precision as wtt_to_ttw_ratio,
        ttw.load_id
    from uk as ttw
    left join uk as wtt
        on wtt.level_1 = 'WTT- delivery vehs & freight'
        and wtt.uom = ttw.uom
        and lower(wtt.level_2) = lower('WTT- ' || ttw.level_2)
        and lower(wtt.level_3) is not distinct from lower(ttw.level_3)
        and lower(wtt.level_4) is not distinct from lower(ttw.level_4)
        and lower(wtt.column_text) is not distinct from lower(ttw.column_text)
    where ttw.level_1 = 'Freighting goods' and ttw.uom = 'tonne.km' and ttw.factor is not null
),

fuel_ratios as (
    select
        combustion.level_3 as fuel,
        well_to_tank.factor / combustion.factor as wtt_to_ttw_ratio,
        well_to_tank.id || ' / ' || combustion.id as source_row_ids
    from uk as combustion
    inner join uk as well_to_tank
        on well_to_tank.level_1 = 'WTT- fuels'
        and well_to_tank.uom = combustion.uom
        and well_to_tank.level_2 = combustion.level_2
        and well_to_tank.level_3 = combustion.level_3
        and well_to_tank.level_4 is not distinct from combustion.level_4
        and well_to_tank.column_text is not distinct from combustion.column_text
    where combustion.level_1 = 'Fuels'
        and combustion.level_2 = 'Liquid fuels'
        and combustion.uom = 'litres'
),

gwp as (
    select
        max(gwp_100yr) filter (where chemical_formula = 'CH4') as ch4,
        max(gwp_100yr) filter (where chemical_formula = 'N2O') as n2o
    from {{ ref('stg_epa_ghg_gwp') }}
),

epa as (
    select
        transport.vehicle_type,
        (transport.co2_kg + (transport.ch4_g * gwp.ch4 + transport.n2o_g * gwp.n2o) / 1000)
            / {{ tonne_km_per_short_ton_mile }} as ttw_kg_co2e_per_tkm,
        {{ epa_vehicle_fuel('transport.vehicle_type') }} as fuel,
        transport.load_id
    from {{ ref('stg_epa_ghg_transport_factors') }} as transport
    cross join gwp
    where transport.units = 'short ton-mile'
),

epa_factors as (
    select
        'epa_hub' as source,
        epa.vehicle_type as source_row_id,
        {{ freight_mode('epa.vehicle_type') }} as mode,
        epa.vehicle_type as variant,
        {{ epa_vehicle_type('epa.vehicle_type') }} as vehicle_type,
        null::text as size_class,
        null::text as haul,
        null::boolean as radiative_forcing,
        epa.fuel,
        epa.ttw_kg_co2e_per_tkm,
        epa.ttw_kg_co2e_per_tkm * fuel_ratios.wtt_to_ttw_ratio as wtt_kg_co2e_per_tkm,
        case when fuel_ratios.fuel is not null then 'uk_fuel_ratio' end as wtt_method,
        fuel_ratios.source_row_ids as wtt_source_row_ids,
        fuel_ratios.wtt_to_ttw_ratio,
        epa.load_id
    from epa
    left join fuel_ratios on fuel_ratios.fuel = epa.fuel
),

factors as (
    select * from uk_factors
    union all
    select * from epa_factors
)

select
    source,
    source_row_id,
    mode,
    variant,
    vehicle_type,
    size_class,
    haul,
    radiative_forcing,
    fuel,
    ttw_kg_co2e_per_tkm,
    wtt_kg_co2e_per_tkm,
    ttw_kg_co2e_per_tkm + wtt_kg_co2e_per_tkm as wtw_kg_co2e_per_tkm,
    wtt_method,
    wtt_source_row_ids,
    wtt_to_ttw_ratio,
    load_id
from factors
