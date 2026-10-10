-- One row per month × chokepoint: totals and daily means of transits and estimated trade volume.
select
    date_trunc('month', date)::date as month,
    chokepoint_id,
    chokepoint_name,
    count(*) as days_reported,
    sum(n_container) as n_container,
    sum(n_cargo) as n_cargo,
    sum(n_total) as n_total,
    sum(container_t) as container_t,
    sum(cargo_t) as cargo_t,
    sum(total_t) as total_t,
    avg(n_container) as n_container_daily_mean,
    avg(n_cargo) as n_cargo_daily_mean,
    avg(container_t) as container_t_daily_mean
from {{ ref('fct_chokepoint_transits_daily') }}
group by 1, 2, 3
