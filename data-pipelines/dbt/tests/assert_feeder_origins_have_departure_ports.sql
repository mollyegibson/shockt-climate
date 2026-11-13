/*
Every feeder origin country must have at least one departure_port node in dim_nodes. Without this,
enumerate_routes finds no departure ports for the country and returns zero routes.
*/
select iso3
from (values ('BGD'), ('KHM'), ('JOR'), ('MMR')) as feeder_origins(iso3)
where iso3 not in (
    select iso3
    from {{ ref('dim_nodes') }}
    where kind = 'departure_port'
)
