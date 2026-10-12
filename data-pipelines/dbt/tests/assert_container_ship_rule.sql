-- Pins is_container_ship to the ship-type names of both Climate TRACE models; returns any type classified differently.
with known (vessel_type, expected) as (
    values ('container', true), ('cargo.container', true), ('cargo.bulk_carrier', false),
           ('tanker.chemical', false), ('passenger', false), ('bulk_carrier', false)
)

select vessel_type, expected
from known
where {{ is_container_ship('vessel_type') }} <> expected
