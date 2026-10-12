-- Fails when more container voyages than `climatetrace.max_contradicting_end_point_share` (config/transforms.yaml) end somewhere that contradicts their end port, so a systematic problem isn't filtered away.
select
    count(*) filter (where end_point_contradicts_end_port) as contradicting,
    count(*) as container_voyages
from {{ ref('stg_climatetrace_voyages') }}
where {{ is_container_ship('vessel_type') }}
having count(*) filter (where end_point_contradicts_end_port)
    > {{ var('climatetrace')['max_contradicting_end_point_share'] }} * count(*)
