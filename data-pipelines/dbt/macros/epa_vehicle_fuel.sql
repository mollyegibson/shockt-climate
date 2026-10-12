{#-
  The fuel each EPA Hub vehicle type burns, as a UK conversion-factor fuel (Fuels > Liquid fuels).
  EPA factors cover combustion only; the fuel's UK well-to-tank to combustion ratio makes them
  well-to-wheel. Vehicle types not listed get no well-to-wheel factor.
-#}
{% macro epa_vehicle_fuels() %}
    {{ return({
        'Medium- and Heavy-Duty Truck': 'Diesel (100% mineral diesel)',
        'Rail': 'Diesel (100% mineral diesel)',
    }) }}
{% endmacro %}

{% macro epa_vehicle_fuel(vehicle_type) %}
    case {{ vehicle_type }}
        {% for vehicle, fuel in epa_vehicle_fuels().items() %}
        when '{{ vehicle }}' then '{{ fuel }}'
        {% endfor %}
    end
{% endmacro %}
