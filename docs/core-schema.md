# Core Schema

Every table dbt builds in the `core` schema of the ShockT Climate database, and the distance seeds it loads into `raw`, with every column. Columns are as the models produce them; each table's purpose and column notes are in `data-pipelines/dbt/models/core/_core.yml` and `data-pipelines/dbt/seeds/_seeds.yml`, and the design is in the [data ingestion plan](plans/data-ingestion-pipelines.md). The `data-pipelines` README has a compact version of these diagrams.

**Reading the diagrams:** `PK` columns are a table's key (its uniqueness test), `FK` columns join another table. A solid line is a join a dbt relationships test enforces; a dotted line is a join the models use without one. A table that already appeared in an earlier diagram shows only its key.

When a model's columns, keys or joins change, update this file in the same pull request.

## Imports and weight ratios

Census imports at country, port, state and state-port grain, with the kg-per-dollar ratios and the Mexico overland estimate built on them. `dim_country`, `dim_port` and `dim_hs` are the hubs.

```mermaid
erDiagram
  dim_country {
    text census_cty_code PK
    text cty_name
    text iso3
    text region
    bool missing_from_schedule
  }
  dim_hs {
    text hs10 PK
    text hs6
    text hs4
    text description
    text_array cases
  }
  dim_port {
    text port_code PK
    text port_name
    text district_code
    text state
    bool is_border_crossing
    float lat
    float lon
    text location_method
    text coast_region
    text named_airport_iata
    float city_lat
    float city_lon
    text municipality_airport_iata
    bool missing_from_schedule
  }
  dim_census_air_ports {
    text port_code PK, FK
    text port_name
    text state
    numeric air_weight_t
    numeric air_weight_share
    text iata_code
    text airport_name
    float lat
    float lon
    text match_method
    float city_to_airport_km
  }
  fct_imports_monthly {
    date month PK
    text hs10 PK, FK
    text hs6
    text census_cty_code PK, FK
    text mode PK
    bigint value_usd
    numeric weight_t
    text weight_method
    bigint charges_usd
    uuid load_id
  }
  fct_import_duties_monthly {
    date month PK
    text hs10 PK, FK
    text hs6
    text census_cty_code PK, FK
    bigint consumption_value_usd
    bigint dutiable_value_usd
    bigint calculated_duty_usd
    uuid load_id
  }
  fct_imports_port_monthly {
    date month PK
    text hs6 PK
    text census_cty_code PK, FK
    text port_code PK, FK
    text mode PK
    bigint value_usd
    numeric weight_t
    text weight_method
    uuid load_id
    text coast_region
  }
  fct_imports_state_monthly {
    date month PK
    text hs6 PK
    text census_cty_code PK, FK
    text state PK
    text mode PK
    bigint value_usd
    numeric weight_t
    text weight_method
    uuid load_id
  }
  fct_imports_state_port_quarterly {
    date quarter PK
    text state PK
    text unlading_port_code PK, FK
    text entry_port_code PK, FK
    text census_cty_code PK, FK
    text mode PK
    bigint value_usd
    numeric weight_t
    text weight_method
    uuid load_id
    text unlading_coast_region
  }
  agg_air_vessel_kg_per_usd {
    text hs6 PK
    text census_cty_code PK, FK
    numeric air_vessel_value_usd
    numeric air_vessel_weight_kg
    numeric kg_per_usd
    bool meets_minimum
    numeric kg_per_usd_low
    numeric kg_per_usd_high
  }
  fct_mexico_overland_monthly {
    date month PK
    text hs6 PK, FK
    text port_code PK, FK
    text mode PK
    numeric value_usd
    numeric weight_t
    numeric weight_t_low
    numeric weight_t_high
    text weight_method
    text ratio_source
    numeric kg_per_usd
    numeric kg_per_usd_low
    numeric kg_per_usd_high
    text split_source
    uuid load_id
    uuid transborder_load_id
  }
  dim_country ||--o{ fct_imports_monthly : "census_cty_code"
  dim_country ||--o{ fct_import_duties_monthly : "census_cty_code"
  dim_country ||--o{ fct_imports_port_monthly : "census_cty_code"
  dim_country ||--o{ fct_imports_state_monthly : "census_cty_code"
  dim_country ||--o{ fct_imports_state_port_quarterly : "census_cty_code"
  dim_hs ||--o{ fct_imports_monthly : "hs10"
  dim_hs ||--o{ fct_import_duties_monthly : "hs10"
  dim_port ||--o{ fct_imports_port_monthly : "port_code"
  dim_port ||--o{ fct_imports_state_port_quarterly : "entry port"
  dim_port ||--o{ fct_imports_state_port_quarterly : "unlading port"
  dim_port ||--o{ fct_mexico_overland_monthly : "port_code"
  dim_port ||..o| dim_census_air_ports : "port_code"
  dim_country |o..o{ agg_air_vessel_kg_per_usd : "census_cty_code, null for all origins"
  agg_air_vessel_kg_per_usd ||..o{ fct_mexico_overland_monthly : "hs6 ratio and range"
```

