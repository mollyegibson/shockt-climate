-- Imports by state of destination, one row per month × HS-6 × country × state × mode.
with by_mode as (
    {{ unpivot_modes(ref('stg_census_statehs'), ['month', 'hs6', 'census_cty_code', 'state']) }}
)

select
    by_mode.*,
    groups.state_group
from by_mode
left join {{ ref('seed_state_groups') }} as groups using (state)
