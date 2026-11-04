# Port Countries from Coordinates

**Status:** Future · **Workstream:** Data engineering · **Date:** 2026-11-04

Climate TRACE gives every port a country (`other4` for the start port, `other5` for the end port), and the `core` models trust it: it decides which origin a voyage counts for, and so which origin's lane a departure port belongs to. This plan replaces the label with a country assigned from the port's own coordinates, by a sourced boundary file and a tested generator. Until then the source's labels are used, and known mislabels are recorded in the [ingestion plan](./data-ingestion-pipelines.md), Section 9.

## 1. Why

- **A known mislabel (2026-11-04):** Indonesia's only departure port, `IDN_1581515630` ("Kampong Tanjong Kupang", 12 container voyages to the US), has its voyages' points at a median 1.36° N, 103.55° E, in the Strait of Johor west of Singapore, which places it in Malaysia rather than Indonesia. Indonesia's sea lane therefore starts there and leaves out the leg from Indonesia. The same port is a feeder hub, with 976 voyages from the feeder origins (Section 5.7.1 of the ingestion plan).
- **The extent is unknown.** A check matching each port to its nearest GeoNames city failed, because `geonames_cities` holds US and Mexican cities only (`config/sources.yaml`: `countries: [US, MX]`).

## 2. Options considered

| Option | Cost | Result |
|---|---|---|
| Keep the source's labels (current) | None | Mislabels stay unknown |
| Load GeoNames cities for every country; each port takes its nearest city's country, as a dbt rule | About 31 MB in `raw` (69,793 rows in `cities5000`, at the current 440 bytes a row), with the database at 854 MB of 1,024 MB | Uses an existing loader; can be wrong for ports near a border |
| **A boundary file and a generator (this plan)** | A new reference source and generator; a seed of a few hundred rows | Each port placed inside a country's boundary; little storage |

## 3. Design

1. **Source:** a country boundary file at a scale fine enough for coastlines, for example Natural Earth's 1:10m Admin 0 countries (public domain). The source, version, URL and licence are confirmed and pinned under `reference_sources` in `config/sources.yaml` before use, and the download is archived like the other reference files.
2. **Generator:** `shockt ref port-countries` reads every Climate TRACE port ID with its median start or end point (US voyages, feeder voyages) from `core`, places each point in a country polygon, and writes `dbt/seeds/seed_port_countries.csv` (port ID, ISO3, method, distance to the boundary in km, source version).
   - **Ports at sea:** a port's point can fall just outside every polygon, since ports sit on the coast. Such a port takes the nearest polygon within a configured distance (`port_countries.max_offshore_km` in `config/transforms.yaml`), recorded as `nearest`; beyond it, the country is null and a warning lists the port.
   - **ISO3:** taken from the boundary file's ISO 3166 code, checked against `seed_census_countries`; disputed or unassigned territories are listed rather than guessed.
3. **dbt:**
   - The staging macro `staged_climatetrace_voyages` adds `start_port_iso3` and `end_port_iso3` from the seed, keeping the source labels as `start_iso3_label` and `end_iso3_label`.
   - `dim_departure_ports`, `fct_node_weights_monthly`, `agg_observed_sea_distances_monthly` and `agg_feeder_hub_shares_monthly` use the assigned country.
   - A warning lists ports whose assigned country differs from the label, with their voyages.
4. **Tests:**
   - The generator is pinned to known ports, including one at sea that takes its nearest polygon.
   - `tests/test_reference_seeds.py` fails if the seed differs from its generator.

## 4. Open questions

1. Which boundary file and scale? The scale has to place coastal ports correctly; the size of the archived file grows with it.
2. If a port changes country, its voyages move to another origin. Does that change which origins need feeder voyages (Indonesia may have no direct US voyages of its own)?
3. Should the seed also hold the ports' coordinates, so `dim_departure_ports` and the hub nodes read one placement?
