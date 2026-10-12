/*
Kg per dollar of air and vessel imports by HS-6 and origin over the loaded months, plus one row per
HS-6 across all origins (`census_cty_code` null): the basis for estimating overland weight from
value (plan section 7.3). An origin meets the minimum when its air and vessel value of the code
reaches `overland_weight.min_air_vessel_value_usd`. On the all-origins row, `kg_per_usd_low` and
`kg_per_usd_high` are the value-weighted percentiles in `overland_weight.range_percentiles` across
origins that meet the minimum: the ratio of the first origin, in order of kg per dollar, whose
cumulative share of the code's air and vessel value reaches the percentile.
*/
{% set low, high = var('overland_weight')['range_percentiles'] %}

with shipments as (
    select
        hs6,
        census_cty_code,
        sum(value_usd) as air_vessel_value_usd,
        sum(weight_t) * 1000 as air_vessel_weight_kg
    from {{ ref('fct_imports_monthly') }}
    where mode in ('air', 'vessel')
    group by hs6, census_cty_code
    having sum(value_usd) > 0
),

origins as (
    select
        hs6,
        census_cty_code,
        air_vessel_value_usd,
        air_vessel_weight_kg,
        air_vessel_weight_kg / air_vessel_value_usd as kg_per_usd,
        air_vessel_value_usd >= {{ var('overland_weight')['min_air_vessel_value_usd'] }} as meets_minimum
    from shipments
),

cumulative as (
    select
        hs6,
        kg_per_usd,
        sum(air_vessel_value_usd) over (partition by hs6 order by kg_per_usd, census_cty_code)
            / sum(air_vessel_value_usd) over (partition by hs6) as value_share_up_to
    from origins
    where meets_minimum
),

band as (
    select
        hs6,
        min(kg_per_usd) filter (where value_share_up_to >= {{ low }}) as kg_per_usd_low,
        min(kg_per_usd) filter (where value_share_up_to >= {{ high }}) as kg_per_usd_high
    from cumulative
    group by hs6
)

select
    hs6,
    census_cty_code,
    air_vessel_value_usd,
    air_vessel_weight_kg,
    kg_per_usd,
    meets_minimum,
    null::numeric as kg_per_usd_low,
    null::numeric as kg_per_usd_high
from origins

union all

select
    origins.hs6,
    null,
    sum(origins.air_vessel_value_usd),
    sum(origins.air_vessel_weight_kg),
    sum(origins.air_vessel_weight_kg) / sum(origins.air_vessel_value_usd),
    true,
    band.kg_per_usd_low,
    band.kg_per_usd_high
from origins
left join band using (hs6)
group by origins.hs6, band.kg_per_usd_low, band.kg_per_usd_high
