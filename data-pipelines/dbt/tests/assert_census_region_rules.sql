-- Pins the Census region macros to known countries and ports; returns any that classify differently.
with known_ports (port_code, expected) as (
    values ('2704', 'west'), ('2709', 'west'), ('3001', 'west'), ('1001', 'east'), ('1401', 'east'),
           ('1703', 'east'), ('5201', 'east'), ('5301', 'gulf'), ('2002', 'gulf'), ('1801', 'gulf'),
           ('2304', 'border_south'), ('2506', 'west'), ('3801', 'border_north'), ('3901', 'inland'),
           ('5501', 'inland'), ('3201', 'noncontiguous'), ('4909', 'noncontiguous')
),

known_countries (code, expected) as (
    values ('5830', 'asia'), ('5700', 'asia'), ('5880', 'asia'), ('2010', 'mexico'), ('1220', 'other'), ('4280', 'other')
)

select port_code as code, expected, {{ census_district_coast_region('left(port_code, 2)') }} as actual
from known_ports
where {{ census_district_coast_region('left(port_code, 2)') }} <> expected
union all
select code, expected, {{ census_country_region('code') }}
from known_countries
where {{ census_country_region('code') }} <> expected
