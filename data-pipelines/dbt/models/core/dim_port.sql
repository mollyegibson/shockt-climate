-- Census ports (Schedule D), plus any port code seen in the trade data but missing from the schedule.
with schedule as (
    select port_code, port_name
    from {{ ref('seed_census_ports') }}
),

seen as (
    select port_code, max(port_name) as port_name
    from (
        select port as port_code, port_name from {{ source('raw', 'census_porths') }}
        union all
        select district_unlading || port_unlading, null from {{ source('raw', 'census_state_port') }}
        union all
        select district_entry || port_entry, null from {{ source('raw', 'census_state_port') }}
        union all
        select depe, null from {{ source('raw', 'bts_transborder') }} where depe is not null
    ) as codes
    where port_code ~ '^[0-9]{4}$'
    group by port_code
)

select
    coalesce(schedule.port_code, seen.port_code) as port_code,
    coalesce(schedule.port_name, seen.port_name) as port_name,
    left(coalesce(schedule.port_code, seen.port_code), 2) as district_code,
    {{ census_district_coast_region('left(coalesce(schedule.port_code, seen.port_code), 2)') }} as coast_region,
    schedule.port_code is null as missing_from_schedule
from schedule
full outer join seen using (port_code)
