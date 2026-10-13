-- Crossings with overland imports of a code whose industries DENUE covers, but no large plant in those industries: their Mexican leg has no start, so it is left out.
{{ config(severity='warn') }}

select overland.port_code, overland.hs6, sum(overland.weight_t) as weight_t
from {{ ref('fct_mexico_overland_monthly') }} as overland
inner join {{ ref('seed_hs_case_codes') }} as prefix
    on overland.hs6 like prefix.hs_prefix || '%' or prefix.hs_prefix like overland.hs6 || '%'
left join {{ ref('map_crossing_plant') }} as crossing
    on crossing.port_code = overland.port_code and crossing.hs6 = overland.hs6
where string_to_array(prefix.cases, '|')
        && array[{% for case in var('denue')['cases'] %}'{{ case }}'{% if not loop.last %}, {% endif %}{% endfor %}]::text[]
    and overland.weight_t > 0
    and crossing.port_code is null
group by overland.port_code, overland.hs6
