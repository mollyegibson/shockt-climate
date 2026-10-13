/*
For each Mexico–US border crossing and HS-6 code with overland imports, the nearest large plant in
the code's industries, by great-circle distance: the plant each crossing's Mexican leg starts at.

Only codes of the cases in `reference_sources.denue.cases` (config/sources.yaml) have DENUE
industries loaded. A code's industries are the NAICS codes the import concordance gives its HS-10
codes, cut to `industry_digits`, where DENUE's SCIAN and NAICS agree.
*/
with denue_codes as (
    select distinct overland.hs6, prefix.hs_prefix
    from {{ ref('fct_mexico_overland_monthly') }} as overland
    inner join {{ ref('seed_hs_case_codes') }} as prefix
        on overland.hs6 like prefix.hs_prefix || '%' or prefix.hs_prefix like overland.hs6 || '%'
    where string_to_array(prefix.cases, '|')
        && array[{% for case in var('denue')['cases'] %}'{{ case }}'{% if not loop.last %}, {% endif %}{% endfor %}]::text[]
),

industries as (
    select distinct denue_codes.hs6, left(concordance.naics, {{ var('denue')['industry_digits'] }}) as industry
    from denue_codes
    inner join {{ ref('stg_census_import_concordance') }} as concordance
        on concordance.hs10 like denue_codes.hs6 || '%'
        and concordance.hs10 like denue_codes.hs_prefix || '%'
),

crossings as (
    select distinct overland.port_code, overland.hs6, port.lat, port.lon
    from {{ ref('fct_mexico_overland_monthly') }} as overland
    inner join {{ ref('dim_port') }} as port using (port_code)
    where overland.hs6 in (select hs6 from denue_codes)
        and overland.weight_t > 0
        and port.lat is not null
)

select
    crossings.port_code,
    crossings.hs6,
    nearest.plant_id,
    nearest.km as great_circle_km
from crossings
cross join lateral (
    select plant.plant_id, distance.km
    from {{ ref('dim_mexico_plants') }} as plant
    cross join lateral (
        select {{ dbt_utils.haversine_distance('crossings.lat', 'crossings.lon', 'plant.lat', 'plant.lon', unit='km') }} as km
    ) as distance
    where left(plant.scian_code, {{ var('denue')['industry_digits'] }}) in (
        select industry from industries where industries.hs6 = crossings.hs6
    )
    order by distance.km, plant.plant_id
    limit 1
) as nearest
