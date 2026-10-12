/*
Imports from Mexico that cross the land border, by month, HS-6, border crossing and mode (truck,
rail), with an estimated weight and its range (plan section 7.3).

Value is Census's overland value (general imports minus air and vessel) at each crossing, split
between truck and rail by the crossing's TransBorder truck and rail value for the chapter that
month; else its district's row; else the national shares. TransBorder's other land codes are left
out of the shares: code 9 is entry through a foreign trade zone, a customs status, and those goods
still crossed by truck or rail.

Weight is value × kg per dollar of the code's air and vessel shipments: Mexico's own when its
shipments reach the minimum, else all origins'. The range uses the value-weighted percentiles of the
ratio across origins that reach the minimum (`agg_air_vessel_kg_per_usd`).
*/
with mexico as (
    select census_cty_code
    from {{ ref('dim_country') }}
    where iso3 = 'MEX'
),

overland as (
    select
        fact.month,
        fact.hs6,
        left(fact.hs6, 2) as hs2,
        fact.port_code,
        fact.value_usd as overland_usd,
        fact.load_id
    from {{ ref('fct_imports_port_monthly') }} as fact
    inner join {{ ref('dim_port') }} as port using (port_code)
    where fact.census_cty_code in (select census_cty_code from mexico)
        and fact.mode = 'other'
        and port.is_border_crossing
        and fact.value_usd > 0
),

transborder as (
    select
        month,
        source_table,
        port_code,
        hs2,
        coalesce(sum(value_usd) filter (where mode = 'truck'), 0) as truck_usd,
        coalesce(sum(value_usd) filter (where mode = 'rail'), 0) as rail_usd,
        max(load_id::text)::uuid as load_id
    from {{ ref('stg_bts_transborder') }}
    where census_cty_code in (select census_cty_code from mexico)
    group by month, source_table, port_code, hs2
),

crossing_split as (
    select month, port_code, hs2, truck_usd, rail_usd, load_id
    from transborder
    where source_table = 'dot3' and port_code ~ '^[0-9]{4}$' and truck_usd + rail_usd > 0
),

district_split as (
    select month, left(port_code, 2) as district, hs2, truck_usd, rail_usd, load_id
    from transborder
    where source_table = 'dot3' and port_code ~ '^[0-9]{2}XX$' and truck_usd + rail_usd > 0
),

national_split as (
    select
        month,
        hs2,
        sum(truck_usd) as truck_usd,
        sum(rail_usd) as rail_usd,
        max(load_id::text)::uuid as load_id
    from transborder
    where source_table = 'dot2'
    group by month, hs2
    having sum(truck_usd) + sum(rail_usd) > 0
),

split as (
    select
        overland.*,
        case
            when crossing.port_code is not null then 'crossing'
            when district.district is not null then 'district'
            when national.hs2 is not null then 'national'
        end as split_source,
        case
            when crossing.port_code is not null then crossing.truck_usd
            when district.district is not null then district.truck_usd
            else national.truck_usd
        end as truck_usd,
        case
            when crossing.port_code is not null then crossing.rail_usd
            when district.district is not null then district.rail_usd
            else national.rail_usd
        end as rail_usd,
        coalesce(crossing.load_id, district.load_id, national.load_id) as transborder_load_id
    from overland
    left join crossing_split as crossing
        on crossing.month = overland.month
        and crossing.port_code = overland.port_code
        and crossing.hs2 = overland.hs2
    left join district_split as district
        on district.month = overland.month
        and district.district = left(overland.port_code, 2)
        and district.hs2 = overland.hs2
    left join national_split as national
        on national.month = overland.month
        and national.hs2 = overland.hs2
),

ratios as (
    select
        codes.hs6,
        coalesce(own.kg_per_usd, all_origins.kg_per_usd) as kg_per_usd,
        case when own.kg_per_usd is not null then 'origin' else 'all_origins' end as ratio_source,
        all_origins.kg_per_usd_low,
        all_origins.kg_per_usd_high
    from (select distinct hs6 from overland) as codes
    left join {{ ref('agg_air_vessel_kg_per_usd') }} as own
        on own.hs6 = codes.hs6
        and own.census_cty_code in (select census_cty_code from mexico)
        and own.meets_minimum
    left join {{ ref('agg_air_vessel_kg_per_usd') }} as all_origins
        on all_origins.hs6 = codes.hs6
        and all_origins.census_cty_code is null
),

by_mode as (
    select
        split.month,
        split.hs6,
        split.port_code,
        modes.mode,
        split.overland_usd * modes.mode_usd / (split.truck_usd + split.rail_usd) as value_usd,
        split.split_source,
        split.load_id,
        split.transborder_load_id
    from split
    cross join lateral (
        values ('truck', split.truck_usd), ('rail', split.rail_usd)
    ) as modes (mode, mode_usd)
    where modes.mode_usd > 0
)

select
    by_mode.month,
    by_mode.hs6,
    by_mode.port_code,
    by_mode.mode,
    by_mode.value_usd,
    by_mode.value_usd * ratios.kg_per_usd / 1000 as weight_t,
    by_mode.value_usd * ratios.kg_per_usd_low / 1000 as weight_t_low,
    by_mode.value_usd * ratios.kg_per_usd_high / 1000 as weight_t_high,
    'estimated_value_ratio' as weight_method,
    ratios.ratio_source,
    ratios.kg_per_usd,
    ratios.kg_per_usd_low,
    ratios.kg_per_usd_high,
    by_mode.split_source,
    by_mode.load_id,
    by_mode.transborder_load_id
from by_mode
inner join ratios using (hs6)
