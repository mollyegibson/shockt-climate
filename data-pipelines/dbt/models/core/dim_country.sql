-- Census countries (Schedule C), plus any country code seen in the trade data but missing from the schedule.
with schedule as (
    select census_cty_code, cty_name, nullif(iso3, '') as iso3
    from {{ ref('seed_census_countries') }}
),

seen as (
    select census_cty_code, max(cty_name) as cty_name
    from (
        select cty_code as census_cty_code, cty_name from {{ source('raw', 'census_hs') }}
        union all
        select cty_code, cty_name from {{ source('raw', 'census_porths') }}
        union all
        select cty_code, cty_name from {{ source('raw', 'census_statehs') }}
    ) as codes
    where census_cty_code ~ '^[0-9]{4}$'
    group by census_cty_code
)

select
    coalesce(schedule.census_cty_code, seen.census_cty_code) as census_cty_code,
    coalesce(schedule.cty_name, seen.cty_name) as cty_name,
    schedule.iso3,
    {{ census_country_region('coalesce(schedule.census_cty_code, seen.census_cty_code)') }} as region,
    schedule.census_cty_code is null as missing_from_schedule
from schedule
full outer join seen using (census_cty_code)
