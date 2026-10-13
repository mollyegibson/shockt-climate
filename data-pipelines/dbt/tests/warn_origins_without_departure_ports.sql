-- Origin countries with case vessel tonnage but no departure port: no container voyage from them to the US, so their sea legs have no start and are left out.
{{ config(severity='warn') }}

select country.iso3, sum(port.weight_t) as vessel_weight_t
from {{ ref('fct_imports_port_monthly') }} as port
inner join {{ ref('dim_country') }} as country using (census_cty_code)
where port.mode = 'vessel'
    and port.weight_t > 0
    and country.region <> 'other'
    and country.iso3 not in (select iso3 from {{ ref('dim_departure_ports') }})
group by country.iso3
