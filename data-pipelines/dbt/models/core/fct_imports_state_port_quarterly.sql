-- Imports of all goods by quarter, state of destination, port of unlading, port of entry, country and mode, with the unlading port's coast region.
with by_mode as (
    {{ unpivot_modes(ref('stg_census_state_port'), ['quarter', 'state', 'unlading_port_code', 'entry_port_code', 'census_cty_code']) }}
)

select
    by_mode.*,
    port.coast_region as unlading_coast_region
from by_mode
left join {{ ref('dim_port') }} as port on port.port_code = by_mode.unlading_port_code
