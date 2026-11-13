/*
Every hub port marked hub_has_us_voyages in agg_feeder_hub_shares_monthly must have at least one
entry in seed_sea_distances. Without this, feeder route enumeration assumes hub ports have sea
distances to US seaports — a hub without them silently produces zero onward routes.
*/
select hub_port_id
from (
    select distinct hub_port_id
    from {{ ref('agg_feeder_hub_shares_monthly') }}
    where hub_has_us_voyages
) as hubs
where 'departure_port:' || hub_port_id not in (
    select distinct from_node_id
    from {{ ref('seed_sea_distances') }}
)
