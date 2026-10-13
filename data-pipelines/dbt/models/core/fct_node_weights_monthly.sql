/*
How much case freight each node carries, by month, origin country, HS-6 and mode: the weights that
make a lane's distance an average over the places it actually uses.

- Departure ports: the origin's case vessel tonnage to each US coast region, spread across its
  start ports by their container voyages to that region over the loaded months; an origin with no
  voyages to the region uses its voyages to every region (`weight_basis` says which). Census
  doesn't record the foreign port, so this is the only basis for the split.
- Departure airports: the origin's case air tonnage, spread across its airports by their share of
  its freight to the US in T-100 over the loaded months.
- Arrival seaports and air gateways: the port's case vessel or air tonnage, as Census reports it.
- Border crossings and the plants their legs start at: estimated truck and rail tonnage, with its
  range (`fct_mexico_overland_monthly`).
- Destination states: air and vessel tonnage as reported, and overland (`other`) tonnage estimated
  as value × kg per dollar: the origin's own ratio when its air and vessel shipments of the code
  reach the minimum, else the all-origins ratio. The range is the all-origins percentiles, widened
  to include the estimate when the origin's own ratio falls outside them.

Tonnage with no node (no departure port or airport, the unidentified state) is left out, and the
`warn_*` tests list it.
*/
with nodes as (
    select node_id, kind, source_key from {{ ref('dim_nodes') }}
),

countries as (
    select country.census_cty_code, country.iso3, seed.iso2
    from {{ ref('dim_country') }} as country
    left join {{ ref('seed_census_countries') }} as seed using (census_cty_code)
    where country.region <> 'other'
),

voyages as (
    select departure.start_port_id, departure.iso3, arrival.coast_region
    from {{ ref('stg_climatetrace_voyages') }} as v
    inner join {{ ref('dim_departure_ports') }} as departure using (start_port_id)
    inner join {{ ref('dim_climatetrace_ports') }} as arrival on arrival.end_port_id = v.end_port_id
    where v.end_iso3 = 'USA'
        and {{ is_container_ship('v.vessel_type') }}
        and not v.end_point_contradicts_end_port
),

region_shares as (
    select
        iso3,
        coast_region,
        start_port_id,
        count(*)::numeric / sum(count(*)) over (partition by iso3, coast_region) as share
    from voyages
    group by iso3, coast_region, start_port_id
),

country_shares as (
    select
        iso3,
        start_port_id,
        count(*)::numeric / sum(count(*)) over (partition by iso3) as share
    from voyages
    group by iso3, start_port_id
),

vessel_by_region as (
    select port.month, port.census_cty_code, countries.iso3, port.hs6, port.coast_region, sum(port.weight_t) as weight_t
    from {{ ref('fct_imports_port_monthly') }} as port
    inner join countries using (census_cty_code)
    where port.mode = 'vessel' and port.weight_t > 0
    group by port.month, port.census_cty_code, countries.iso3, port.hs6, port.coast_region
),

departure_ports as (
    select
        tonnage.month,
        'departure_port:' || coalesce(by_region.start_port_id, by_country.start_port_id) as node_id,
        tonnage.census_cty_code,
        tonnage.hs6,
        'vessel' as mode,
        tonnage.coast_region as lane_coast_region,
        tonnage.weight_t * coalesce(by_region.share, by_country.share) as weight_t,
        tonnage.weight_t * coalesce(by_region.share, by_country.share) as weight_t_low,
        tonnage.weight_t * coalesce(by_region.share, by_country.share) as weight_t_high,
        case when by_region.share is not null then 'voyage_share_region' else 'voyage_share_country' end as weight_basis
    from vessel_by_region as tonnage
    left join region_shares as by_region
        on by_region.iso3 = tonnage.iso3 and by_region.coast_region = tonnage.coast_region
    left join country_shares as by_country
        on by_country.iso3 = tonnage.iso3 and by_region.start_port_id is null
    where coalesce(by_region.share, by_country.share) is not null
),

airport_shares as (
    select
        iso2,
        iata_code,
        freight_t / sum(freight_t) over (partition by iso2) as share
    from {{ ref('dim_departure_airports') }}
    where lat is not null
),

