-- Duty on country-level imports for consumption, one row per month × HS-10 × country. Duty isn't
-- reported by mode. Null where the partition was loaded before the duty fields were requested.
select
    month,
    hs10,
    hs6,
    census_cty_code,
    consumption_value_usd,
    dutiable_value_usd,
    calculated_duty_usd,
    load_id
from {{ ref('stg_census_hs') }}
where consumption_value_usd <> 0 or calculated_duty_usd <> 0
