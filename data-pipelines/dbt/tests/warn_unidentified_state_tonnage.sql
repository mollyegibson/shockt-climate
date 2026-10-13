-- Warns when case imports to Census's unidentified state `XX`, which has no destination node, pass `destination_states.max_unidentified_share` of state-level air and vessel tonnage; lists them.
{{ config(severity='warn') }}

with states as (
    select state, census_cty_code, hs6, mode, weight_t
    from {{ ref('fct_imports_state_monthly') }}
    where mode in ('air', 'vessel') and weight_t > 0
),

unidentified as (
    select census_cty_code, hs6, mode, sum(weight_t) as weight_t
    from states
    where state = 'XX'
    group by census_cty_code, hs6, mode
)

select *
from unidentified
where (select sum(weight_t) from unidentified)
    > {{ var('destination_states')['max_unidentified_share'] }} * (select sum(weight_t) from states)