departure_airports as (
    select
        air.month,
        'departure_airport:' || shares.iata_code as node_id,
        air.census_cty_code,
        air.hs6,
        'air' as mode,
        null::text as lane_coast_region,
        sum(air.weight_t) * shares.share as weight_t,
        sum(air.weight_t) * shares.share as weight_t_low,
        sum(air.weight_t) * shares.share as weight_t_high,
        't100_share' as weight_basis
    from {{ ref('fct_imports_monthly') }} as air
    inner join countries using (census_cty_code)
    inner join airport_shares as shares on shares.iso2 = countries.iso2
    where air.mode = 'air' and air.weight_t > 0
    group by air.month, shares.iata_code, air.census_cty_code, air.hs6, shares.share
),

us_ports as (
    select
        port.month,
        nodes.node_id,
        port.census_cty_code,
        port.hs6,
        port.mode,
        null::text as lane_coast_region,
        port.weight_t,
        port.weight_t as weight_t_low,
        port.weight_t as weight_t_high,
        'reported' as weight_basis
    from {{ ref('fct_imports_port_monthly') }} as port
    inner join countries using (census_cty_code)
    inner join nodes
        on nodes.source_key = port.port_code
        and nodes.kind = case port.mode when 'vessel' then 'arrival_seaport' when 'air' then 'air_gateway' end
    where port.mode in ('vessel', 'air') and port.weight_t > 0
),

mexico as (
    select census_cty_code from countries where iso3 = 'MEX'
),

crossings as (
    select
        overland.month,
        'border_crossing:' || overland.port_code as node_id,
        mexico.census_cty_code,
        overland.hs6,
        overland.mode,
        null::text as lane_coast_region,
        overland.weight_t,
        overland.weight_t_low,
        overland.weight_t_high,
        overland.weight_method as weight_basis
    from {{ ref('fct_mexico_overland_monthly') }} as overland
    cross join mexico
    where overland.weight_t > 0
),

plants as (
    select
        crossings.month,
        'mexico_plant:' || map.plant_id::text as node_id,
        crossings.census_cty_code,
        crossings.hs6,
        crossings.mode,
        null::text as lane_coast_region,
        sum(crossings.weight_t) as weight_t,
        sum(crossings.weight_t_low) as weight_t_low,
        sum(crossings.weight_t_high) as weight_t_high,
        crossings.weight_basis
    from crossings
    inner join {{ ref('map_crossing_plant') }} as map
        on 'border_crossing:' || map.port_code = crossings.node_id and map.hs6 = crossings.hs6
    group by crossings.month, map.plant_id, crossings.census_cty_code, crossings.hs6, crossings.mode, crossings.weight_basis
),

all_origins_ratio as (
    select hs6, kg_per_usd, kg_per_usd_low, kg_per_usd_high
    from {{ ref('agg_air_vessel_kg_per_usd') }}
    where census_cty_code is null
),

own_ratio as (
    select hs6, census_cty_code, kg_per_usd
    from {{ ref('agg_air_vessel_kg_per_usd') }}
    where census_cty_code is not null and meets_minimum
),

states as (
    select
        state.month,
        'destination_state:' || state.state as node_id,
        state.census_cty_code,
        state.hs6,
        state.mode,
        null::text as lane_coast_region,
        case when state.mode = 'other'
            then state.value_usd * coalesce(own.kg_per_usd, all_origins.kg_per_usd) / 1000
            else state.weight_t
        end as weight_t,
        case when state.mode = 'other'
            then state.value_usd * least(coalesce(own.kg_per_usd, all_origins.kg_per_usd), all_origins.kg_per_usd_low) / 1000
            else state.weight_t
        end as weight_t_low,
        case when state.mode = 'other'
            then state.value_usd * greatest(coalesce(own.kg_per_usd, all_origins.kg_per_usd), all_origins.kg_per_usd_high) / 1000
            else state.weight_t
        end as weight_t_high,
        case
            when state.mode <> 'other' then 'reported'
            when own.kg_per_usd is not null then 'estimated_own_ratio'
            else 'estimated_all_origins_ratio'
        end as weight_basis
    from {{ ref('fct_imports_state_monthly') }} as state
    inner join countries using (census_cty_code)
    inner join nodes on nodes.kind = 'destination_state' and nodes.source_key = state.state
    left join own_ratio as own using (hs6, census_cty_code)
    left join all_origins_ratio as all_origins using (hs6)
    where state.mode in ('air', 'vessel', 'other')
        and (state.weight_t > 0 or (state.mode = 'other' and state.value_usd > 0))
)

select * from departure_ports
union all
select * from departure_airports
union all
select * from us_ports
union all
select * from crossings
union all
select * from plants
union all
select * from states
