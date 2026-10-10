-- One row per HS-10 code seen in the country-level data, with the cases whose prefix it matches.
with codes as (
    select distinct on (hs10) hs10, hs6, hs10_description
    from {{ ref('stg_census_hs') }}
    order by hs10, month desc
)

select
    codes.hs10,
    codes.hs6,
    left(codes.hs10, 4) as hs4,
    codes.hs10_description as description,
    array(
        select distinct unnest(string_to_array(c.cases, '|'))
        from {{ ref('seed_hs_case_codes') }} as c
        where codes.hs10 like c.hs_prefix || '%'
        order by 1
    ) as cases
from codes
