-- Case imports to the unidentified state `XX`, which has no destination node, so they are left out of the destination weights.
{{ config(severity='warn') }}

select census_cty_code, hs6, mode, sum(value_usd) as value_usd, sum(weight_t) as weight_t
from {{ ref('fct_imports_state_monthly') }}
where state = 'XX'
group by census_cty_code, hs6, mode
