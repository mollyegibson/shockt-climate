-- Mexican overland (`other`) value of the case codes entered at ports that aren't US–Mexico crossings (through Canada, or recorded at airports), which `fct_mexico_overland_monthly` leaves out.
{{ config(severity='warn') }}

select imports.hs6, port.port_code, port.port_name, sum(imports.value_usd) as value_usd
from {{ ref('fct_imports_port_monthly') }} as imports
inner join {{ ref('dim_country') }} as country using (census_cty_code)
inner join {{ ref('dim_port') }} as port using (port_code)
where country.iso3 = 'MEX'
    and imports.mode = 'other'
    and imports.value_usd > 0
    and not port.is_border_crossing
group by imports.hs6, port.port_code, port.port_name
