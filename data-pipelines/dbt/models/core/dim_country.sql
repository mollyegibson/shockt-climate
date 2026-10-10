select
    census_cty_code,
    cty_name,
    nullif(iso3, '') as iso3,
    region
from {{ ref('seed_country_codes') }}
where census_cty_code <> '-'
