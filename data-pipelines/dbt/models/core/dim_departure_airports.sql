-- Airports in the origin countries that flew freight to the US in BTS T-100, each placed by its IATA code at the OurAirports airport in the same country.
with departures as (
    select origin_iata as iata_code, origin_iso2 as iso2, sum(freight_t) as freight_t
    from {{ ref('stg_bts_t100_segments') }}
    where freight_t > 0
    group by origin_iata, origin_iso2
)

select
    departures.iata_code,
    departures.iso2,
    country.iso3,
    airport.name as airport_name,
    airport.lat,
    airport.lon,
    departures.freight_t
from departures
inner join {{ ref('seed_census_countries') }} as country on country.iso2 = departures.iso2
left join {{ ref('stg_ourairports_all_airports') }} as airport
    on airport.iata_code = departures.iata_code and airport.iso2 = departures.iso2
