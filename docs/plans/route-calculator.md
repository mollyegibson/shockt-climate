# Route Calculator

- **Status:** proposed
- **Depends on:** [Data Ingestion Pipelines](data-ingestion-pipelines.md), [Core Schema](../core-schema.md), [Case 1 Analysis](case-1-analysis.md)

A public web app where a user enters an origin, destination and shipment details, and the system returns freight routes ranked by carbon footprint across transport modes, with the option to view alternatives, compare modes side by side, and see which routes are affected by active disruptions.

---

## 1. Architecture

Three decoupled layers, each independently useful:

```
┌─────────────────────────────────────────────────────────────┐
│  Front end (React + TypeScript + Effect)                    │
│  - origin / destination autocomplete                        │
│  - ranked route list with per-leg emissions                 │
│  - map with route legs drawn                                │
│  - disruption badges (additive, from annotation layer)      │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────────┐
│  API (FastAPI, Python)                                      │
│  - /nodes/search — autocomplete against dim_nodes           │
│  - /routes — enumerate + score routes, return ranked        │
│  - /disruptions — current disruption state                  │
│  Imports engine.routing (boundary departure §2);            │
│  reads core via shockt_app                                  │
└──────────────────────┬──────────────────────────────────────┘
                       │ SQL (core schema only)
┌──────────────────────▼──────────────────────────────────────┐
│  Postgres (Neon → later Amazon RDS)                         │
│  - core schema (dim_nodes, distances_*, ref_emission_factors│
│    agg_feeder_hub_shares_monthly, dim_disruptions)          │
│  Populated offline by the existing data pipeline            │
└─────────────────────────────────────────────────────────────┘
```

### 1.1 Layer 1 — Route enumeration and scoring (general calculator)

Given `(origin, destination, options)`, enumerate all viable multimodal routes and score each by kg CO2e per tonne. This layer knows nothing about disruptions — it is a pure function of the graph, the user's options and a scenario.

A **route** is a sequence of legs through known node types:

| Mode | Legs |
|---|---|
| vessel (direct) | departure\_port →(ocean)→ arrival\_seaport →(truck/rail)→ destination\_state |
| vessel (feeder) | departure\_port →(ocean)→ departure\_port\* →(ocean)→ arrival\_seaport →(truck/rail)→ destination\_state |
| air | departure\_airport →(air)→ air\_gateway →(truck)→ destination\_state |
| truck | mexico\_plant →(truck)→ border\_crossing →(truck)→ destination\_state |
| rail | mexico\_plant →(truck)→ border\_crossing →(rail)→ destination\_state |

\*The hub in a feeder route is a `departure_port` node with `is_feeder_hub = true` in `dim_departure_ports` — not a separate node kind. The enumeration identifies hubs by matching `agg_feeder_hub_shares_monthly.hub_port_id` against `departure_port:{id}` nodes in `dim_nodes`. The leg-chain notation uses "hub" as a role, not a kind.

Each leg's emissions = `distance_km × kg_co2e_per_tkm`. A route's total = the sum of its legs.

This is not a general graph search — it is enumeration of the fixed multimodal topology, which keeps the computation simple and the results interpretable.

**Multi-hop routes.** Some origins require more than two legs. A feeder origin's vessel route has three legs (origin port → hub port → US seaport → destination state). The engine handles this by defining each mode as a **leg chain** — an ordered sequence of `(from_kind, to_kind, network)` tuples. Enumeration walks the chain: for each node matching the first `from_kind`, find nodes of the first `to_kind` with a distance, then from those find the next hop, and so on. The chain for each mode:

| Mode | Leg chain |
|---|---|
| vessel (direct) | departure\_port →ocean→ arrival\_seaport →truck/rail→ destination\_state |
| vessel (feeder) | departure\_port →ocean(feeder)→ departure\_port[hub] →ocean→ arrival\_seaport →truck/rail→ destination\_state |
| air | departure\_airport →air→ air\_gateway →truck→ destination\_state |
| truck | mexico\_plant →truck→ border\_crossing →truck→ destination\_state |
| rail | mexico\_plant →truck→ border\_crossing →rail→ destination\_state |

`departure_port[hub]` is a `departure_port` node with `is_feeder_hub = true`; "hub" is a role filter, not a distinct kind. The feeder leg's distance comes from `RouteDistances.feeder`, not from `RouteDistances.sea`.

Each hop is independently scored (distance × factor). If a hop has no distance edge, that partial route is dropped. The chain structure is extensible: adding a new hop (e.g. a rail terminal between seaport and state) means adding a leg to the chain and the corresponding distances to the seeds — no algorithmic change.

**What multi-hop scenarios the current data supports vs. doesn't:**

| Scenario | Supported | Why / what's needed |
|---|---|---|
| Feeder → hub → US seaport → state | Yes (after Phase 1b) | Feeder distances in `agg_feeder_hub_shares_monthly`, hub→seaport in `seed_sea_distances`. Requires feeder origin ports in `dim_nodes` (see "Feeder origin ports" above). |
| Direct ocean → seaport → state | Yes | `seed_sea_distances` + `seed_road_distances` |
| Ocean → seaport →(rail)→ state | Yes | `seed_rail_distances` has `arrival_seaport → destination_state` pairs. Used when `inland_mode: "rail"`. |
| Ocean → seaport → rail terminal → state (via intermediate) | Not yet | Would need rail-terminal nodes and seaport→terminal distances |
| Multi-port ocean (stop at intermediate ports) | Not yet | Would need intermediate-port stops in the sea distance data |
| Cross-border → US hub → final destination | Not yet | Would need hub-to-hub inland distances |

Future expansion adds nodes and distances; the leg-chain enumeration handles any depth without code changes.

**Feeder origin ports (prerequisite).** The four feeder origin countries (BGD, KHM, JOR, MMR per `config/sources.yaml`) have zero US-bound container voyages, so their ports do not appear in `dim_departure_ports` — which only includes US departure start ports and hub end ports. Their origin ports (Chittagong, Sihanoukville, etc.) are absent from `dim_nodes`. Without them, `enumerate_routes` step 1 returns zero departure ports for these countries, and no vessel routes — direct or feeder — can be enumerated.

The existing engine sidesteps this by assigning feeder tonnage to hub ports via `fct_node_weights_monthly.hub_shares`. The route calculator cannot use that trick because it needs to show the individual origin→hub leg on the map.

**Fix (Phase 1b):** Extend `dim_departure_ports` with a third role, `feeder_origin`, sourced from `agg_feeder_hub_shares_monthly.start_port_id`. Place each feeder origin port at the median start coordinates of its feeder voyages (available in `stg_climatetrace_feeder_voyages.start_lat`, `start_lon`). These ports enter `dim_nodes` as `departure_port` nodes with `is_feeder_origin = true` (and `is_us_departure = false`, `is_feeder_hub = false`). They don't need sea distances to US seaports — their ocean leg uses `RouteDistances.feeder`, not `RouteDistances.sea`. They only need to exist as nodes so the calculator can find them, enumerate feeder routes through them, and display them on the map.

**Cycle prevention.** Each partial route carries a `visited: frozenset[str]` of node\_ids it has passed through. Before adding a hop, the enumeration checks `if next_node in visited` and skips it. This is necessary because node kinds are not strictly distinct per hop — hub ports share `departure_port` kind with origin ports, so kind-based uniqueness alone doesn't prevent cycles. The visited set costs nothing at 2–4 legs per route.

**Mode availability is data-driven.** Not every mode is possible for every origin→destination pair:

