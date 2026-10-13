-- Every loaded DENUE establishment's employee band has a lower bound; a band label in a new form needs `employee_band_min` updated first.
select id, employee_band
from {{ ref('stg_denue_establishments') }}
where employee_band_min is null
