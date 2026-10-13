-- Departure port and airport weights split an origin's tonnage without losing or duplicating any: per month, origin, HS-6 and mode (and coast region for vessel), they sum to the tonnage they split, within 0.1% or 1 kg. Origins with no departure node are excluded; the warn_ tests list them.
with weights as (
    select month, census_cty_code, hs6, mode, coalesce(lane_coast_region, '') as coast_region, sum(weight_t) as weight_t
    from {{ ref('fct_node_weights_monthly') }}
    where node_id like 'departure_%'
    group by 1, 2, 3, 4, 5
),

vessel as (
    select month, census_cty_code, hs6, 'vessel' as mode, coast_region, sum(weight_t) as weight_t
    from {{ ref('fct_imports_port_monthly') }}
    where mode = 'vessel' and weight_t > 0
    group by 1, 2, 3, 5
),

air as (
    select month, census_cty_code, hs6, 'air' as mode, '' as coast_region, sum(weight_t) as weight_t
    from {{ ref('fct_imports_monthly') }}
    where mode = 'air' and weight_t > 0
    group by 1, 2, 3
),

expected as (
    select * from vessel
    union all
    select * from air
)

select expected.*, weights.weight_t as split_weight_t
from expected
inner join weights using (month, census_cty_code, hs6, mode, coast_region)
where abs(weights.weight_t - expected.weight_t) > greatest(0.001, 0.001 * expected.weight_t)
