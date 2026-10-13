-- Each mode in `leg_factors` (config/transforms.yaml) names exactly one emission factor with a well-to-wheel value; returns the modes that name none or several.
{% set modes = var('leg_factors') %}
with choices (mode, source, vehicle_type, size_class, haul, radiative_forcing) as (
    values
    {% for mode, choice in modes.items() %}
        (
            '{{ mode }}', '{{ choice.source }}', '{{ choice.vehicle_type }}',
            {{ "'" ~ choice.size_class ~ "'" if choice.size_class is not none else 'null' }}::text,
            {{ "'" ~ choice.haul ~ "'" if choice.haul is not none else 'null' }}::text,
            {{ choice.radiative_forcing if choice.radiative_forcing is not none else 'null' }}::boolean
        ){% if not loop.last %},{% endif %}
    {% endfor %}
)

select choices.mode, count(factor.source_row_id) as matching_factors
from choices
left join {{ ref('ref_emission_factors') }} as factor
    on factor.mode = choices.mode
    and factor.source = choices.source
    and factor.vehicle_type = choices.vehicle_type
    and (choices.size_class is null or factor.size_class = choices.size_class)
    and (choices.haul is null or factor.haul = choices.haul)
    and (choices.radiative_forcing is null or factor.radiative_forcing = choices.radiative_forcing)
    and factor.wtw_kg_co2e_per_tkm is not null
group by choices.mode
having count(factor.source_row_id) <> 1
