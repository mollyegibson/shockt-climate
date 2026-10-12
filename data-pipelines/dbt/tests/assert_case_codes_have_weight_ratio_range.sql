-- Fails when a code imported overland from Mexico has no origin whose air and vessel shipments reach `overland_weight.min_air_vessel_value_usd`, so its weight would have no range.
select distinct overland.hs6
from {{ ref('fct_imports_port_monthly') }} as overland
inner join {{ ref('dim_country') }} as country using (census_cty_code)
where country.iso3 = 'MEX'
    and overland.mode = 'other'
    and overland.value_usd > 0
    and not exists (
        select 1
        from {{ ref('agg_air_vessel_kg_per_usd') }} as ratio
        where ratio.hs6 = overland.hs6 and ratio.census_cty_code is not null and ratio.meets_minimum
    )
