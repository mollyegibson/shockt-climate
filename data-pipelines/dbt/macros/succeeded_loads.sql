{#- load_ids of the current (succeeded) loads of one dataset. -#}
{% macro succeeded_loads(dataset) %}
    select load_id
    from {{ source('raw', 'load_manifest') }}
    where dataset = '{{ dataset }}' and status = 'succeeded'
{% endmacro %}
