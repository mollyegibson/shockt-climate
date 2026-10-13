-- Census charges and duty hold together on every country-level row: general charges are at least
-- air plus vessel charges, containerized charges are part of vessel charges, and dutiable value is
-- part of consumption value. Rows loaded before these fields were requested are null and skipped.
select
    month,
    hs10,
    census_cty_code,
    general_charges_usd,
    air_charges_usd,
    vessel_charges_usd,
    containerized_charges_usd,
    dutiable_value_usd,
    consumption_value_usd
from {{ ref('stg_census_hs') }}
where general_charges_usd < air_charges_usd + vessel_charges_usd
    or containerized_charges_usd > vessel_charges_usd
    or dutiable_value_usd > consumption_value_usd
