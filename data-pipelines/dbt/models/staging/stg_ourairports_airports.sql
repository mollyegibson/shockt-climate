-- US and US-territory airports with scheduled service, large or medium, with a two-letter state or territory code.
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
    and a.scheduled_service = 'yes'
    and a.type in ('large_airport', 'medium_airport')
    and a.iso_country in ('US', 'PR', 'VI', 'GU', 'AS', 'MP')
