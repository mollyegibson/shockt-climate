-- EU imports summed across reporters: month × HS-6 × partner × transport mode.
select
    month,
    hs6,
    partner,
    transport_mode,
    sum(quantity_kg) as quantity_kg,
    sum(value_eur) as value_eur,
    count(distinct reporter) as reporter_count
from {{ ref('fct_eu_imports_monthly') }}
group by month, hs6, partner, transport_mode
