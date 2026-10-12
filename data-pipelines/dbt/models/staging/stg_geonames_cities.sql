-- GeoNames cities of 5,000 or more; for US cities `admin1_code` is the two-letter state code.
select
    g.geonameid,
    g.name,
    g.country_code,
    g.admin1_code,
    {{ normalize_place('g.asciiname') }} as name_normalized,
    g.latitude as lat,
    g.longitude as lon,
    g.population,
    g.load_id
from {{ source('raw', 'geonames_cities') }} as g
where g.load_id in ({{ succeeded_loads('geonames_cities') }})
