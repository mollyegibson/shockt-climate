{#-
  Structured attributes of an emission factor, from the source's labels, so config can name a
  factor by what it is (`vehicle_type: container_ship`, `size_class: average`) instead of its
  label. A label these macros don't know gets null, which `assert_freight_factors_have_vehicle_type`
  catches. `assert_factor_attribute_rules` pins them to known rows.
-#}

{#- UK vehicle or ship type from Level 2 and Level 3 of `Freighting goods`. -#}
{% macro uk_vehicle_type(level_2, level_3) %}
    case
        when {{ level_2 }} in ('Cargo ship', 'Sea tanker') then case {{ level_3 }}
            when 'Container ship' then 'container_ship'
            when 'Bulk carrier' then 'bulk_carrier'
            when 'General cargo' then 'general_cargo'
            when 'Large RoPax ferry' then 'ropax_ferry'
            when 'Refrigerated cargo' then 'refrigerated_cargo'
            when 'RoRo-Ferry' then 'roro_ferry'
            when 'Vehicle transport' then 'vehicle_carrier'
            when 'Chemical tanker' then 'chemical_tanker'
            when 'Crude tanker' then 'crude_tanker'
            when 'LNG tanker' then 'lng_tanker'
            when 'LPG Tanker' then 'lpg_tanker'
            when 'Products tanker' then 'products_tanker'
        end
        when {{ level_2 }} = 'Freight flights' then 'freight_flight'
        when {{ level_2 }} = 'Rail' then 'rail'
        when {{ level_2 }} = 'HGV (non-refrigerated, all diesel)' then 'hgv'
        when {{ level_2 }} = 'HGV (refrigerated, all diesel)' then 'hgv_refrigerated'
        when {{ level_2 }} = 'Vans' then 'van'
    end
{% endmacro %}

{#- UK ship size class from Level 4: `average`, or the band as a lower-case token ("8000+ TEU" → 8000_plus_teu). Null for other modes. -#}
{% macro uk_size_class(level_2, level_4) %}
    case
        when {{ level_2 }} not in ('Cargo ship', 'Sea tanker') then null
        when {{ level_4 }} = 'Average' then 'average'
        else trim(both '_' from regexp_replace(
            replace(replace(lower({{ level_4 }}), ',', ''), '+', '_plus'), '[^a-z0-9]+', '_', 'g'
        ))
    end
{% endmacro %}

{#- UK flight haul from Level 3 of `Freight flights`. -#}
{% macro uk_haul(level_2, level_3) %}
    case when {{ level_2 }} = 'Freight flights' then case {{ level_3 }}
        when 'Domestic, to/from UK' then 'domestic_uk'
        when 'Short-haul, to/from UK' then 'short_haul_uk'
        when 'Long-haul, to/from UK' then 'long_haul_uk'
        when 'International, to/from non-UK' then 'international'
    end end
{% endmacro %}

{#- Whether a UK flight factor includes radiative forcing, from its column ("With RF" or "Without RF"). -#}
{% macro uk_radiative_forcing(level_2, column_text) %}
    case when {{ level_2 }} = 'Freight flights' then case {{ column_text }}
        when 'With RF' then true
        when 'Without RF' then false
    end end
{% endmacro %}

{#- EPA Hub Table 8 vehicle type. -#}
{% macro epa_vehicle_type(vehicle_type) %}
    case {{ vehicle_type }}
        when 'Medium- and Heavy-Duty Truck' then 'medium_heavy_duty_truck'
        when 'Rail' then 'rail'
        when 'Aircraft' then 'aircraft'
        when 'Waterborne Craft' then 'waterborne_craft'
    end
{% endmacro %}
