select
    from_node_id,
    to_node_id,
    km,
    duration_h,
    source
from {{ ref('seed_road_distances') }}
