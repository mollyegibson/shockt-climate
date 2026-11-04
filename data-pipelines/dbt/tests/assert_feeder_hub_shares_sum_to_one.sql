-- Fails when a feeder origin's hub shares in a month don't sum to one, or a port reports two countries (which would split its voyages across rows).
select month, origin_iso3, sum(share) as total_share
from {{ ref('agg_feeder_hub_shares_monthly') }}
group by month, origin_iso3
having abs(sum(share) - 1) > 1e-9
union all
select null, hub_port_id, count(distinct hub_iso3)
from {{ ref('agg_feeder_hub_shares_monthly') }}
group by hub_port_id
having count(distinct hub_iso3) > 1
