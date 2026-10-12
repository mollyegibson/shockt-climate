-- Pins census_country_region to known countries; returns any that classify differently.
with known_countries (code, expected) as (
    values ('5830', 'asia'), ('5700', 'asia'), ('5880', 'asia'), ('2010', 'mexico'), ('1220', 'other'), ('4280', 'other')
)

select code, expected, {{ census_country_region('code') }} as actual
from known_countries
where {{ census_country_region('code') }} <> expected
