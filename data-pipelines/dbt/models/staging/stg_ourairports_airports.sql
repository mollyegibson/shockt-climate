-- Airports in the US and its territories (Schedule C), of the types and service in `air_ports` (config/transforms.yaml), with a two-letter state or territory code.
select
    a.iata_code,
    a.name,
    a.municipality,
    a.type,
    case when a.iso_country = 'US' then substr(a.iso_region, 4) else a.iso_country end as state,
    a.latitude_deg as lat,
    a.longitude_deg as lon,
    {{ normalize_place('a.name') }} as name_normalized,
    {{ normalize_place('a.municipality') }} as municipality_normalized,
    a.load_id
from {{ source('raw', 'ourairports_airports') }} as a
where a.load_id in ({{ succeeded_loads('ourairports_airports') }})
    {% if var('air_ports')['scheduled_service_only'] %}and a.scheduled_service = 'yes'{% endif %}
    and a.type in ({% for t in var('air_ports')['airport_types'] %}'{{ t }}'{% if not loop.last %}, {% endif %}{% endfor %})
    and a.iso_country in ({{ us_and_territories_iso2() }})
