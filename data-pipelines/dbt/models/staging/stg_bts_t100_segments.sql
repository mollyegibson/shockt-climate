-- BTS T-100 International Segment freight from the current loads: month, carrier and airport pair, with freight in tonnes. Rows the source repeats are kept, since each is a reported segment.
{% set tonnes_per_pound = 0.45359237 / 1000 %}

select
    make_date(s.year, s.month, 1) as month,
    s.unique_carrier,
    s.origin_airport_id,
    s.origin as origin_iata,
    s.origin_country as origin_iso2,
    s.dest_airport_id,
    s.dest as dest_iata,
    s.dest_country as dest_iso2,
    s.class as service_class,
    s.aircraft_config,
    s.aircraft_type,
    s.departures_performed,
    s.freight * {{ tonnes_per_pound }} as freight_t,
    s.mail * {{ tonnes_per_pound }} as mail_t,
    s.distance as distance_mi,
    s.load_id
from {{ source('raw', 'bts_t100_segments') }} as s
where s.load_id in ({{ succeeded_loads('bts_t100_segments') }})
