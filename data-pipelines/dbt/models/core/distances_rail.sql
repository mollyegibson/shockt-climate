select
    from_node_id,
    to_node_id,
    km,
    from_snap_km,
    to_snap_km,
    source
from {{ ref('seed_rail_distances') }}