| Mode | Available when |
|---|---|
| vessel | The origin country has departure ports in `dim_nodes`, at least one has a sea distance to a US seaport, and that seaport has a road (or rail) distance to the destination state |
| air | The origin country has departure airports, at least one has an air distance to a US air gateway, and that gateway has a road distance to the destination state |
| truck | Origin is Mexico, with plants mapped to border crossings that have road distances to the destination state |
| rail | Origin is Mexico, with crossings that have rail distances to the destination state |
| vessel (feeder) | The origin has feeder hub data in `agg_feeder_hub_shares_monthly` with `hub_has_us_voyages = true`, **and** the origin's feeder ports exist in `dim_nodes` (see "Feeder origin ports" above). Feeder routes are enumerated **alongside** direct routes when both exist — a port can be both `is_us_departure` and `is_feeder_hub` (e.g. an origin with direct service to the West Coast but transshipment via Singapore for the East Coast). The existing engine includes both; the calculator does the same. |

The engine enforces this by construction: no distance edge → no route. The API additionally exposes mode availability before the user submits (section 5.1, `/modes`), so the front end can disable impossible options and explain why.

**User options.** The calculator accepts optional parameters that narrow or enrich the results:

| Option | What it does | Effort |
|---|---|---|
| `cargo_t` | Multiply per-tonne results by weight → total kg CO2e | Trivial |
| `modes` | Restrict to specific transport modes (e.g. vessel only, air only) or return all (default) | Trivial |
| `inland_mode` | Prefer truck or rail for the seaport → destination inland leg | Trivial |
| `vehicle_type` | Override the emission factor for a mode. Requires `source` + `vehicle_type` (and optionally `size_class`, `haul`, `radiative_forcing`) to uniquely identify a factor row — vehicle type alone is ambiguous (e.g. UK has container\_ship with and without radiative forcing). | Low |
| `emission_scope` | Return well-to-wheel (default), tank-to-wheel, or well-to-tank breakdown | Low |
| `radiative_forcing` | Include or exclude radiative forcing on air freight factors | Low |
| `scenario` | Sea-distance scenario: open, red\_sea\_closed, panama\_closed, panama\_and\_red\_sea\_closed | Already built in |
| `compare_scenarios` | Return results under two scenarios side by side with the delta | Low |
| `hs6` | Filter Mexico plants to those making this product; annotate routes with relative traffic volume (high/medium/low); show historical port volumes as context. From `fct_node_weights_monthly` and `map_crossing_plant` | Medium |

All options have sensible defaults, so the simplest query is just `(origin, destination)`.

**Scenario selection.** The sea distance seeds carry a `scenario` column (`open`, `red_sea_closed`, `panama_closed`, `panama_and_red_sea_closed`). The calculator accepts a scenario parameter and uses the matching sea distances. Air, road and rail distances do not vary by scenario.

**Passage metadata.** Each sea edge carries a `passages` list (e.g. `babalmandab|suez|gibraltar`). A route's passages are the union of its legs' passages. This is a structural property, not an interpretation.

**Time estimates.** Duration data varies by network:

| Network | Duration source | Method |
|---|---|---|
| Road | `seed_road_distances.duration_h` | Observed (openrouteservice HGV profile) |
| Sea | Speed-based estimate: `km / 23.15` | Estimated at 12.5 knots (23.15 km/h), the average container-ship speed post-slow-steaming per IMO Fourth GHG Study (2018–2020 data). `agg_observed_sea_distances_monthly.mean_duration_h` exists but is per origin *country* × seaport — coarser than the per-port distances the calculator uses, so two routes from different ports in the same country would show different distances but identical durations. Using the speed-based formula keeps duration proportional to each route's actual distance. |
| Air | None in seeds | Estimated: `km / 850` (typical freighter cruise speed in km/h). Air distances are geodesic (great-circle), matching the existing engine. See §4.4 for the known underestimate. |
| Rail | None in seeds | Not available; shown as null |
| Feeder (sea) | `agg_feeder_hub_shares_monthly.mean_duration_h` | Observed aggregate per origin × hub |

The calculator carries `duration_h: float | None` on each leg. `total_duration_h` on a route is null if any leg's duration is null — summing known legs would produce misleadingly small totals (e.g. 0.2h for a multi-day trip). When the total is null, the front end shows per-leg durations individually (e.g. "Ocean: ~400h | Rail inland: unknown") rather than hiding all time information. Each leg's `duration_h` is always present in the response.

### 1.2 Layer 2 — Disruption annotation

A thin layer that reads the `dim_disruptions` table (which passages are currently affected) and annotates each route:

- `is_disrupted`: does this route transit a disrupted passage?
- `disrupted_passages`: which of its passages are disrupted?

The front end uses these annotations to badge routes. The annotation is additive — the app works without it, and disruption data can be added or updated independently.

### 1.3 Layer 3 — Presentation

The front end combines the calculator's output with the disruption annotations and renders:

- Routes ranked by emissions (lowest first), groupable and filterable by transport mode
- Per-leg breakdown (mode, distance, emissions, estimated time)
- Emissions shown as per-tonne and total (when cargo weight provided)
- Emissions scope toggle (well-to-wheel / tank-to-wheel / well-to-tank)
- Map with legs drawn between node coordinates, colored by mode
- Disruption badges on affected routes
- Mode comparison view: side-by-side cards for vessel, air, truck, rail
- Scenario comparison: toggle between open and disrupted, with emissions delta
- Commodity context panel (when HS code provided): historical port volumes for this product

---

## 2. Relationship to the existing engine

The existing engine (`shockt_engine.lanes`) computes weighted-average emissions for an entire origin-country trade flow — all its ports averaged by tonnage. The route calculator needs individual routes between specific nodes.

**Boundary departure.** The [DDD doc](../domain-driven-design.md) states the app reads `inputs` and `outputs`, never importing engine code. The route calculator violates this: `app/api/` takes a path dependency on `engine/` and calls `enumerate_routes()` directly. The alternative — precomputing all O×D×scenario×option combinations into `outputs` — is infeasible (the combinatorial space is too large and user options are open-ended). This is an intentional, documented departure. Before implementation, update the DDD doc's bounded-context table to add `engine` to the app's "Reads" column and note the exception: "The app imports the engine's routing module for on-demand route enumeration; precomputed outputs are not feasible for the combinatorial query space."

The new `shockt_engine.routing` module reuses the factor-selection logic and config, but not the weighted-average lane calculations:

