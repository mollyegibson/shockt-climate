-- Fails when Census ports dim_port can't place carry more case vessel or air tonnage than `census_ports.max_unlocated_share` (config/transforms.yaml), per mode.
with tonnage as (
    select fact.mode, port.coast_region = 'unknown' as unlocated, sum(fact.weight_t) as weight_t
    from {{ ref('fct_imports_port_monthly') }} as fact
    left join {{ ref('dim_port') }} as port using (port_code)
    where fact.mode in ('vessel', 'air')
    group by 1, 2
)

select mode, sum(weight_t) filter (where unlocated) / nullif(sum(weight_t), 0) as unlocated_share
from tonnage
group by mode
having sum(weight_t) filter (where unlocated) / nullif(sum(weight_t), 0)
    > {{ var('census_ports')['max_unlocated_share'] }}
