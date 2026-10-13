-- Pins the town each destination state is placed at; returns any state placed elsewhere. Nevada, Washington and Idaho have centres far from any road, which the town fixes.
with known (state, expected_town) as (
    values
        ('NV', 'Pahrump'),
        ('WA', 'North Bend'),
        ('ID', 'Boise'),
        ('TX', 'Belton'),
        ('VA', 'Ashland')
)

select known.state, known.expected_town, state.town
from known
left join {{ ref('dim_destination_states') }} as state using (state)
where state.town is distinct from known.expected_town
