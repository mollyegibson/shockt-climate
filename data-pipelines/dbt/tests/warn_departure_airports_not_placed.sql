-- Departure airports in T-100 that OurAirports can't place by IATA code and country: their freight has no departure node, so it is left out.
{{ config(severity='warn') }}

select iata_code, iso2, freight_t
from {{ ref('dim_departure_airports') }}
where lat is null
