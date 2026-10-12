{#- A source label with non-breaking spaces made plain and surrounding spaces trimmed; empty becomes null. -#}
{% macro clean_label(expr) %}
    nullif(btrim(replace({{ expr }}, chr(160), ' ')), '')
{% endmacro %}
