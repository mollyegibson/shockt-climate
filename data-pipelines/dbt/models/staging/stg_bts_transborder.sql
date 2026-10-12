-- BTS TransBorder imports from the current loads, with the month as a date and the mode by name; `dot2` rows are by US state, `dot3` rows by port (four-digit Census codes, or a district's `DDXX` row).
select
    make_date(t.year, t.month, 1) as month,
    t.source_table,
    t.usastate,
    t.depe as port_code,
    t.commodity2 as hs2,
    t.disagmot,
    {{ transborder_mode('t.disagmot') }} as mode,
    t.country as census_cty_code,
    t.value as value_usd,
    t.shipwt as weight_kg,
    t.load_id
from {{ source('raw', 'bts_transborder') }} as t
where t.load_id in ({{ succeeded_loads('bts_transborder') }})