- `dim_country`: Census Schedule C countries with ISO3 and analysis region.
- `dim_hs`: HS-10 codes seen in the country-level data, with the cases they belong to.
- `dim_port`: Census Schedule D ports, each placed at a point (a US–Mexico crossing, a named airport, its GeoNames city or an airport in its municipality) and given a coast region by `coast_region`, the same rule as the Climate TRACE ports.
- `dim_census_air_ports`: Census ports with air imports of the case HS codes, each placed at an OurAirports airport by a scripted match: by airport name when the port name names an airport, else the nearest large airport within `air_ports.city_radius_km` (config/transforms.yaml) of the port's GeoNames city, else the nearest airport; a city GeoNames lacks is matched by airport municipality.
- `fct_imports_monthly`: Country-level imports by month, HS-10, country and mode, with Census's import charges (`charges_usd`: freight, insurance and other costs to the first US port; `other` is general minus air and vessel charges). Null for partitions loaded before charges were requested.
- `fct_import_duties_monthly`: Duty on country-level imports for consumption by month, HS-10 and country: consumption value, dutiable value and Census's calculated duty. Duty isn't reported by mode.
- `fct_imports_port_monthly`: Imports by month, HS-6, country, port of unlading and mode, with the port's coast region.
- `fct_imports_state_monthly`: Imports by month, HS-6, country, state of destination and mode.
- `fct_imports_state_port_quarterly`: Imports of all goods (no HS code) by quarter, state of destination, port of unlading, port of entry, country and mode (air and vessel only), from Census State/Port Imports, with the unlading port's coast region.
- `agg_air_vessel_kg_per_usd`: Kg per dollar of air and vessel imports by HS-6 and origin over the loaded months, and across all origins (`census_cty_code` null): the basis for estimating overland weight from value.
- `fct_mexico_overland_monthly`: Imports from Mexico across the land border by month, HS-6, border crossing and mode (truck, rail): Census overland value at each crossing, split by TransBorder's truck and rail shares for the chapter, with weight estimated from the code's kg per dollar in air and vessel shipments and a range from value-weighted percentiles across origins (plan section 7.3).

## Voyages, chokepoints and emission factors

Climate TRACE voyages and their lanes, PortWatch chokepoint transits (time series compared with the imports by month), and the emission factors the engine chooses from through `engine/config/leg_factors.yaml`.

