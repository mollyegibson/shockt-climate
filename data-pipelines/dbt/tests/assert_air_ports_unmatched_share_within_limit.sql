-- Fails when Census ports with no matched airport carry more case air tonnage than `air_port_max_unmatched_share`.
select sum(air_weight_share) as unmatched_share
from {{ ref('dim_census_air_ports') }}
where match_method = 'unmatched'
having sum(air_weight_share) > {{ var('air_port_max_unmatched_share') }}
