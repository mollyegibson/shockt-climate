{{
    config(
        severity='warn'
    )
}}
/*
Arrival seaports in seed_sea_distances that have no road or rail distance to any destination state.
Routes through these seaports dead-end at the port with no inland leg.
*/
select distinct sea.to_node_id as seaport_node_id
from {{ ref('seed_sea_distances') }} as sea
where sea.to_node_id not in (
    select from_node_id from {{ ref('seed_road_distances') }}
    union
    select from_node_id from {{ ref('seed_rail_distances') }}
)
