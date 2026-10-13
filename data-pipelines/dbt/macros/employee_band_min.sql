{#- The lower bound of a DENUE employee-size band label ("6 a 10 personas" → 6, "251 y más personas" → 251); null for a label in another form. -#}
{% macro employee_band_min(label) %}
    (substring({{ label }} from '^(\d+) (?:a \d+|y más) personas$'))::integer
{% endmacro %}
