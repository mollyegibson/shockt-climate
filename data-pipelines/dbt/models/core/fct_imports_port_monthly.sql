-- Imports by port of unlading, one row per month × HS-6 × country × port × mode.
with by_mode as (
    {{ unpivot_modes(ref('stg_census_porths'), ['month', 'hs6', 'census_cty_code', 'port_code']) }}
)

select
    by_mode.*,
    port.coast_region
from by_mode
left join {{ ref('dim_port') }} as port using (port_code)
