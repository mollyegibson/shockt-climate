{#- Whether a Climate TRACE ship type is a container ship: `container` in OceanMind's names, `cargo.container` in Global Fishing Watch's. -#}
{% macro is_container_ship(vessel_type) %}
    ({{ vessel_type }} in ('container', 'cargo.container'))
{% endmacro %}
