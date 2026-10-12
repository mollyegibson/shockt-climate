-- Pins us_and_territories_iso2 to known codes: returns any expected code missing, or a foreign country included.
with known (iso2, expected) as (
    values ('US', true), ('PR', true), ('VI', true), ('GU', true), ('AS', true), ('MP', true),
           ('CA', false), ('MX', false)
),

included as ({{ us_and_territories_iso2() }})

select known.iso2, known.expected
from known
where known.expected <> (known.iso2 in (select iso2 from included))
