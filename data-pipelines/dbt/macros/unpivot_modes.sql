{#-
  Turns one staging row with air, vessel and containerized vessel columns into one row per mode.
  `other` is general imports value minus air and vessel value (overland for Mexico and Canada);
  Census reports no weight for it. `modes` limits the output to some of them. Rows with neither
  value nor weight are dropped.
-#}
{% macro unpivot_modes(relation, keys, modes=none) %}
{% set columns = {
    'air': ('air_value_usd', 'air_weight_kg'),
    'vessel': ('vessel_value_usd', 'vessel_weight_kg'),
    'vessel_containerized': ('containerized_value_usd', 'containerized_weight_kg'),
    'other': ('general_value_usd - air_value_usd - vessel_value_usd', 'null::bigint'),
} %}
{% set selected = modes if modes is not none else columns.keys() | list %}
{% for mode in selected if mode not in columns %}
    {{ exceptions.raise_compiler_error("unpivot_modes: unknown mode '" ~ mode ~ "'") }}
{% endfor %}
with modes as (
    {% for mode in selected %}
    {% set value_col, weight_col = columns[mode] %}
    select
        {{ keys | join(', ') }},
        '{{ mode }}'::text as mode,
        {{ value_col }} as value_usd,
        {{ weight_col }} as weight_kg,
        load_id
    from {{ relation }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    {{ keys | join(', ') }},
    mode,
    value_usd,
    weight_kg / 1000.0 as weight_t,
    case when weight_kg is not null then 'reported' end as weight_method,
    load_id
from modes
where coalesce(value_usd, 0) <> 0 or coalesce(weight_kg, 0) <> 0
{% endmacro %}
