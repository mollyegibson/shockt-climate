-- One row per day × chokepoint: ship transits by type and estimated trade volume in metric tons.
select * from {{ ref('stg_portwatch_chokepoints') }}
