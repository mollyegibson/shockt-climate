-- Pins the factor attribute macros to known rows; returns any factor whose attributes differ.
with known (source, variant, vehicle_type, size_class, haul, radiative_forcing) as (
    values
        ('uk_desnz', 'Cargo ship / Container ship / Average', 'container_ship', 'average', null, null::boolean),
        ('uk_desnz', 'Cargo ship / Container ship / 8000+ TEU', 'container_ship', '8000_plus_teu', null, null::boolean),
        ('uk_desnz', 'Cargo ship / Bulk carrier / 10,000–34,999 dwt', 'bulk_carrier', '10000_34999_dwt', null, null::boolean),
        ('uk_desnz', 'Sea tanker / LPG Tanker / Average', 'lpg_tanker', 'average', null, null::boolean),
        ('uk_desnz', 'Freight flights / International, to/from non-UK / With RF', 'freight_flight', null, 'international', true),
        ('uk_desnz', 'Freight flights / Short-haul, to/from UK / Without RF', 'freight_flight', null, 'short_haul_uk', false),
        ('uk_desnz', 'Rail / Freight train', 'rail', null, null, null::boolean),
        ('epa_hub', 'Medium- and Heavy-Duty Truck', 'medium_heavy_duty_truck', null, null, null::boolean),
        ('epa_hub', 'Rail', 'rail', null, null, null::boolean)
)

select known.*, factor.vehicle_type as actual_vehicle_type, factor.size_class as actual_size_class,
    factor.haul as actual_haul, factor.radiative_forcing as actual_radiative_forcing
from known
left join {{ ref('ref_emission_factors') }} as factor using (source, variant)
where factor.vehicle_type is distinct from known.vehicle_type
    or factor.size_class is distinct from known.size_class
    or factor.haul is distinct from known.haul
    or factor.radiative_forcing is distinct from known.radiative_forcing
