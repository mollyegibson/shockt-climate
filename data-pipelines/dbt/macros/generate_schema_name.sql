{#- Use a model's configured schema as-is (`core`, `core_staging`, `raw`) rather than dbt's default `<target>_<schema>`. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}