```mermaid
erDiagram
  dim_country {
    text census_cty_code PK
  }
  dim_climatetrace_ports {
    text end_port_id PK
    text port_name
    float lon
    float lat
    text coast_region
    bigint voyages
    bigint container_voyages
  }
  fct_voyages {
    text asset_identifier PK
    text model_source
    timestamptz started_at PK
    date start_month
    timestamptz ended_at
    text vessel_name
    text start_port
    text start_iso3 FK
    text origin_region
    text end_port
    text end_port_id FK
    text end_coast_region
    float distance_nm
    float distance_km
    numeric duration_h
    float co2e_t
    float co2e_t_per_km
    uuid load_id
  }
  agg_voyage_lanes_monthly {
    date month PK
    text origin_iso3 PK, FK
    text origin_region
    text end_coast_region PK
    bigint n_voyages
    float total_distance_km
    float mean_distance_km
    float median_distance_km
    numeric mean_duration_h
    float total_co2e_t
    float co2e_t_per_km
  }
  fct_chokepoint_transits_daily {
    date date PK
    text chokepoint_id PK
    text chokepoint_name
    int n_container
    int n_dry_bulk
    int n_general_cargo
    int n_roro
    int n_tanker
    int n_cargo
    int n_total
    bigint container_t
    bigint dry_bulk_t
    bigint general_cargo_t
    bigint roro_t
    bigint tanker_t
    bigint cargo_t
    bigint total_t
    uuid load_id
  }
  fct_chokepoint_transits_monthly {
    date month PK
    text chokepoint_id PK
    text chokepoint_name
    bigint days_reported
    bigint n_container
    bigint n_cargo
    bigint n_total
    numeric container_t
    numeric cargo_t
    numeric total_t
    numeric n_container_daily_mean
    numeric n_cargo_daily_mean
    numeric container_t_daily_mean
  }
  ref_emission_factors {
    text source PK
    text source_row_id
    text mode
    text variant PK
    text vehicle_type
    text size_class
    text haul
    bool radiative_forcing
    text fuel
    float ttw_kg_co2e_per_tkm
    float wtt_kg_co2e_per_tkm
    float wtw_kg_co2e_per_tkm
    text wtt_method
    text wtt_source_row_ids
    float wtt_to_ttw_ratio
    uuid load_id
  }
  dim_climatetrace_ports ||..o{ fct_voyages : "end_port_id"
  dim_country ||..o{ fct_voyages : "start_iso3 = iso3"
  dim_country ||..o{ agg_voyage_lanes_monthly : "origin_iso3 = iso3"
```