| Existing | How routing uses it |
|---|---|
| `factors.py`: `select_factors`, `load_leg_factors`, `LegFactors` | Picking the right emission factor for each mode. The selection logic and `config/leg_factors.yaml` are reused directly. Both feeder and main-line ocean legs use `ocean` / `container_ship / average`, matching the existing engine. |
| `factors.py`: `Factor` dataclass | **Must be extended.** The existing `Factor` stores only `wtw_kg_co2e_per_tkm`. The routing module needs TTW and WTT separately (both exist in `ref_emission_factors` but aren't loaded). Add `ttw_kg_co2e_per_tkm` and `wtt_kg_co2e_per_tkm` fields to `Factor` and update the loader query. |
| `emissions.py`: `Leg`, `lane_intensity` | Not reused — `RouteLeg` is richer (TTW/WTT breakdown, passages, duration, node IDs). The per-leg emission formula (`km × factor`) is the same arithmetic but not worth an import. |
| `lanes.py` | Not reused — it computes weighted averages over all nodes in a lane; the calculator shows each specific route individually. |

---

## 3. Data model

### 3.1 Existing tables the calculator reads

| Table | What it provides |
|---|---|
| `core.dim_nodes` | Every origin and destination the user can pick, with coordinates |
| `core.dim_country` | Country names and ISO codes for the autocomplete |
| `core.distances_sea` | Departure port → arrival seaport distances, by scenario, with passages |
| `core.distances_air` | Departure airport → air gateway distances |
| `core.distances_road` | Road distances for truck legs |
| `core.distances_rail` | Rail distances |
| `core.ref_emission_factors` | kg CO2e per tonne-km by mode and variant (ttw, wtt, wtw) |
| `core.agg_feeder_hub_shares_monthly` | Feeder voyage distances and durations per origin × hub, monthly |
| `core.dim_departure_ports` | Port roles: `is_us_departure`, `is_feeder_hub` — identifies which departure ports are hubs |

The distance seeds currently land in `raw` as dbt seeds. The [DDD doc](../domain-driven-design.md) says the app never reads `raw`, and the `shockt_app` role has grants only on `core`. Before phase 2, add thin dbt models (e.g. `core.distances_sea` as `select * from {{ ref('seed_sea_distances') }}`) so the API reads `core` views, not `raw` tables. This also lets the models add computed columns later (e.g. speed-estimated duration for sea edges) without changing the API queries.

### 3.2 New table

Source: `config/disruptions.yaml`, a checked-in config file listing each passage and its current status:

```yaml
# config/disruptions.yaml
passages:
  - passage: babalmandab
    status: disrupted
    since_date: 2023-11-19
    description: Houthi attacks on commercial shipping in the Red Sea
    rerouted_by: [red_sea_closed, panama_and_red_sea_closed]
  - passage: suez
    status: open
    rerouted_by: [red_sea_closed, panama_and_red_sea_closed]
  - passage: panama
    status: open
    rerouted_by: [panama_closed, panama_and_red_sea_closed]
  - passage: gibraltar
    status: open
    rerouted_by: []   # badge-only; no scenario reroutes distances for this passage
  - passage: malacca
    status: open
    rerouted_by: []
  # ...
```

Each passage declares which scenarios reroute its distances via `rerouted_by`. Passages with an empty list are badge-only: the front end can flag them as disrupted, but the route's distance and emissions don't change. This mapping is implicit in how `searoute` handles the `restrictions` parameter; making it explicit in config lets the front end distinguish "disrupted — distance rerouted" from "disrupted — distance not rerouted" (see §4.4).

Generated by `shockt ref disruptions`, which reads the config and writes a dbt seed (`seed_disruptions.csv`). The seed loads into `raw.seed_disruptions` and a dbt model exposes it as `core.dim_disruptions` (including the `rerouted_by` column). This follows the project's data provenance rules: analytical decisions live in config, generators read them, and no data is written by hand.

The table is small (≤10 rows: suez, babalmandab, panama, gibraltar, south\_africa, hormuz, malacca, sunda, ormuz, chili). Status changes are pull requests to `config/disruptions.yaml`.

---

## 4. Engine: `shockt_engine.routing`

A new module in `engine/src/shockt_engine/routing.py`.

### 4.1 Data structures

```python
@dataclass(frozen=True)
class RouteLeg:
    name: str                    # e.g. "Chittagong → Port of Los Angeles"
    from_node: str               # node_id
    to_node: str                 # node_id
    network: Network             # sea, air, road, rail
    factor_mode: Mode            # ocean, air, truck, rail
    km: float
    duration_h: float | None     # from distance seeds, null when not available
    ttw_kg_co2e_per_tkm: float   # tank-to-wheel
    wtt_kg_co2e_per_tkm: float   # well-to-tank
    passages: tuple[str, ...]    # empty for non-sea legs

    @property
    def wtw_kg_co2e_per_tkm(self) -> float:
        return self.ttw_kg_co2e_per_tkm + self.wtt_kg_co2e_per_tkm

    @property
    def wtw_kg_co2e_per_t(self) -> float:
        return self.km * self.wtw_kg_co2e_per_tkm

@dataclass(frozen=True)
class Route:
    mode: LaneMode               # vessel, air, truck, rail
    legs: tuple[RouteLeg, ...]
    total_km: float
    total_duration_h: float | None     # null when any leg's duration is null
    total_ttw_kg_co2e_per_t: float
    total_wtt_kg_co2e_per_t: float
    total_wtw_kg_co2e_per_t: float
    passages: tuple[str, ...]    # union of leg passages
    scenario: str                # which sea-distance scenario was used
```

### 4.2 Core function

```python
@dataclass(frozen=True)
class EdgeDistance:
    km: float
    duration_h: float | None         # road: observed; sea: speed estimate; air: speed estimate; rail: null
    passages: tuple[str, ...] = ()   # non-empty only for sea edges

@dataclass(frozen=True)
class FeederEdge:
    """Origin port → hub port, from agg_feeder_hub_shares_monthly."""
    km: float                        # voyage-count-weighted mean of monthly median distances
    duration_h: float | None         # voyage-count-weighted mean of monthly mean durations
    hub_has_us_voyages: bool

@dataclass(frozen=True)
class RouteDistances:
    sea: Mapping[tuple[str, str], Mapping[str, EdgeDistance]]
    """(from_node, to_node) → scenario → EdgeDistance. Sea edges carry passages."""
    air: Mapping[tuple[str, str], EdgeDistance]
    road: Mapping[tuple[str, str], EdgeDistance]
    rail: Mapping[tuple[str, str], EdgeDistance]
    feeder: Mapping[tuple[str, str], FeederEdge]
    """(origin_port, hub_port) → FeederEdge. Separate from sea because feeder distances
    come from agg_feeder_hub_shares_monthly, not seed_sea_distances."""

@dataclass(frozen=True)
class FactorRow:
    """One row of ref_emission_factors with all three scopes."""
    source: str
    variant: str
    vehicle_type: str | None
    size_class: str | None
    haul: str | None
    radiative_forcing: bool | None
    ttw_kg_co2e_per_tkm: float
    wtt_kg_co2e_per_tkm: float
    wtw_kg_co2e_per_tkm: float

@dataclass(frozen=True)
class RouteOptions:
    scenario: str = "open"
    modes: frozenset[LaneMode] | None = None       # None = all modes
    inland_mode: InlandMode = "truck"               # truck or rail for the port → state leg
    vehicle_overrides: Mapping[Mode, LegFactor] = field(default_factory=dict)
    """Mode → full LegFactor override (source + vehicle_type + optional size_class/haul/radiative_forcing),
    not just a vehicle_type string, because vehicle_type alone can match multiple rows."""

def enumerate_routes(
    origin_country: str,              # ISO3
    destination_state: str,           # US state code
    nodes: Mapping[str, Node],        # node_id → Node(kind, lat, lon, iso3, ...)
    distances: RouteDistances,        # all networks including feeder, with durations and passages
    factors: Iterable[FactorRow],     # all factor rows; select_factor picks the right one per mode
    factor_choices: LegFactors,       # which factor each mode uses (or overridden by options)
    crossing_plants: Mapping[str, Mapping[str, str]] | None = None,
    # hs6 → {border_crossing_node → plant_node}; from map_crossing_plant. None for non-Mexico.
    options: RouteOptions = RouteOptions(),
    origin_node: str | None = None,   # specific node_id; when set, only routes from this node
    destination_node: str | None = None,  # specific node_id; when set, only routes to this node
    hs6: str | None = None,           # HS6 code; filters Mexico plants via crossing_plants
) -> list[Route]:
```

**Node-level origin/destination.** The API accepts either an ISO3 country code or a specific `node_id` as origin (and state code or `node_id` as destination). The engine always enumerates over the full country/state, then post-filters when a specific node is given. This avoids a separate code path: `origin_node` restricts routes to those starting from that node; `destination_node` restricts to those ending at that node. The API extracts the country from the node's `iso3` field and the state from `source_key` before calling the engine.

**Feeder data: temporal aggregation.** `agg_feeder_hub_shares_monthly` is per-month. The API aggregates across the most recent 12 months with data into a single distance and duration per (origin port, hub port) pair. The distance aggregation is a **voyage-count-weighted mean of monthly medians**: each month's `median_distance_km` weighted by its `n_voyages`. This is a mean of order statistics, not a mean of individual voyage distances. For a fixed port pair the monthly medians cluster tightly (same shipping lanes), so the distinction is academic — but the plan should be precise about what's being aggregated. (The source table's asymmetry — `median_distance_km` for distance, `mean_duration_h` for duration — reflects the original model's choice to be robust to outlier voyages on distance while preserving the mean for duration. The aggregation inherits this.) Hubs are included if they appear in any month within the window. The 12-month window smooths seasonal variation while staying current.

**Feeder data: hub coverage.** Only hubs with `hub_has_us_voyages = true` are used for feeder routes — a hub without US voyages has no sea distances to US seaports in `seed_sea_distances`. The `/modes` endpoint reports when an origin has feeder data but no covered hubs, so the user sees "transshipment hubs for this origin lack US voyage data" rather than silent empty results.

**Feeder data: missing passages — accuracy risk.** Feeder voyage distances come from `agg_feeder_hub_shares_monthly`, which has no `passages` column. Passages for feeder legs are therefore unknown and reported as empty. The disruption annotation layer cannot detect a disrupted passage on a feeder leg (e.g. Strait of Malacca for a Bangladesh → Singapore feeder). **This is a product-level accuracy risk, not just a data gap:** the absence of a disruption badge is a positive signal ("this route is fine") when it should be indeterminate. The front end must display a caveat on feeder routes: "Feeder leg disruption status unknown — transit passages are not yet mapped." To close the gap, a future `shockt ref feeder-passages` command would run `searoute` on each (origin port, hub port) pair and record the passages — the same approach as `seed_sea_distances`.

**Feeder data: scenario-invariant hub selection.** Hub choices come from observed voyage data in `agg_feeder_hub_shares_monthly`, which has no scenario dimension. Under a disrupted scenario (e.g. `red_sea_closed`), the hub set and feeder-leg distances stay fixed even though real transshipment patterns would shift (e.g. from Colombo to Durban). The calculator may produce routes that transit a hub whose onward main-line leg goes via the Cape — structurally plausible but with a hub that wouldn't be used in practice under that scenario. This is a known limitation; the fix would require modeling counterfactual feeder patterns per scenario, which is beyond MVP.

1. Find departure ports in the origin country: `kind=departure_port, iso3=origin_country`.
2. Find arrival seaports: `kind=arrival_seaport`.
3. **Direct vessel routes**: for each (departure_port, arrival_seaport) pair with a sea distance in the given scenario, and each arrival_seaport that has a road (or rail, per `options.inland_mode`) distance to the destination state, build a vessel route with two legs.
4. **Feeder vessel routes**: if the origin has feeder hub data (`agg_feeder_hub_shares_monthly`), find its hub ports where `hub_has_us_voyages = true`, then enumerate (departure_port → hub_port → arrival_seaport → destination_state) with three legs. The feeder leg uses the aggregated `FeederEdge.km` (the voyage-count-weighted mean across the 12-month window, as described above — not the raw `median_distance_km` column from a single month); the main leg uses the hub's sea distance to the seaport from `core.distances_sea`. Feeder routes are enumerated **alongside** direct routes — not as a fallback.
5. Similarly enumerate air routes through departure airports and air gateways.
6. For Mexico, enumerate truck/rail routes through plants and border crossings. When `hs6` is provided and `crossing_plants` has that code, only the plants mapped to each crossing for that HS6 are used — so a refrigerator query doesn't show routes from apparel factories. When `hs6` is omitted, all plants for all HS6 codes are included, but each route carries the plant name so the user can distinguish them. The existing `map_crossing_plant` maps (hs6, port_code) → plant_id; there are only ~15 mexico_plant → border_crossing pairs, so the unfiltered set is small.
7. Filter by `options.modes` if set; filter by `origin_node` / `destination_node` if set.
8. Score each route, sort by `total_wtw_kg_co2e_per_t`, return all.

The function is pure — no database access. The API layer fetches the data and passes it in.

### 4.3 Pruning and deduplication

With ~200 departure ports × ~50 arrival seaports × ~50 states, the full enumeration is manageable (~500K combinations in the worst case, but most pairs have no distance). In practice the origin country has 1–20 departure ports, so the enumeration is small.

**Port cluster deduplication.** Some countries have multiple port IDs that resolve to the same physical port area — e.g. China has 36 departure ports, including multiple terminals in Shanghai and Shenzhen. Without deduplication, these produce near-identical routes (same distance ± a few km, same emissions) that crowd the per-mode limit and push genuinely different routes (e.g. from Ningbo vs. Shanghai) out of the results. The API groups departure ports into clusters by proximity (haversine <5 km) and keeps one representative per cluster. The representative is the port with the most US-bound container voyages (from `dim_departure_ports`); for feeder-origin ports (which have zero US-bound voyages by definition), it's the port with the most feeder voyages. The deduplication applies at query time, not in the data model — the underlying tables retain all ports.

For future global expansion with more nodes, add a pre-filter: only consider arrival seaports on the coast region nearest the destination, or within a distance threshold.

### 4.4 Known accuracy limitations

The calculator matches the existing engine's factor and distance methodology at launch. Differences from ideal accuracy are documented below; improvements are future work, not Phase 1 scope.

**Distance methodology.**

| Limitation | Impact | Mitigation |
|---|---|---|
| **Sea distances are modelled (`searoute`), not observed.** The existing engine prefers AIS-observed distances per (origin country, arrival seaport) from `agg_observed_sea_distances_monthly`, falling back to `searoute`. The calculator uses only `searoute` because it needs per-departure-port granularity. Real voyages are 5–15% longer (~32 kg CO2e/t on a 20,000 km route). | Understates ocean emissions vs. the existing engine. Rankings within a route type are preserved (all use `searoute`). | Accepted. Future: per-port observed distances. |
| **Feeder routes mix observed and modelled distances.** Feeder leg: observed AIS (accurate). Main-line leg: `searoute` (short). Direct routes: 100% `searoute`. | Direct routes get a proportionally larger undercount, biasing rankings to favor direct over feeder (~24 kg CO2e/t on a 15,000 km leg at 10% underestimate). | Accepted: generating `searoute` for feeder pairs would discard more accurate observed data. Bias direction is known and stable. |
| **Air distances are geodesic** (great-circle, ~5–10% short of actual flight paths). Matches the existing engine. | Understates air emissions by ~7%. On a mode 30–40× more carbon-intensive than ocean, the absolute gap is large (~600 kg CO2e/t on Asia–US). | Accepted for engine consistency. Future: 1.07× ICAO routing correction. |
| **37 of 84 arrival seaports have sea distances but no road/rail distances** — routes through them are silently dropped. Similarly, 4 air gateways lack road distances. | Route families through those ports are absent. | Phase 1b adds a dbt test flagging seaports in `seed_sea_distances` that lack any entry in `seed_road_distances`. Seed additional distances if significant trade ports are affected. |
| **State-level destination is a single centroid.** Texas is ~1,200 km across; the centroid-based inland distance can be misleading for users near a port. | Could invert inland-leg rankings within large states. | Accepted for MVP. UI notes inland distances are to the state centre. Future: city-level destinations. |

**Emission factors.**

| Limitation | Impact | Mitigation |
|---|---|---|
| **Feeder and main-line ocean legs use the same factor** (`container_ship / average`), matching the existing engine. Feeder vessels (1,000–4,000 TEU) emit ~2–3× more per tkm than main-line ships (14,000+ TEU). | Understates feeder leg, overstates main-line leg. Net error biases feeder routes to look ~5–15% cheaper. | Accepted for engine consistency. Future: `feeder_ocean` Mode with UK DESNZ per-TEU-band factor. |
| **Transshipment handling emissions omitted** (~1 kg CO2e/t per hub stop). | ~0.2–0.3% of a 300–500 kg CO2e/t route. | Within factor uncertainty. Revisit for multi-transshipment routes. |
| **Rail distances omit drayage.** `seed_rail_distances` records track-only distance (BTS rail network). Real intermodal rail includes truck drayage (seaport→terminal, terminal→destination). The seed's `from_snap_km` / `to_snap_km` columns capture the gap but the plan doesn't use them. | Understates rail route emissions by the drayage distance × truck factor (10–50 km each end). Biases rail to look cheaper vs. all-truck. | Future: add drayage legs using snap distances and the truck factor. |

**Disruptions and scenarios.**

| Limitation | Impact | Mitigation |
|---|---|---|
| **Feeder passages unknown.** No `passages` column in `agg_feeder_hub_shares_monthly`. | Feeder legs get no disruption badges — an asymmetric "clean" signal vs. direct routes. | UI: grey "?" badge for "status unavailable." Future: `shockt ref feeder-passages`. |
| **Feeder hubs are scenario-invariant.** Hub selection and feeder distances don't change under disrupted scenarios. | Scenario comparison deltas for feeder routes reflect only main-line rerouting, not the hub switch that would occur in practice. Could be 30–50% of the actual delta. | Prominent UI caveat on feeder scenario comparisons. Fix requires counterfactual feeder modeling. |
| **Scenario rerouting covers only Red Sea and Panama** (4 variants). Badges can flag all ~10 passages. | Badge-only disruptions (Malacca, Hormuz, etc.) don't change emissions. | Each passage in `config/disruptions.yaml` declares `rerouted_by`. Front end distinguishes badge types. |
| **Scenarios only affect vessel distances.** Air, road and rail are scenario-invariant. | `compare_scenario` shows zero delta for non-vessel modes. | UI note: "Air, truck and rail distances do not vary by scenario." |

**Duration.**

| Limitation | Impact | Mitigation |
|---|---|---|
| **Sea duration uses 12.5 knots** (23.15 km/h, IMO Fourth GHG Study). Doesn't affect emissions. | Approximate — no port congestion, slow-steaming variation. | Label as "estimated." |
| **Rail duration is null** → `total_duration_h` null for vessel routes with `inland_mode: "rail"`. | Loses the ocean leg's valid estimate. | Front end shows per-leg durations individually when total is null. |

---

## 5. API: `app/api/`

FastAPI application, its own `pyproject.toml` with a path dependency on `engine/`.

### 5.1 Endpoints

#### `GET /nodes/search`

Autocomplete for origin/destination selection.

| Parameter | Type | Description |
|---|---|---|
| `q` | string | Search term (matches node name, country name, ISO code) |
| `kind` | string, optional | Filter by node kind (departure\_port, destination\_state, etc.) |
| `limit` | int, default 20 | Max results |

Returns: `[{node_id, kind, name, iso3, lat, lon}]`

#### `GET /countries`

List of origin countries that have departure nodes.

Returns: `[{iso3, name, modes: ["vessel", "air"]}]`

#### `GET /modes`

Which transport modes are available for a given origin→destination pair. Called when the user selects both ends, before they submit. The front end uses this to enable/disable mode checkboxes and show explanations.

| Parameter | Type | Description |
|---|---|---|
| `origin` | string | ISO3 country code or node\_id |
| `destination` | string | US state code or node\_id |

Returns:

```json
{
  "vessel": {
    "available": true,
    "departure_ports": 3,
    "arrival_seaports": 12,
    "inland_modes": ["truck", "rail"],
    "has_direct": true,
    "has_feeder": false,
    "feeder_hubs": 0
  },
  "air": {
    "available": true,
    "departure_airports": 2,
    "air_gateways": 8,
    "inland_modes": ["truck"]
  },
  "truck": {
    "available": false,
    "reason": "Overland routes available from Mexico only"
  },
  "rail": {
    "available": false,
    "reason": "Overland routes available from Mexico only"
  },
  "_note": "For Mexico, truck/rail show: available, border_crossings count, plants count"
}
```

When `has_feeder` is true, some vessel routes include a feeder leg (origin port → hub port) before the main ocean leg. The front end can note this: "Some cargo from this origin transships at a hub port." Both `has_direct` and `has_feeder` can be true simultaneously. The endpoint checks the same 12-month aggregation window used by `enumerate_routes` for feeder data — not all-time records. A feeder origin port may exist in `dim_nodes` (from all-time data) but have no voyages in the recent 12 months; in that case, `has_feeder` is false.

#### `GET /routes`

The core endpoint: ranked routes between an origin and destination.

| Parameter | Type | Description |
|---|---|---|
| `origin` | string | ISO3 country code, or a specific node\_id |
| `destination` | string | US state code, or a specific node\_id |
| `cargo_t` | float, optional | Cargo weight in tonnes; when set, response includes total emissions |
| `modes` | string, optional | Comma-separated modes to include: `vessel,air,truck,rail`. Default: all |
| `inland_mode` | string, default "truck" | Inland leg mode for vessel routes: `truck` or `rail` |
| `vehicle_overrides` | JSON string, optional | Per-mode factor overrides as a JSON object: `{"ocean": {"source": "uk_desnz", "vehicle_type": "bulk_carrier", "size_class": "average"}}`. Each value maps to a `LegFactor`. Only `source` and `vehicle_type` are required; `size_class`, `haul` and `radiative_forcing` disambiguate when needed. |
| `scenario` | string, default "open" | Sea-distance scenario |
| `compare_scenario` | string, optional | A second scenario; when set, returns both side by side with deltas |
| `hs6` | string, optional | HS-6 code. When set: (1) Mexico truck/rail routes filter to plants that make this product (via `map_crossing_plant`); (2) each route's arrival seaport is annotated with a relative traffic indicator derived from `fct_node_weights_monthly` (high / medium / low volume for this commodity), so the user can distinguish well-trafficked routes from exotic ones. When omitted, Mexico shows all plants (with plant names for disambiguation), and no traffic annotations appear. |
| `limit` | int, default 10 | Max routes per mode. Vessel routes are returned in two sub-lists: `direct_routes` and `feeder_routes`, each ranked by emissions and each capped at `limit`. Air, truck, and rail routes are in their own lists. This avoids a representation problem: in a single ranked list, the top N vessel routes by emissions could all be direct (or all feeder), burying the other type entirely. Separate sub-lists ensure both types are visible when both exist. The front end interleaves or tabs them. |

Returns:

```json
{
  "vessel_direct": [
    {
      "legs": [
        {
          "name": "Chittagong → Port of Los Angeles",
          "from_node": "departure_port:BGD_1234",
          "to_node": "arrival_seaport:2704",
          "from_name": "Chittagong",
          "to_name": "Los Angeles",
          "from_lat": 22.33, "from_lon": 91.80,
          "to_lat": 33.74, "to_lon": -118.27,
          "network": "sea",
          "mode": "ocean",
          "km": 18950.0,
          "duration_h": 456.0,
          "ttw_kg_co2e_per_tkm": 0.0131,
          "wtt_kg_co2e_per_tkm": 0.0027,
          "wtw_kg_co2e_per_tkm": 0.0158,
          "wtw_kg_co2e_per_t": 299.4,
          "passages": ["babalmandab", "suez", "gibraltar"]
        },
        {
          "name": "Los Angeles → Texas",
          "from_node": "arrival_seaport:2704",
          "to_node": "destination_state:TX",
          "network": "road",
          "mode": "truck",
          "km": 2200.0,
          "duration_h": 22.5,
          "ttw_kg_co2e_per_tkm": 0.0892,
          "wtt_kg_co2e_per_tkm": 0.0181,
          "wtw_kg_co2e_per_tkm": 0.1073,
          "wtw_kg_co2e_per_t": 236.1,
          "passages": []
        }
      ],
      "total_wtw_kg_co2e_per_t": 535.5,
      "total_ttw_kg_co2e_per_t": 445.3,
      "total_wtt_kg_co2e_per_t": 90.2,
      "total_wtw_kg_co2e": 5355.0,
      "total_km": 21150.0,
      "total_duration_h": 478.5,
      "passages": ["babalmandab", "suez", "gibraltar"],
      "scenario": "open",
      "traffic_volume": "high"
    }
  ],
  "vessel_feeder": [],
  "air": [],
  "truck": [],
  "rail": [],
  "comparison": null,
  "disruptions": {
    "passages": [
      {"passage": "babalmandab", "status": "disrupted", "since_date": "2023-11-19"}
    ],
    "affected_routes": {"vessel_direct": [0], "vessel_feeder": [], "air": []}
  },
  "factors": {
    "ocean": {"source": "uk_desnz", "vehicle_type": "container_ship", "size_class": "average", "ttw": 0.0131, "wtt": 0.0027, "wtw": 0.0158},
    "air": {"source": "uk_desnz", "vehicle_type": "freight_flight", "ttw": 0.4927, "wtt": 0.1094, "wtw": 0.6021},
    "truck": {"source": "epa_hub", "vehicle_type": "medium_heavy_duty_truck", "ttw": 0.0892, "wtt": 0.0181, "wtw": 0.1073},
    "rail": {"source": "uk_desnz", "vehicle_type": "rail", "ttw": 0.0245, "wtt": 0.0033, "wtw": 0.0278}
  },
  "commodity": null,
  "query": {
    "origin": "BGD",
    "destination": "TX",
    "cargo_t": 10.0,
    "scenario": "open",
    "modes": ["vessel", "air"],
    "inland_mode": "truck"
  }
}
```

When `compare_scenario` is set, the API enumerates **all** routes under both scenarios (no limit), matches them by **full node path** — the tuple of all leg node-pairs `(origin_port, hub_port?, arrival_seaport, destination_state)` — then applies the `limit` to the matched set, ranked by the primary scenario's emissions. Matching before limiting avoids false "unmatched" entries caused by a route ranking #11 in one scenario (outside `limit`) but matching a top-10 route in the other. This distinguishes feeder routes through different hubs (e.g. Chittagong → Singapore → LA vs. Chittagong → Colombo → LA) and handles direct routes where hub is absent. Each matched route carries a `delta_wtw_kg_co2e_per_t`. Routes that exist under one scenario but not the other (e.g. a Suez route under `open` that disappears under `red_sea_closed` because no distance exists for that scenario) appear as unmatched, with `delta` null and a note: "Route not available under [scenario]." The front end displays matched routes side by side and unmatched routes in a separate section. Scenario comparison is meaningful only for vessel routes — air, truck and rail distances are scenario-invariant. The front end notes this for non-vessel modes; `delta` is zero.

Route-level fields: When `hs6` is set, `traffic_volume` is `"high"` / `"medium"` / `"low"` based on the route's arrival seaport share of that commodity's total tonnage in `fct_node_weights_monthly` (terciles); when `hs6` is omitted, `traffic_volume` is null. This prevents an exotic low-traffic route from looking equivalent to a high-traffic one — the ranking is still by emissions, but the user sees which routes are realistic. Each sub-list (`vessel_direct`, `vessel_feeder`, `air`, `truck`, `rail`) is independently ranked by `total_wtw_kg_co2e_per_t`.

When `hs6` is set, `commodity` contains `{hs6, description, top_ports: [{node_id, name, weight_t}]}` from `fct_node_weights_monthly`. When `cargo_t` is set, `total_wtw_kg_co2e` (and ttw/wtt variants) appear on each route.

The `disruptions` key is the annotation layer: it reads `dim_disruptions` and tags which routes are affected. The front end uses it to badge routes, but the route ranking is disruption-agnostic.

#### `GET /disruptions`

Current disruption state, for the front end to display independently of a route query.

Returns: `[{passage, status, since_date, description}]`

### 5.2 Database access

The API connects to Neon (later RDS) as `shockt_app` (read-only on `core`). On startup it loads the distance views and emission factors into memory — they total ~35K rows and change only when the offline pipeline runs, so caching is safe. **After a pipeline run, restart the API to pick up new data.** A future improvement could add a `/reload` admin endpoint or watch a version marker in the database. Node search and commodity-context queries hit the database per request.

Connection pooling: the API connects via Neon's pooled endpoint, which handles connection multiplexing. The FastAPI app uses `psycopg` with a small local pool (5–10 connections). When migrating to RDS, swap the connection string; no code changes.

### 5.3 Project layout

```
app/
  api/
    pyproject.toml          # depends on shockt-engine (path dep), fastapi, psycopg, uvicorn
                            # The path dependency makes engine's config/leg_factors.yaml
                            # accessible at runtime via importlib.resources or __file__.
    src/
      shockt_api/
        __init__.py
        main.py             # FastAPI app, CORS, lifespan
        routes.py           # /routes endpoint
        nodes.py            # /nodes/search, /countries endpoints
        disruptions.py      # /disruptions endpoint
        db.py               # connection pool, queries
        schemas.py          # Pydantic response models
    tests/
      conftest.py
      test_routes.py
      test_nodes.py
```

---

## 6. Front end: `app/web/`

React + TypeScript + Effect, following [Effect Style](../effect-style.md) and [Front-end Code Style](../front-end-code-style.md). Validates API responses with Effect `Schema`.

### 6.1 Pages

**Single page** with four sections:

1. **Search bar**: origin and destination autocomplete, optional cargo weight (tonnes), optional HS-6 code, transport mode checkboxes (vessel, air, truck, rail — all checked by default), and a "Calculate" button.
2. **Mode comparison strip**: after results load, a horizontal strip of cards — one per mode — showing the best route's emissions, time and distance. Clicking a card filters the results list to that mode.
3. **Results panel**: routes ranked by emissions, expandable to show per-leg breakdown (distance, time, emissions in the selected scope). The lowest-emissions route is highlighted. Disruption badges appear on affected routes.
4. **Map**: Leaflet (free, no API key) with route legs drawn as arcs between node coordinates. Clicking a route in the results panel highlights it on the map.

### 6.2 State

- `origin: Node | null` — selected origin
- `destination: Node | null` — selected destination
- `cargoT: number | null` — optional cargo weight
- `hs6: string | null` — optional commodity code
- `modes: Set<LaneMode>` — selected transport modes (default: all)
- `inlandMode: "truck" | "rail"` — inland leg preference
- `scenario: string` — selected sea-distance scenario (default "open")
- `compareScenario: string | null` — second scenario for comparison
- `emissionScope: "wtw" | "ttw" | "wtt"` — which scope to display (default "wtw")
- `routes: Route[]` — results from the API
- `comparison: Route[] | null` — results under the second scenario
- `disruptions: Disruption[]` — from the API
- `commodity: CommodityContext | null` — historical port volumes for the HS code
- `selectedRoute: number | null` — index of the route highlighted on the map
- `loading: boolean`

State is in hooks per the front-end style guide, not in a global store.

### 6.3 Map

Leaflet with OpenStreetMap tiles (free, no key). Route legs are drawn as geodesic arcs using `leaflet.geodesic`. Each leg is colored by transport mode:

| Mode | Color |
|---|---|
| ocean (sea) | blue |
| air | light grey |
| truck (road) | orange |
| rail | green |

Node markers show the port/airport/state name on hover. When comparing scenarios, the second scenario's route is drawn as a dashed line in the same color.

### 6.4 Scenario comparison

A dropdown to select the primary scenario and a "Compare with…" dropdown for the second. When both are set, the results panel shows paired routes with an emissions delta (↑ or ↓ percentage) and the map overlays both.

### 6.5 Options panel

A collapsible "Advanced options" section below the search bar:

- **Inland mode**: truck (default) or rail for the seaport → state leg
- **Vehicle type overrides**: per-mode dropdowns (e.g. container\_ship / bulk\_carrier for ocean; hgv / hgv\_refrigerated for truck)
- **Emissions scope**: well-to-wheel (default), tank-to-wheel, well-to-tank
- **Radiative forcing**: include (default) or exclude for air freight

### 6.6 Project layout

```
app/
  web/
    package.json
    tsconfig.json
    vite.config.ts
    src/
      main.tsx
      App.tsx
      api/
        client.ts           # fetch wrapper, base URL from env
        schemas.ts          # Effect Schema definitions for API responses
      components/
        SearchBar.tsx
        ModeComparison.tsx   # horizontal strip of per-mode summary cards
        RouteList.tsx
        RouteDetail.tsx      # per-leg breakdown (distance, time, emissions)
        RouteMap.tsx
        DisruptionBadge.tsx
        ScenarioSelector.tsx
        EmissionsScopeToggle.tsx
        VehicleTypeSelector.tsx
        CommodityContext.tsx  # historical port volumes for an HS code
        OptionsPanel.tsx     # collapsible advanced options
      hooks/
        useNodes.ts          # autocomplete search
        useRoutes.ts         # route fetching, mode filtering, state
        useDisruptions.ts    # disruption state
      types/
        index.ts             # shared types (Route, Leg, Node, Disruption, etc.)
```

### 6.7 Dependencies

| Package | Purpose |
|---|---|
| react, react-dom | UI |
| effect, `@effect/schema` | Validation, typed errors |
| leaflet, react-leaflet, leaflet.geodesic | Map |
| vite | Build |

No UI component library to start — plain HTML + CSS. Add one later if the design needs it.

---

## 7. Infrastructure

### 7.1 Database: Neon first, RDS later

Ship with the existing Neon database. The API connects as `shockt_app` (read-only on `core`) using Neon's pooled connection string. No infrastructure provisioning needed to launch.

Neon's built-in connection pooling (`-pooler` endpoint) handles DO App Platform's connection pattern without RDS Proxy or PgBouncer.

**Cost (launch)**: $0 incremental (Neon is already running).

#### Future: migrate to Amazon RDS

When Neon's cost, performance or availability becomes a constraint, migrate to RDS. The only change is the `DATABASE_URL` environment variable — the API uses standard `psycopg` and doesn't depend on Neon-specific features.

| Setting | Value |
|---|---|
| Engine | PostgreSQL 16 |
| Instance | db.t4g.micro (1 vCPU, 1 GB RAM) |
| Storage | 30 GB gp3 |
| Deployment | Single-AZ |
| Public access | Yes (security group restricts to team IPs + DO App Platform) |

**Migration steps**: provision the instance, run `alembic upgrade head`, rebuild with `dbt seed && dbt run`, swap `DATABASE_URL`, allow DO's outbound IPs in the RDS security group.

**Cost (RDS)**: ~$16/mo (instance $12 + 30 GB storage $3.45).

### 7.2 DigitalOcean App Platform

One app with two components:

| Component | Type | Source | Build |
|---|---|---|---|
| `web` | Static Site | `app/web/` | `npm run build`, output `dist/` |
| `api` | Web Service | `app/api/` | `pip install .`, run `uvicorn shockt_api.main:app` |

Environment variables on the `api` component:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon pooled connection string for `shockt_app` (later: RDS) |
| `ALLOWED_ORIGINS` | The static site's URL (for CORS) |

The static site's `VITE_API_URL` env var points to the api component's URL.

**Cost**: $12/mo (Professional tier, 1 container). The API loads ~35K rows into memory at startup and enumerates thousands of routes per request with Python's per-object overhead. The Basic tier's 256 MB RAM is likely too tight under concurrent load. The Professional tier provides 512 MB and autoscaling support. Start with 1 container; scale horizontally if needed.

### 7.3 Total cost at launch

| Layer | Cost/mo |
|---|---|
| DigitalOcean App Platform (Professional, 1 container) | $12 |
| Neon (existing) | $0 incremental |
| **Total** | **$12/mo** |

After RDS migration: ~$28/mo.

---

## 8. Phases

No infrastructure provisioning phase — the app connects to the existing Neon database at launch.

### Phase 1: Engine routing module

1. Extend `shockt_engine.factors.Factor` to load `ttw_kg_co2e_per_tkm` and `wtt_kg_co2e_per_tkm` alongside the existing `wtw_kg_co2e_per_tkm`. Update the `select_factor` loader query accordingly. Verify existing lane tests still pass.
2. Add `shockt_engine/routing.py` with `Node`, `EdgeDistance`, `FeederEdge`, `RouteDistances`, `FactorRow`, `RouteLeg`, `Route`, `RouteOptions` data structures.
3. Implement `enumerate_routes()`: iterate over node combinations per mode, look up distances and durations, score each leg with `select_factor` (both feeder and main-line ocean legs use `ocean` / `container_ship / average`, matching `lanes.py`), collect passages, apply cycle prevention via visited set, sort by total wtw emissions. Accept optional `hs6` to filter Mexico plant routes via `map_crossing_plant` (see §4.2).
4. Sea durations use 12.5 knots (23.15 km/h) per IMO Fourth GHG Study. Air distances are geodesic, matching the existing engine.
5. Support `RouteOptions`: mode filter, inland mode preference, vehicle type overrides (as `LegFactor`, not bare strings).
6. Port deduplication: group departure ports within the same port cluster (by proximity, e.g. <5 km haversine) and keep one representative per cluster (highest US-bound `container_voyages`; for feeder-origin ports, highest `feeder_voyages`). See §4.3.
7. Tests against known node pairs from the existing seeds (e.g. a Bangladesh departure port → a US east coast seaport → a US state, with a hand-verified emission total).
8. `uv run ruff check . && uv run ruff format --check . && uv run pytest`.

### Phase 1b: Data prerequisites

1. **Feeder origin ports.** Extend `dim_departure_ports` with a `feeder_origin` role: add a CTE sourcing `start_port_id` from `stg_climatetrace_feeder_voyages`, placed at the median `(start_lat, start_lon)`. Add `is_feeder_origin` boolean column. These ports enter `dim_nodes` as `departure_port` nodes. Verify with a test that feeder origin countries (BGD, KHM, JOR, MMR) have at least one departure\_port node.
2. **Core distance views.** Add thin dbt models: `core.distances_sea`, `core.distances_air`, `core.distances_road`, `core.distances_rail` — each a `select * from {{ ref('seed_*_distances') }}`. `core.distances_sea` adds a speed-estimated `duration_h` column (`km / 23.15`, i.e. 12.5 knots per IMO Fourth GHG Study).
3. Grant `shockt_app` read access on the new views (Alembic migration).
4. Update the [DDD doc](../domain-driven-design.md) bounded-context table: add `engine` to the app's "Reads" column with a note that the app imports the engine's routing module for on-demand enumeration.
5. Add a dbt test (or `test_reference_seeds.py` assertion) that every hub port with `hub_has_us_voyages = true` in `agg_feeder_hub_shares_monthly` has at least one entry in `seed_sea_distances`. This enforces the invariant that feeder route enumeration depends on: step 4 in §4.2 assumes hub ports have sea distances to US seaports.
6. Add a dbt test flagging arrival seaports in `seed_sea_distances` that have no entry in `seed_road_distances` or `seed_rail_distances`. These seaports produce routes that dead-end at the port with no inland leg. The test is a warning (not a hard failure) — it quantifies the gap so we can prioritize additional distance seeds.
7. `dbt run && dbt test` to verify.

### Phase 2: API backend

1. Create `app/api/` with `pyproject.toml` (FastAPI, psycopg, uvicorn; path dependency on engine).
2. `db.py`: connection pool (Neon pooled endpoint), queries for nodes, distances (from `core.distances_*` views), factors, disruptions.
3. `nodes.py`: `/nodes/search` and `/countries` endpoints.
4. `routes.py`: `/routes` endpoint — loads data, calls `enumerate_routes`, annotates with disruptions, attaches commodity context when `hs6` provided, computes total emissions when `cargo_t` provided, handles `compare_scenario`. When `origin` is a `node_id`, extract its country and pass both `origin_country` and `origin_node` to the engine.
5. `disruptions.py`: `/disruptions` endpoint.
6. `schemas.py`: Pydantic response models matching the JSON in section 5.1.
7. Tests with httpx `TestClient` and a test database (same testcontainer pattern as `data-pipelines/`).
8. Run locally: `uv run uvicorn shockt_api.main:app --reload`.

### Phase 3: Front end — core

1. Create `app/web/` with Vite + React + TypeScript.
2. `api/schemas.ts`: Effect Schema definitions for route, leg, node, disruption.
3. `api/client.ts`: fetch wrapper with typed error handling per the front-end style guide.
4. `hooks/useNodes.ts`: debounced autocomplete search.
5. `components/SearchBar.tsx`: origin + destination inputs, cargo weight field, mode checkboxes.
6. `hooks/useRoutes.ts`: fetch routes on submit, hold results state.
7. `components/RouteList.tsx` + `RouteDetail.tsx`: ranked results with per-leg breakdown (distance, time, emissions by scope).
8. `components/RouteMap.tsx`: Leaflet map with geodesic arcs for route legs, colored by mode.
9. Verify in browser: search for Bangladesh → Texas, confirm routes render with times and emissions, map shows legs.

### Phase 4: Front end — options and comparison

1. `components/ModeComparison.tsx`: side-by-side cards showing the best route per mode.
2. `components/ScenarioSelector.tsx`: dropdown to switch scenarios; "compare" toggle fetches both and shows deltas.
3. `components/DisruptionBadge.tsx`: visual indicator on disrupted routes.
4. `components/EmissionsScopeToggle.tsx`: switch between wtw / ttw / wtt display.
5. `components/VehicleTypeSelector.tsx`: override vehicle subtype per mode (e.g. refrigerated HGV).
6. `components/CommodityContext.tsx`: when HS code entered, show top ports for this product.
7. Verify all options in browser.

### Phase 5: Deploy

1. Create DO App Platform app with `web` (static) and `api` (web service) components.
2. Set environment variables (`DATABASE_URL` = Neon pooled string, `ALLOWED_ORIGINS`, `VITE_API_URL`).
3. Deploy, verify the public URL works end to end.

### Phase 6: Disruption data (can ship independently)

1. Create `config/disruptions.yaml` with passage statuses (Bab al-Mandab disrupted since 2023-11-19, others open).
2. Implement `shockt ref disruptions` command to generate `seed_disruptions.csv` from the config.
3. Add dbt seed + model for `core.dim_disruptions`.
4. Add `tests/test_reference_seeds.py` entry for the disruptions seed.
5. API already reads it (phase 2); front end already renders it (phase 4). This phase just adds the data.

### Phase 7 (future): RDS migration

1. Provision RDS, rebuild data, swap `DATABASE_URL`, verify. See section 7.1.

---

## 9. Future: global expansion

The architecture is ready for global routes. Expanding requires:

1. **Global port dimension**: replace or extend `dim_nodes` with ports worldwide (e.g. from the World Port Index or UN/LOCODE).
2. **Global sea distances**: run `searoute` for new port pairs and append to `seed_sea_distances`.
3. **Global road/rail distances**: OSRM or openrouteservice for continental legs.
4. **Destination nodes beyond US states**: add cities, regions or countries as destination nodes.
5. **The engine and API need no structural changes** — they already work with any nodes in `dim_nodes` and any distances in the seeds. The topology of legs (section 1.1) extends to new node kinds.

---

## 10. Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Database (launch) | Neon (existing) | Zero provisioning, built-in pooling, $0 incremental; migrate to RDS when needed |
| Map library | Leaflet + OpenStreetMap | Free, no API key, sufficient for route visualization |
| Front-end build | Vite | Fast, simple, no SSR needed for a single-page calculator |
| API framework | FastAPI | Existing Python ecosystem, path dependency on engine, good enough for the traffic |
| Connection pooling | Neon pooled endpoint (later: psycopg pool to RDS) | Low concurrency; avoids RDS Proxy ($21/mo) |
| Route enumeration vs graph search | Enumeration over fixed topology | The multimodal leg structure is known and small; Dijkstra adds complexity without benefit |
| No UI library | Plain HTML + CSS | Keeps bundle small and avoids framework lock-in for a single-page app |
| App imports engine | Path dependency from `app/api/` to `engine/` | Departs from the DDD doc's bounded-context rule. Precomputing all routes into `outputs` is infeasible; the engine is pure Python with no DB dependency and stays testable. DDD doc updated to note the exception. |
| Distance views in core | Thin `core.distances_*` models over `raw` seeds | The app reads only `core`; `shockt_app` has no `raw` grants. Views also allow adding computed columns (e.g. speed-estimated duration) without changing API queries. |

---

## 11. Calculator options: effort summary

All options the calculator supports, ranked by implementation effort. Everything except "rank by cost" is buildable from existing data.

| Option | Effort | Phase | Notes |
|---|---|---|---|
| Cargo weight (total emissions) | Trivial | 2–3 | One field, one multiplication |
| Transport mode filter | Trivial | 1–3 | Already enumerated by mode |
| Inland mode preference (truck / rail) | Trivial | 1–2 | Already a parameter in the engine |
| Time estimates per route | Low | 1–3 | Road seeds have duration; sea and feeder have observed aggregates; air estimated from speed; rail null. See section 1.1 duration table. |
| Emissions scope toggle (wtw / ttw / wtt) | Low | 1–3 | All three scopes in `ref_emission_factors`; expose all |
| Radiative forcing toggle (air) | Low | 1–3 | Factor attribute; one toggle |
| Vehicle subtype selection | Low | 1–3 | Factors exist per subtype; dropdown selects different factor |
| Mode comparison (side-by-side cards) | Low | 4 | Group results by mode, show best per mode |
| Scenario comparison (side-by-side with delta) | Low | 2–4 | Run calculator twice, diff results |
| HS code / commodity context | Medium | 2–3 | Query `fct_node_weights_monthly` for historical port volumes |
| Rank by multiple criteria (emissions + time) | Medium | 4 | Both available; add a sort selector |
| Rank by cost | Not yet possible | — | Requires freight-rate data not in the database |
