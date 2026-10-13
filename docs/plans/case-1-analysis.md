# Case 1 Analysis: 2025 Trade-Policy Shocks and Data Center Hardware Supply

**Status:** Draft · **Workstream:** Analysis, engine · **Date:** 2026-10-13

This plan covers the first Case 1 notebook: a worked template the analysts copy and extend, which also produces the first findings to share. It reads `core`, computes with functions that will move into the engine, and drafts the case's input files. It doesn't cover the engine's `outputs` tables, CI or the app.

## 1. Goal

Show where US supply of AI servers moved between origins and modes around the 2025 trade-policy shocks, and what that did to the transport emissions of delivering a tonne of servers to the US, as a range. Servers were excluded from the reciprocal tariffs within days (Section 2), so the case compares them with the data center electrical gear that stayed exposed (transformers and switchgear, already loaded as Case 2's codes): same industry, same buyers, same AI demand, different exposure. Keep accounting (what changed) separate from attribution (why), as the proposal requires.

The notebook answers six questions:

1. **Origin shares:** how much of US server tonnage came from Taiwan, Mexico, Thailand, Vietnam and the other origins, by month and by window?
2. **Mode shares:** within each origin, how much came by air, vessel, truck and rail?
3. **Delivery emissions per tonne:** for each origin and mode, how much CO₂e does delivering a tonne to its US destination emit?
4. **The supply mix:** what was the emissions per tonne of the whole US server supply in each window, and what diversion rates moved it?
5. **The missing leg:** how far, and by which mode, would components have to travel into Mexico to cancel the Mexico route's advantage?
6. **The comparison:** did the exposed gear's origin shares move differently from the servers' across the same windows?

## 2. What the policy record says

The official record (`inputs/cases/tariffs_2025/evidence.yaml`, each item checked against its source) changes what "the tariff shock" means for servers:

| Date | Event | Source |
|---|---|---|
| 2025-02-01 | 25% duty on products of Mexico ordered, originally from February 4 | EO 14194, 90 FR 9117 |
| 2025-02-03 | Mexico duty paused until March 4 | EO 14198, 90 FR 9185 |
| 2025-03-04 | Mexico duty in effect | CBP notice, 90 FR 11429 |
| 2025-03-07 | USMCA-qualifying goods of Mexico exempted | EO 14232, 90 FR 11787 |
| 2025-04-01 | Section 232 investigation of semiconductors and derivative products initiated | BIS notice, 90 FR 15950 |
| 2025-04-02 | Reciprocal tariffs announced: 10% from April 5, country rates from April 9 | EO 14257, 90 FR 15041 |
| 2025-04-11 | Heading 8471, including servers, excluded from the reciprocal tariffs, back to April 5 | CBP CSMS #64724565 |
| 2025-08-07 | New reciprocal rates, keeping EO 14257's exceptions | EO 14326, 90 FR 37963 |
| 2025-08-18 | Transformers 8504.23, 8504.33 and 8504.34 added to the section 232 steel and aluminum derivatives (duty on their metal content) | BIS notice, 90 FR 40326 |

**Servers were excluded from the reciprocal tariffs within nine days of the announcement**, and the exclusion carried through the August rate change. Mexico's duty exempts USMCA-qualifying goods, and whether servers assembled in Mexico qualify isn't in the record. What servers faced was a short exposure, uncertainty (the Section 232 investigation names derivative products), and possibly the Mexico duty on non-qualifying goods.

**The electrical gear stayed exposed.** No subheading of 8504 or 8537 is on CBP's exclusion list or in EO 14257's Annex II, so the gear paid the reciprocal tariffs from April 2025, and three of the six codes also paid the steel and aluminum duty on their metal content from August 18, 2025.

The analysis therefore asks whether supply shifted around these dates, not how it reacted to a tariff it paid, and uses the gear as the comparison: if exposed gear and exempt servers moved alike, demand rather than the tariffs is the likelier driver; if the gear shifted and servers didn't, that points to the tariffs. A finding that shifts don't line up with the exposure is a result, and the causal labels say so. A first look at the data: Taiwan's air tonnage roughly tripled from April to May 2025 and stayed high, Thailand's grew tenfold from late 2025, and Mexico's overland tonnage grew steadily. A step that holds, after the exclusion, reads more like growth or a lasting change than front-loading.

## 3. Scope

- **Products:** servers, HS 847150, the Case 1 code in `config/hs_codes.yaml`; and, as the exposed comparison group, the electrical gear: liquid-dielectric transformers (850421, 850422, 850423), dry transformers above 16 kVA (850433, 850434) and switchgear above 1,000 V (853720), loaded for Case 2. The gear's results are shown as a group and by its two exposure levels (reciprocal only; reciprocal plus section 232 from August 2025).
- **Origins:** Taiwan, Mexico, Thailand and Vietnam each on their own; the rest of the configured origins as "other origins". Thailand is in because its growth from late 2025 may be a diversion the proposal's Taiwan–Mexico framing would miss.
- **Months:** January 2024 to the latest loaded month.
- **Legs:** the delivery into the US only:
  - air: departure airport → US gateway → destination state by truck;
  - vessel: departure port → US seaport → destination state by truck;
  - Mexico overland: assembly plant → crossing by truck, then crossing → destination state by truck or rail.
- **Out of scope:** components into Mexico (no data loaded; Section 7.5 bounds them instead), production emissions, and freight cost (a [future plan](./cost-calculator.md)).

## 4. Windows

Illustrative windows from the proposal, set in `inputs/cases/tariffs_2025/shock_windows.yaml` with the evidence each rests on. Windows are whole months, because Census data is monthly.

| Window | Months | Rests on |
|---|---|---|
| Baseline | 2024-01 to 2025-01 | The 12 months before the first tariff order (EO 14194, February 1, 2025) |
| Anticipation | 2025-02 to 2025-04 | From the Mexico order to the reciprocal tariffs and the server exclusion |
| Response | 2025-05 to 2025-12 | After the exclusion, to the end of 2025 |

The data runs past December 2025, so the notebook also shows 2026 as context, without a window. Detecting breaks in the series to set windows is for a later version.

## 5. Data

Read from `core` (and the distance seeds in `raw`) with the read-only analyst login, `ANALYST_DATABASE_URL`:

| Table | Used for |
|---|---|
| `fct_imports_monthly` | Air and vessel tonnage by origin and month |
| `fct_mexico_overland_monthly` | Mexican truck and rail tonnage, with its low–high range |
| `dim_country` | Origin names and regions |
| `dim_nodes`, `fct_node_weights_monthly` | Where each lane's freight leaves, arrives and ends up, and how much |
| `agg_observed_sea_distances_monthly`, `seed_sea_distances` | Sea distance: observed where voyages exist, `searoute` open route otherwise |
| `seed_air_distances`, `seed_road_distances`, `seed_rail_distances` | Air, truck and rail leg distances |
| `ref_emission_factors` | Factors per tonne-km, chosen by `engine/config/leg_factors.yaml` |

## 6. Layout

| Folder | Holds |
|---|---|
| `engine/` | The `shockt_engine` Python package (uv project): pure functions, plain values in and out, no database. Tested with pytest. The notebook imports it; later the engine runs the same functions to write `outputs`. |
| `analysis/` | A uv project with Jupyter. `analysis/shockt_analysis/core.py` is the adapter that reads `core` into data frames; `analysis/case1/case1_tariffs_2025.ipynb` is the notebook. |
| `inputs/cases/tariffs_2025/` | `shock_windows.yaml`, `causal_labels.yaml`, `evidence.yaml` (FACT and INFERENCE records, written by people) and `evidence_derived.yaml` (DERIVED records, written by the notebook). |

The notebook connects through the adapter; the engine never sees the database, as the [architecture](../domain-driven-design.md) requires. Polars for data frames, matplotlib for charts.

## 7. Method

### 7.1 Monthly supply

One table, month × origin × mode, in tonnes, with a low and high:

- **Air and vessel:** Census shipping weight; low = high = reported.
- **Truck and rail from Mexico:** `fct_mexico_overland_monthly`, with its range.
- **Other origins:** summed. Their own overland tonnage (goods entering over a land border) is under 1% of overland and left out.

### 7.2 Shares and diversion rates

Origin shares and, within each origin, mode shares of tonnage, by month and by window. A diversion rate between two categories, from the proposal: r = (s_to,response − s_to,baseline) / s_from,baseline, with s a category's share of lane tonnage. Computed per month within the response window against the baseline window; the window's rate is the tonnage-weighted mean, and its range is the monthly low and high, as the proposal specifies. Country-lanes too thin for their own rate use their region's (plan question 16 of the ingestion plan); for this case Taiwan, Mexico, Thailand and Vietnam are all steady.

### 7.3 Delivery emissions per tonne, per lane

A lane is an origin × mode. Its emissions per tonne are the sum over its legs of distance × factor:

- **Distance of a leg:** the average over the node pairs the lane uses, weighted by the node weights over the window. With no source linking a departure node to an arrival node to a destination, the weights are combined as independent: weight(departure) × weight(arrival) × weight(destination), each normalised within the lane. A stated assumption.
- **Sea distance:** the observed median for the origin and arrival port, else the `searoute` open-route distance.
- **Factor of a leg:** the one `ref_emission_factors` row that `engine/config/leg_factors.yaml` names for the leg's mode, well-to-wheel (`select_factors`, which fails if a mode matches none or several).
- **Range:** a lane's per-tonne intensity is a point value; the ranges come from the mix (7.4) and from Mexico's tonnage estimate.

### 7.4 The supply mix

The emissions per tonne of US server supply in a window is the sum over lanes of the lane's share of tonnage × its intensity. Reported per window with the monthly low and high, and the change from baseline to each later window. This is the case's headline: what the observed shifts did to the carbon cost of a delivered tonne, independent of how much the total grew.

### 7.5 The missing leg into Mexico

The Mexico route's advantage per tonne, A = intensity(Taiwan air) − intensity(Mexico overland), is cancelled by a component leg of A ÷ factor km for each mode, per tonne of components. Reported for sea and air, with the assumption stated: about one tonne of components per tonne of servers. The result says which component modes would cancel the advantage, without data on imports into Mexico.

### 7.6 The comparison

The same supply table, shares and diversion rates (7.1, 7.2) for the gear, side by side with the servers, by window. The comparison is of changes, not levels: the change in each origin's share from baseline to response for the servers against the same for the gear, and within the gear, the codes that took the August duty against those that didn't. The gear moves mostly by sea, so it shows origin shifts more than mode shifts; its delivery emissions per tonne use the same lane method (7.3). Two groups and a few windows can show whether shifts line up with exposure; they can't prove the tariffs caused them, and the causal labels say how strong the alignment is.

### 7.7 Engine functions

Each is a pure function with tests pinned to hand-computed values:

| Function | Computes |
|---|---|
| `shares(tonnes, by)` | Shares within groups |
| `diversion_rate(s_from_baseline, s_to_baseline, s_to_response)` | The proposal's r |
| `window_summary(monthly, windows)` | Weighted mean, low and high per window |
| `weighted_leg_distance(pairs, weights)` | A leg's distance, averaged over node pairs |
| `lane_intensity(legs)` | Sum of distance × factor over a lane's legs, kg CO₂e per tonne |
| `mix_intensity(lane_shares, lane_intensities)` | The supply mix's emissions per tonne |
| `break_even_km(advantage, factor)` | The component distance that cancels an advantage |
| `pair_weighted_distance(distances, pair_weights)` | A leg's distance over node pairs with known weights (plant → crossing) |
| `sea_leg_distance(observed, modelled, departures, arrivals)` | The sea leg: observed distance per arrival port, else `searoute` |
| `lane_legs(mode, inputs)` | A lane's legs, their distances and factors |
| `select_factors(factors, leg_factors)` | Each mode's emission factor |
| `share_change(baseline_shares, window_shares)` | Each category's change in share between windows, for comparing groups |

## 8. Input files

Drafts in the shape the proposal sets out; the schema is fixed when CI validation is built.

- **`shock_windows.yaml`:** case, shock, window type, months, lanes, method ("illustrative"), evidence ids.
- **`causal_labels.yaml`:** one per observed response, with a Shock-T status, competing explanations (AI capex growth, capacity built before the shock) and evidence ids. Drafted after the numbers, by the analyst; the notebook proposes text. A server response can be `TEMPORAL_ALIGNMENT` at most, since servers were excluded; the gear comparison decides whether anything stronger is supported for the gear.
- **`evidence.yaml`:** FACT records for the policy record (done), and INFERENCE records for the team's reading.
- **`evidence_derived.yaml`:** written by the notebook: each DERIVED record names its metric (an engine function), parameters, the windows file, the git commit and the `load_id`s of the data, so a number can be traced to its sources until the engine's calculation runs exist.

## 9. Notebook outline

1. Setup: connect, load the windows and evidence.
2. The policy timeline, from `evidence.yaml`.
3. Monthly supply by origin and mode, with the windows shaded.
4. Origin and mode shares by window, and the diversion rates.
5. Lane intensities: the legs of each lane, their distances and factors.
6. The supply mix per window, and its change.
7. The missing leg into Mexico.
8. The comparison: servers against the exposed gear.
9. Findings: what the data shows (DERIVED), what it suggests (INFERENCE) and what it can't say.
10. Write `evidence_derived.yaml`, and draft causal labels for review.

## 10. Open questions

1. **Where `leg_factors` lives.** Answered: in the engine (`engine/config/leg_factors.yaml`), with the test that each mode names exactly one factor; data-pipelines publishes the factors and their attributes.
2. **Inland mode from seaports.** Truck for this notebook; rail from the West Coast is one of the alternatives the calculator offers, so it's a scenario, not the observed baseline.
3. **The independence assumption** in 7.3: a departure airport's freight is spread over gateways and destinations in the lane's overall proportions.
4. **USMCA qualification of Mexican-assembled servers and gear**, and any duty that followed the semiconductor investigation: for the analysts to establish, as evidence.
5. **The April 2026 metal tariff proclamation** (91 FR 18201) changed how the steel and aluminum duties are assessed; its effect on the three transformer codes after April 2026 isn't established. It falls after the response window.

## 11. Verification

- Engine functions: pytest, against hand-computed values.
- Monthly supply reconciles with `fct_imports_monthly` and `fct_mexico_overland_monthly` totals.
- Each lane's leg weights sum to 1.
- The notebook runs top to bottom from a clean kernel (`jupyter nbconvert --execute`).
