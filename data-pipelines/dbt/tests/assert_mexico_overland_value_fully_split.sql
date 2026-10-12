-- Fails when a crossing's Census overland value from Mexico for a code and month isn't fully split into truck and rail (within $1), e.g. a month with no TransBorder split at all.
with census as (
    select fact.month, fact.hs6, fact.port_code, fact.value_usd
    from {{ ref('fct_imports_port_monthly') }} as fact
    inner join {{ ref('dim_port') }} as port using (port_code)
    inner join {{ ref('dim_country') }} as country using (census_cty_code)
    where country.iso3 = 'MEX' and fact.mode = 'other' and port.is_border_crossing and fact.value_usd > 0
),

split as (
    select month, hs6, port_code, sum(value_usd) as value_usd
    from {{ ref('fct_mexico_overland_monthly') }}
    group by month, hs6, port_code
)

select census.month, census.hs6, census.port_code, census.value_usd as census_usd, split.value_usd as split_usd
from census
left join split using (month, hs6, port_code)
where split.value_usd is null or abs(census.value_usd - split.value_usd) > 1
