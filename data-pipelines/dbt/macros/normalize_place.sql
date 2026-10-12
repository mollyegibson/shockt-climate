{#- Upper-case place or airport name with punctuation (periods, dashes, slashes) turned into single spaces. -#}
{% macro normalize_place(expr) %}
    trim(regexp_replace(upper({{ expr }}), '[^A-Z0-9]+', ' ', 'g'))
{% endmacro %}
