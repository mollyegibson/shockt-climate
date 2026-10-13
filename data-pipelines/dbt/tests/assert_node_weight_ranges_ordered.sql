-- Every node weight lies inside its own range: low ≤ estimate ≤ high.
select *
from {{ ref('fct_node_weights_monthly') }}
where not (weight_t_low <= weight_t and weight_t <= weight_t_high)
