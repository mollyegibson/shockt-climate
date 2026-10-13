-- Census HS-10 to NAICS import concordance, every loaded year, one row per commodity and year.
select
    c.year,
    c.commodity as hs10,
    c.naics,
    c.load_id
from {{ source('raw', 'census_import_concordance') }} as c
where c.load_id in ({{ succeeded_loads('census_import_concordance') }})
    and c.naics is not null