- `dim_climatetrace_ports`: US arrival ports in the Climate TRACE voyages, rebuilt on every run: median coordinates of the voyages' end points, the most common port name, the coast region from the `coast_region` macro, and voyage counts (all ship types and container ships) for the loaded years and lanes.
- `fct_voyages`: Container-ship voyages (Climate TRACE) from the configured Asian origins and Mexico to US ports.
- `agg_voyage_lanes_monthly`: Container-ship voyages by start month, origin country and US coast region: voyage count, distance sailed, duration and CO2e.
- `fct_chokepoint_transits_daily`: Daily ship transits through the configured chokepoints (IMF PortWatch), by ship type, with estimated trade volume in metric tons (each ship's estimated payload share × deadweight tonnage).
- `fct_chokepoint_transits_monthly`: Monthly totals and daily means of chokepoint transits; a partial month has fewer `days_reported`.
- `ref_emission_factors`: Every freight emission factor per tonne-km in the UK government conversion factors and the EPA GHG Emission Factors Hub, in kg CO2e: tank-to-wheel, well-to-tank and well-to-wheel.

## Nodes

Every place a leg starts or ends. One model places each kind; `dim_nodes` combines them, keyed `kind:source_key`.

```mermaid
erDiagram
  dim_country {
    text census_cty_code PK
  }
  dim_port {
    text port_code PK
  }
  dim_census_air_ports {
    text port_code PK, FK
  }
  dim_departure_ports {
    text start_port_id PK
    text port_name
    text iso3 FK
    float lon
    float lat
    bigint container_voyages
  }
  dim_departure_airports {
    text iata_code PK
    text iso2
    text iso3 FK
    text airport_name
    float lat
    float lon
    float freight_t
  }
  dim_mexico_plants {
    bigint plant_id
    text name
    text scian_code PK
    text industry_name
    text employee_band
    int employee_band_min
    text state_name
    text municipality
    float lat PK
    float lon PK
  }
  map_crossing_plant {
    text port_code PK, FK
    text hs6 PK
    bigint plant_id FK
    float great_circle_km
  }
  dim_destination_states {
    text state PK
    text town
    float lat
    float lon
    float centre_lat
    float centre_lon
    float centre_to_town_km
    numeric population
    bigint cities
  }
  dim_nodes {
    text node_id PK
    text kind
    text name
    text iso3
    float lat
    float lon
    text coast_region
    text location_method
    text source_key
  }
  dim_mexico_plants ||--o{ map_crossing_plant : "plant_id"
  dim_port ||..o| dim_census_air_ports : "port_code"
  dim_country ||..o{ dim_departure_ports : "iso3"
  dim_country ||..o{ dim_departure_airports : "iso3"
  dim_port ||..o{ map_crossing_plant : "crossing port_code"
  dim_departure_ports ||..|| dim_nodes : "departure_port"
  dim_departure_airports ||..|| dim_nodes : "departure_airport"
  dim_port ||..o| dim_nodes : "arrival_seaport and border_crossing"
  dim_census_air_ports ||..o| dim_nodes : "air_gateway"
  dim_mexico_plants ||..o| dim_nodes : "mexico_plant"
  dim_destination_states ||..|| dim_nodes : "destination_state"
```

- `dim_departure_ports`: Climate TRACE start ports in the origin countries that container ships sailed from to the US, each at the median start point of its voyages.
- `dim_departure_airports`: Airports in the origin countries that flew freight to the US in BTS T-100, placed by IATA code and country with OurAirports.
- `dim_mexico_plants`: DENUE establishments in the case industries whose employee band starts at or above `mexico_sites.min_employees`, one per industry and location.
- `map_crossing_plant`: The nearest large plant, by great-circle distance, for each border crossing and HS-6 code with overland imports, among codes whose industries DENUE covers.
- `dim_destination_states`: US states of destination with case imports, each at the GeoNames town nearest the population-weighted centre of its cities.
- `dim_nodes`: Every place a leg starts or ends: departure ports and airports, US arrival seaports, air gateways and border crossings, Mexican plants and US destination states.

## Node weights and distances

How much case freight each node carries, and the distances between nodes. The `seed_*` tables are written by the `shockt ref` distance commands and load into `raw`.

```mermaid
erDiagram
  dim_country {
    text census_cty_code PK
  }
  dim_nodes {
    text node_id PK
  }
  fct_node_weights_monthly {
    date month PK
    text node_id PK, FK
    text census_cty_code PK, FK
    text hs6 PK
    text mode PK
    text lane_coast_region PK
    float weight_t
    float weight_t_low
    float weight_t_high
    text weight_basis
  }
  agg_observed_sea_distances_monthly {
    date month PK
    text origin_iso3 PK, FK
    text arrival_node_id PK, FK
    bigint n_voyages
    float median_distance_km
    numeric mean_duration_h
  }
  seed_sea_distances {
    text from_node_id PK, FK
    text to_node_id PK, FK
    text scenario PK
    numeric km
    text passages
    text source
  }
  seed_air_distances {
    text from_node_id PK, FK
    text to_node_id PK, FK
    numeric km
    text source
  }
  seed_road_distances {
    text from_node_id PK, FK
    text to_node_id PK, FK
    numeric km
    numeric duration_h
    text osm_date
    text graph_date
    text engine_version
    text source
  }
  seed_rail_distances {
    text from_node_id PK, FK
    text to_node_id PK, FK
    numeric km
    numeric from_snap_km
    numeric to_snap_km
    text network_version
    text source
  }
  dim_nodes ||--o{ agg_observed_sea_distances_monthly : "arrival seaport"
  dim_nodes ||--o{ fct_node_weights_monthly : "node_id"
  dim_nodes ||--o{ seed_air_distances : "from"
  dim_nodes ||--o{ seed_air_distances : "to"
  dim_nodes ||--o{ seed_rail_distances : "from"
  dim_nodes ||--o{ seed_rail_distances : "to"
  dim_nodes ||--o{ seed_road_distances : "from"
  dim_nodes ||--o{ seed_road_distances : "to"
  dim_nodes ||--o{ seed_sea_distances : "from"
  dim_nodes ||--o{ seed_sea_distances : "to"
  dim_country ||..o{ fct_node_weights_monthly : "origin census_cty_code"
  dim_country ||..o{ agg_observed_sea_distances_monthly : "origin_iso3 = iso3"
```

- `fct_node_weights_monthly`: Case tonnage each node carries by month, origin country, HS-6 and mode, with a low–high range where the tonnage is estimated.
- `agg_observed_sea_distances_monthly`: Observed sea distance by month, origin country and US arrival seaport, from container voyages ending within `arrival_ports.voyage_radius_km` of the port.
- `seed_sea_distances`: searoute distances from departure ports to arrival seaports, per scenario (`shockt ref sea-distances`).
- `seed_air_distances`: Geodesic distances from departure airports to air gateways (`shockt ref air-distances`).
- `seed_road_distances`: openrouteservice heavy-vehicle distances for truck legs (`shockt ref road-distances`).
- `seed_rail_distances`: Shortest-track distances for rail legs on the BTS North American Rail Network (`shockt ref rail-distances`).
