-- Warns, per HS-6 code, when the Mexican overland (`other`) value entering at ports that aren't US–Mexico crossings (through Canada, or recorded at airports) passes `overland_weight.max_non_crossing_share` of the code's Mexican overland value over the loaded months. `fct_mexico_overland_monthly` leaves that value out.
{{ config(severity='warn') }}

with overland as (
    select imports.hs6, port.is_border_crossing, imports.value_usd
    from {{ ref('fct_imports_port_monthly') }} as imports
    inner join {{ ref('dim_country') }} as country using (census_cty_code)
    inner join {{ ref('dim_port') }} as port using (port_code)
    where country.iso3 = 'MEX' and imports.mode = 'other' and imports.value_usd > 0
)

select
    hs6,
    sum(value_usd) filter (where not is_border_crossing) as non_crossing_value_usd,
    sum(value_usd) as overland_value_usd
from overland
group by hs6
having coalesce(sum(value_usd) filter (where not is_border_crossing), 0)
    > {{ var('overland_weight')['max_non_crossing_share'] }} * sum(value_usd)
