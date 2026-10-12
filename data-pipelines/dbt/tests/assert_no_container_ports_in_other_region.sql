-- Fails when a US arrival port with container voyages matches no coast rule, so a gap in `coast_region` can't hide in a region.
select end_port_id, port_name, lon, lat, container_voyages
from {{ ref('dim_climatetrace_ports') }}
where coast_region = 'other' and container_voyages > 0
