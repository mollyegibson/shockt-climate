{#- load_ids of a Census dataset's current loads whose HS prefix (the partition key after the month) is still in config/hs_codes.yaml. -#}
{% macro current_census_loads(dataset) %}
    select load_id
    from {{ source('raw', 'load_manifest') }}
    where dataset = '{{ dataset }}'
        and status = 'succeeded'
        and split_part(partition_key, ':', 2) in (select hs_prefix from {{ ref('seed_hs_case_codes') }})
{% endmacro %}
