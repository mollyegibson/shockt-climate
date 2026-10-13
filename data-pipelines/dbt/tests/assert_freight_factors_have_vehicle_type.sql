-- Every freight emission factor has a `vehicle_type`; a label the factor attribute macros don't know needs adding there before it can be chosen.
select source, variant
from {{ ref('ref_emission_factors') }}
where vehicle_type is null
