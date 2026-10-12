-- Pins dim_port's placement and coast region to known ports; returns any port that is missing or classified differently.
with known (port_code, expected_region, expected_border_crossing) as (
    values
        ('2704', 'west', false), ('2709', 'west', false), ('3001', 'west', false),
        ('1001', 'east', false), ('1401', 'east', false), ('1703', 'east', false), ('5201', 'east', false),
        ('5301', 'gulf', false), ('2002', 'gulf', false), ('1801', 'gulf', false),
        ('2304', 'inland', true), ('2506', 'west', true),
        ('3801', 'inland', false), ('3901', 'inland', false), ('5501', 'inland', false),
        ('3201', 'noncontiguous', false), ('4909', 'noncontiguous', false)
)

select known.port_code, known.expected_region, port.coast_region, port.is_border_crossing, port.location_method
from known
left join {{ ref('dim_port') }} as port using (port_code)
where port.port_code is null
    or port.coast_region <> known.expected_region
    or port.is_border_crossing <> known.expected_border_crossing
