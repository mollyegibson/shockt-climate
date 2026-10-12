-- Fails when a Census port with case vessel or air tonnage matches no coast rule, so a gap in `coast_region` can't hide in a region.
select port.port_code, port.port_name, port.lon, port.lat, sum(fact.weight_t) as weight_t
from {{ ref('fct_imports_port_monthly') }} as fact
inner join {{ ref('dim_port') }} as port using (port_code)
where fact.mode in ('vessel', 'air') and port.coast_region = 'other'
group by 1, 2, 3, 4
having sum(fact.weight_t) > 0
