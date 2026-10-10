select
    port_code,
    port_name,
    district_code,
    coast_region
from {{ ref('seed_port_regions') }}
where port_code <> '-'
