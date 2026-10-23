-- Comext extra-EU imports pivoted from indicator rows to quantity_kg and value_eur columns.
with raw as (
    select
        c.time_period,
        c.reporter,
        c.partner,
        c.product as hs6,
        c.flow,
        c.transport_mode,
        c.indicator,
        c.obs_value,
        c.load_id
    from {{ source('raw', 'comext_trade') }} as c
    where c.load_id in ({{ succeeded_loads('comext_trade') }})
)

select
    to_date(time_period, 'YYYY-MM') as month,
    reporter,
    partner,
    hs6,
    transport_mode,
    max(case when indicator = 'QUANTITY_KG' then obs_value end) as quantity_kg,
    max(case when indicator = 'VALUE_EUR' then obs_value end) as value_eur,
    (array_agg(load_id))[1] as load_id
from raw
group by time_period, reporter, partner, hs6, transport_mode
