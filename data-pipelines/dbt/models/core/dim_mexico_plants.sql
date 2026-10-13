-- DENUE establishments whose employee band starts at or above `mexico_sites.min_employees` (config/transforms.yaml), one per industry and location: DENUE lists some plants several times at the same coordinates.
select distinct on (lat, lon, scian_code)
    id as plant_id,
    name,
    scian_code,
    industry_name,
    employee_band,
    employee_band_min,
    state_name,
    municipality,
    lat,
    lon
from {{ ref('stg_denue_establishments') }}
where employee_band_min >= {{ var('mexico_sites')['min_employees'] }}
    and lat is not null
    and lon is not null
order by lat, lon, scian_code, id
