# Data access: `shockt_analysis.core`

The only module that reads the database. Every function takes a `psycopg.Connection`
(from `core.connect(get_settings())`) as its first argument and returns a Polars
`DataFrame` unless noted otherwise. The connection is read-only.

## Helper

### `frame(conn, sql, params=None) → DataFrame`
Run arbitrary SQL and return the result as a Polars DataFrame. Use only when no
purpose-built reader below covers the query.

## Country and product references

### `origins(conn) → DataFrame`
Configured origin countries (those with a region other than `other`).
Columns: `census_cty_code`, `iso3`, `cty_name`, `region`.

### `countries(conn) → DataFrame`
All Census Schedule C countries, including those with region `other`.
Columns: `census_cty_code`, `cty_name`, `iso3`, `region`.

### `case_codes(conn) → DataFrame`
HS prefixes and the cases each belongs to (from `raw.seed_hs_case_codes`).
Columns: `hs_prefix`, `cases`.

## OECD maritime

### `oecd_maritime_emissions(conn, ref_area="W") → DataFrame`
Monthly OECD maritime CO₂ by vessel type for one ref_area (default: world aggregate).
Columns: `month`, `vessel`, `co2_t`.

## CBAM

### `cbam_default_values(conn) → DataFrame`
All CBAM default emission values from the current load.
Columns: `country`, `sector`, `cn_code`, `description`, `production_route`,
`direct_emissions`, `indirect_emissions`, `total_emissions`.

## SBTi

### `sbti_companies(conn) → DataFrame`
All SBTi companies from the current load.
Columns: `company_name`, `location`, `sbti_region`, `sector`, `near_term_status`,
`long_term_status`, `net_zero_status`, `net_zero_year`.

## New-source country keys

### `cbam_countries(conn) → DataFrame`
Distinct countries in the current CBAM default values, with the number of CN codes each.
Columns: `country`, `n_cn_codes`.

### `ceda_country_codes(conn) → DataFrame`
Distinct (country_code, country) pairs in the current Open CEDA factors.
Columns: `country_code`, `country`.

### `oecd_ref_areas(conn) → DataFrame`
Distinct ref_area codes in the current OECD maritime emissions, with observation counts.
Columns: `ref_area`, `n_obs`.

### `sbti_locations(conn) → DataFrame`
Distinct (location, region) pairs in the current SBTi companies, with company counts.
Columns: `location`, `region`, `n_companies`.

## Trade data

### `supply(conn, hs6: list[str]) → DataFrame`
Monthly tonnage by origin, HS-6 and delivery mode: air, vessel, truck, rail. Includes
low/high estimates for Mexican overland modes.
Columns: `month`, `census_cty_code`, `iso3`, `cty_name`, `hs6`, `mode`, `weight_t`,
`weight_t_low`, `weight_t_high`.

### `imports_by_port(conn, hs6: list[str]) → DataFrame`
Monthly air and vessel tonnage by origin, HS-6, US port and its coast region.
Columns: `month`, `census_cty_code`, `iso3`, `region`, `hs6`, `mode`, `port_code`,
`coast_region`, `weight_t`.

### `imports_by_state(conn, hs6: list[str]) → DataFrame`
Monthly air and vessel tonnage by origin, HS-6 and state of destination.
Columns: `month`, `census_cty_code`, `iso3`, `region`, `hs6`, `mode`, `state`,
`weight_t`.

### `state_port_vessel(conn, region: str) → DataFrame`
All-goods quarterly vessel tonnage from one origin region, by state and the coast
region of the port of unlading.
Columns: `quarter`, `state`, `unlading_coast_region`, `weight_t`.

### `duties(conn, hs6: list[str]) → DataFrame`
Monthly duty by HS-10 and country: consumption value, dutiable value, calculated duty.
Columns: `month`, `hs10`, `hs6`, `census_cty_code`, `iso3`, `cty_name`,
`consumption_value_usd`, `dutiable_value_usd`, `calculated_duty_usd`.

### `air_values(conn, hs6: list[str]) → DataFrame`
Monthly air value and shipping weight by origin and HS-6 (for weight-quality checks).
Columns: `month`, `census_cty_code`, `hs6`, `value_usd`, `weight_t`.

### `eu_imports(conn, hs6: list[str]) → DataFrame`
Monthly EU imports from extra-EU partners, by HS-6, partner and transport mode.
Columns: `month`, `hs6`, `partner`, `transport_mode`, `quantity_kg`, `value_eur`,
`reporter_count`.

## Distances and geography

### `distances(conn, seed: str, scenario: str | None = None) → dict[(str, str), float]`
`(from_node, to_node) → km` from one distance seed. `seed` is one of `sea`, `air`,
`road`, `rail`. For `sea`, `scenario` selects the routing scenario (default `open`;
also `panama_closed`, `red_sea_closed`). Returns a dict, not a DataFrame.

### `node_weights(conn, hs6: list[str]) → DataFrame`
Node weights by month, origin, HS-6 and mode, with each node's kind and coast region.
Columns: `month`, `node_id`, `kind`, `coast_region`, `census_cty_code`, `hs6`, `mode`,
`lane_coast_region`, `weight_t`.

### `observed_sea(conn) → DataFrame`
Observed sea distance by month, origin and US arrival seaport (from Climate TRACE
voyage data).
Columns: `month`, `origin_iso3`, `arrival_node_id`, `n_voyages`,
`median_distance_km`, `mean_duration_h`.

### `crossing_plants(conn) → DataFrame`
For each border crossing and HS-6, the Mexican plant node its leg starts at.
Columns: `crossing_node_id`, `hs6`, `plant_node_id`.

### `voyage_lanes(conn) → DataFrame`
Container voyages by month, origin country and US coast region, with distances.
Columns: `month`, `origin_iso3`, `origin_region`, `end_coast_region`, `n_voyages`,
`total_distance_km`, `median_distance_km`, `mean_duration_h`.

## Emission factors

### `factors(conn) → list[Factor]`
All emission factors from `core.ref_emission_factors`. Returns `Factor` dataclass
instances (from `shockt_engine`), not a DataFrame.

### `factor_components(conn) → DataFrame`
TTW, WTT and WTW components from the UK DESNZ factors.
Columns: `variant`, `ttw_kg_co2e_per_tkm`, `wtt_kg_co2e_per_tkm`,
`wtw_kg_co2e_per_tkm`.

## Ship fuel

### `ship_fuel_intensities(conn) → DataFrame`
Per-ship annual fuel intensity from THETIS-MRV.
Columns: `imo_number`, `reporting_year`, `ship_name`, `ship_type`, `port_of_registry`,
`total_fuel_consumption_mt`, `total_co2_mt`, `total_co2eq_mt`, `time_at_sea_hours`,
`fuel_per_distance_kg_nm`, `co2_per_distance_kg_nm`, `co2_per_transport_work_mass`,
`in_voyage_data`.

## Chokepoint transits

### `chokepoint_transits(conn) → DataFrame`
Monthly transits by chokepoint: all ships and container ships, with days reported.
Columns: `month`, `chokepoint_id`, `chokepoint_name`, `days_reported`, `n_total`,
`n_container`.

## Load manifest

### `current_loads(conn, datasets: list[str]) → DataFrame`
How many partitions each dataset has and when the latest load ran.
Columns: `dataset`, `partitions`, `latest_load`, `code_versions`.
