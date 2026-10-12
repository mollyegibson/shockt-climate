-- Fails when a vehicle type named in `epa_vehicle_fuels` isn't a loaded EPA ton-mile factor with a well-to-wheel value, e.g. after EPA renames it.
{% for vehicle in epa_vehicle_fuels() %}
select '{{ vehicle }}' as vehicle_type
where not exists (
    select 1
    from {{ ref('ref_emission_factors') }}
    where source = 'epa_hub' and variant = '{{ vehicle }}' and wtw_kg_co2e_per_tkm is not null
)
{% if not loop.last %}union all{% endif %}
{% endfor %}
