-- Fails when a country's region isn't a region of config/origins.yaml or `other`, or a voyage starts outside the configured origins.
{% set regions = var('origins')['regions'].keys() | list %}
select 'dim_country' as model, region, count(*) as n
from {{ ref('dim_country') }}
where region not in ({% for r in regions %}'{{ r }}', {% endfor %}'other')
group by region
union all
select 'fct_voyages', origin_region, count(*)
from {{ ref('fct_voyages') }}
where origin_region not in ({% for r in regions %}'{{ r }}'{% if not loop.last %}, {% endif %}{% endfor %})
group by origin_region
