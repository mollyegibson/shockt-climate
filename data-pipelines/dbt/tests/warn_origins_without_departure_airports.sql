-- Warns when case air tonnage from origins with no placed departure airport in T-100 passes `departure_nodes.max_unplaced_share.air`; lists those origins. Their air legs have no start, so they are left out of the weights.
{{ config(severity='warn') }}

with air as (
    select country.iso3, sum(imports.weight_t) as weight_t
    from {{ ref('fct_imports_monthly') }} as imports
    inner join {{ ref('dim_country') }} as country using (census_cty_code)
    where imports.mode = 'air' and imports.weight_t > 0 and country.region <> 'other'
    group by country.iso3
),

unplaced as (
    select iso3, weight_t, weight_t / (select sum(weight_t) from air) as share_of_air
    from air
    where iso3 not in (select iso3 from {{ ref('dim_departure_airports') }} where lat is not null)
)

select *
from unplaced
where (select sum(share_of_air) from unplaced)
    > {{ var('departure_nodes')['max_unplaced_share']['air'] }}
