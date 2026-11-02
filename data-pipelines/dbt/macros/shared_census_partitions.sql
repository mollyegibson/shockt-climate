{#- Month and HS prefix of the Census partitions (`YYYY-MM:prefix`) with a current load in both datasets. -#}
{% macro shared_census_partitions(dataset_a, dataset_b) %}
    select to_date(split_part(partition_key, ':', 1), 'YYYY-MM') as month,
        split_part(partition_key, ':', 2) as hs_prefix
    from {{ source('raw', 'load_manifest') }}
    where dataset = '{{ dataset_a }}' and status = 'succeeded'
    intersect
    select to_date(split_part(partition_key, ':', 1), 'YYYY-MM') as month,
        split_part(partition_key, ':', 2) as hs_prefix
    from {{ source('raw', 'load_manifest') }}
    where dataset = '{{ dataset_b }}' and status = 'succeeded'
{% endmacro %}
