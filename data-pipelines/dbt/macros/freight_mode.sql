{#- Freight mode of a UK conversion factor's Level 2 or an EPA Hub Table 8 vehicle type; anything else is `other`. -#}
{% macro freight_mode(label) %}
    case
        when {{ label }} in ('Cargo ship', 'Sea tanker') then 'ocean'
        when {{ label }} in ('Freight flights', 'Aircraft') then 'air'
        when {{ label }} in ('Vans', 'Medium- and Heavy-Duty Truck') or {{ label }} like 'HGV (%' then 'truck'
        when {{ label }} = 'Rail' then 'rail'
        else 'other'
    end
{% endmacro %}
