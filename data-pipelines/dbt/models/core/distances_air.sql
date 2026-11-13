select
    from_node_id,
    to_node_id,
    km,
    source
from {{ ref('seed_air_distances') }}
