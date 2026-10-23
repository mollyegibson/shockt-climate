-- EU imports by month × HS-6 × reporter × partner × transport mode, with mode labels.
select
    c.month,
    c.hs6,
    c.reporter,
    c.partner,
    c.transport_mode as transport_mode_code,
    case c.transport_mode
        when '1' then 'sea'
        when '2' then 'rail'
        when '3' then 'road'
        when '4' then 'air'
        when '8' then 'inland_waterway'
        else 'other'
    end as transport_mode,
    c.quantity_kg,
    c.value_eur,
    c.load_id
from {{ ref('stg_comext_trade') }} as c
