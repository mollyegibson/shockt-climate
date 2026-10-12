-- Container-ship voyages by start month, origin country and US coast region of arrival.
select
    start_month as month,
    start_iso3 as origin_iso3,
    origin_region,
    end_coast_region,
    count(*) as n_voyages,
    sum(distance_km) as total_distance_km,
    avg(distance_km) as mean_distance_km,
    percentile_cont(0.5) within group (order by distance_km) as median_distance_km,
    avg(duration_h) as mean_duration_h,
    sum(co2e_t) as total_co2e_t,
    sum(co2e_t) / nullif(sum(distance_km), 0) as co2e_t_per_km
from {{ ref('fct_voyages') }}
group by 1, 2, 3, 4
