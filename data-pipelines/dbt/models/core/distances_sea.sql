/*
Sea distances between departure ports and arrival seaports, with scenario variants and passages.
Adds a speed-estimated duration (12.5 knots / 23.15 km/h per IMO Fourth GHG Study).
*/
select
    from_node_id,
    to_node_id,
    scenario,
    km,
    km / 23.15 as duration_h,
    passages,
    source
from {{ ref('seed_sea_distances') }}
