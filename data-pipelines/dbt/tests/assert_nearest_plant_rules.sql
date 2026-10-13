-- Pins the plant each crossing's server leg starts at to the state it should be in; returns any crossing placed differently.
with known (port_code, expected_state) as (
    values
        ('2304', 'Nuevo León'),
        ('2401', 'Chihuahua'),
        ('2408', 'Chihuahua'),
        ('2506', 'Baja California'),
        ('2604', 'Sonora')
)

select known.port_code, known.expected_state, plant.state_name
from known
left join {{ ref('map_crossing_plant') }} as crossing
    on crossing.port_code = known.port_code and crossing.hs6 = '847150'
left join {{ ref('dim_mexico_plants') }} as plant using (plant_id)
where plant.state_name is distinct from known.expected_state
