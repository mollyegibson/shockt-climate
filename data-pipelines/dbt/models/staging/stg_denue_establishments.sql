-- INEGI DENUE manufacturing establishments from the current load, in the case industries, with each employee band's lower bound.
select
    d.id,
    d.nom_estab as name,
    d.codigo_act as scian_code,
    d.nombre_act as industry_name,
    d.per_ocu as employee_band,
    {{ employee_band_min('d.per_ocu') }} as employee_band_min,
    d.entidad as state_name,
    d.municipio as municipality,
    d.latitud as lat,
    d.longitud as lon,
    d.load_id
from {{ source('raw', 'denue_establishments') }} as d
where d.load_id in ({{ succeeded_loads('denue_establishments') }})
