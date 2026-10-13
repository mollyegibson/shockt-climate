-- Warns when case vessel tonnage from origins with no departure port (no container voyage from them to the US) passes `departure_nodes.max_unplaced_share.vessel`; lists those origins. Their sea legs have no start, so they are left out of the weights.
{{ config(severity='warn') }}

with vessel as (
    select country.iso3, sum(port.weight_t) as weight_t
    from {{ ref('fct_imports_port_monthly') }} as port
    inner join {{ ref('dim_country') }} as country using (census_cty_code)
    where port.mode = 'vessel' and port.weight_t > 0 and country.region <> 'other'
    group by country.iso3
),

unplaced as (
    select iso3, weight_t, weight_t / (select sum(weight_t) from vessel) as share_of_vessel
    from vessel
    where iso3 not in (select iso3 from {{ ref('dim_departure_ports') }})
)

select *
from unplaced
where (select sum(share_of_vessel) from unplaced)
    > {{ var('departure_nodes')['max_unplaced_share']['vessel'] }}
