-- Every OurAirports airport with an IATA code, in any country, for placing departure airports by the codes other sources report.
select
    a.iata_code,
    a.name,
    a.municipality,
    a.type,
    a.iso_country as iso2,
    a.latitude_deg as lat,
    a.longitude_deg as lon,
    a.load_id
from {{ source('raw', 'ourairports_airports') }} as a
where a.load_id in ({{ succeeded_loads('ourairports_airports') }})
    and a.iata_code is not null
    and a.iata_code <> ''
