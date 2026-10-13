# Case 2 Analysis: Panama Drought and Red Sea Diversions, 2023–24

**Status:** Draft · **Workstream:** Analysis, engine · **Date:** 2026-10-13

This plan covers the first Case 2 notebook. It follows the [Case 1 plan](./case-1-analysis.md): it reads `core`, computes with engine functions, and drafts the case's input files. It reuses Case 1's engine functions and adds the few that a physical shock needs. It doesn't cover the engine's `outputs` tables, CI or the app.

## 1. Goal

Show how sea freight from Asia to the US responded to two physical shocks, the Panama Canal drought restrictions and the Red Sea diversions, and what that did to the transport emissions of delivering a tonne, as a range. The proposal names three responses: longer sea routes, a shift from all-water East Coast delivery to West Coast ports with inland transport east, and diversion to air. The case measures each, and keeps accounting (what changed) separate from attribution (why).

The notebook answers six questions:

1. **Shock dating:** in which months were Panama and Bab el-Mandeb transits below their baseline range?
2. **Route length:** how much longer did observed voyages from Asia to the US East and Gulf coasts become, and which lanes use which passage?
3. **Port of entry:** did the share of Asian vessel tonnage unladen on the West Coast rise, and was the rise freight bound east or growth in West-bound freight?
4. **Mode:** did any of the freight move to air?
5. **Delivery emissions per tonne:** for each origin, arrival coast and inland mode, what does delivering a tonne emit, per window?
6. **The supply mix:** how much did emissions per tonne change, and how much of the change came from route length, port of entry, origin and mode?

## 2. What the data shows already

Read-only queries on 2026-10-13. They set the scope; the notebook recomputes each as a DERIVED record.

- **The electrical gear carries the case.** Vessel tonnage from Asia to East Coast ports was 16,449 t (2022) to 68,376 t (2025) for the six gear codes, against at most 2,122 t a year for servers. This answers the proposal's first check: servers barely move by sea to the East Coast.
- **The gear moves in containers:** 92–99.5% of its vessel tonnage from Asia is containerized for four codes, 79% for 850433, and 49.5% for 850423 (the largest liquid-dielectric transformers). Climate TRACE's container-ship voyages therefore stand for most of it; half of 850423 moves on other ships.
- **The Red Sea shock is large and lasting.** Container transits of Bab el-Mandeb fell from 494–634 a month (2023, quarterly averages) to 132 in 2024 Q1, while the Cape of Good Hope's rose from 191–217 to 536. The mean container voyage from Asia to the US East and Gulf coasts went from 17,394–18,780 km (2022 to 2023 Q3) to 19,496–20,605 km from 2023 Q4, and has stayed there through 2026 Q2.
- **The Panama shock barely touched container ships.** Total Panama transits fell from about 1,000 a month to 628 in 2024 Q1 and recovered by 2024 Q3, but container transits stayed at 209–249. Whether the Panama restrictions changed the gear's routes is an open question (Section 10).
- **The West Coast's share rose, but so did West-bound freight.** The West Coast's share of the gear's Asian vessel tonnage was 32–41% from 2022 to 2024 H1, then 52% (2024 H2), 43% (2025 H1) and 53–55% since. Over the same period, vessel tonnage bound for the West Coast control states (California, Oregon, Washington, Arizona) grew from 6,676 t to 64,961 t a half-year, while freight bound for the East-bound states (Virginia, Georgia, Ohio) rose to 21,490 t in 2024 H1 and fell to about 10,000 t. Destination growth, not port switching, may explain much of the rise; the state-level checks (Section 7.3) decide.
- **Air is small:** 0.2–1.5% of the gear's tonnage from Asia through 2026 H1.
- **Weights look reported.** The gear's vessel value per kilogram spreads widely, with none of the clustering that marks likely imputed air weights for servers (ingestion plan, Question 18).

## 3. Scope

- **Products:** the six gear codes in `config/hs_codes.yaml`: liquid-dielectric transformers (850421, 850422, 850423), dry transformers above 16 kVA (850433, 850434) and switchgear above 1,000 V (853720). Servers by vessel are shown for completeness, not as a finding. The method takes any HS codes, so another product can reuse it with a config change and a reload.
- **Origins:** the Asian origins (`region = 'asia'` in `dim_country`). Korea, China and Taiwan, the steady gear lanes (ingestion plan, Question 16), each on their own; the rest as "other Asian origins".
- **Months:** January 2022 to the latest loaded month.
- **Legs:**
  - vessel: departure port → US seaport (observed distance where voyages exist, `searoute` otherwise) → destination state by truck, or by rail as the alternative;
  - air: departure airport → US gateway → destination state by truck.
- **Out of scope:** the leg from factory to departure port, production emissions, freight cost, and transit time (Section 10).

## 4. Windows

Set by rule from PortWatch, as the proposal specifies, and recorded in `inputs/cases/panama_red_sea_2023/shock_windows.yaml` with the method and its parameters.

| Window | Shock | Rule |
|---|---|---|
| Baseline | (case) | January 2022 to the month before either shock's first month |
| Effective | Panama drought restrictions | Months when Panama transits (all ship types) are below the baseline range |
| Effective | Red Sea diversions | Months when Bab el-Mandeb container transits are below the baseline range |

- **Baseline range:** the lowest and highest monthly value in the baseline months. A declared choice, in the windows file's method parameters; a percentile band is the alternative if one low baseline month makes the rule too lax.
- **Windows are runs of whole months.** Up to `max_gap` consecutive months back inside the range don't end the window; `max_gap` is a parameter.
- **The Red Sea window is open-ended** and ends at the last month loaded, which the manifest records.
- **Runs after the case:** a rule keeps the runs that start by its `starts_by` month (December 2024 for both shocks). Later runs, such as Panama's in 2025 and 2026, belong to later events and are reported, not used.
- **Partial months:** transits are per reported day, and PortWatch's latest month, reported only in part, is left out.
- **The two shocks overlap** from late 2023 to mid-2024. They stay separate shocks with their own windows, as Shock-T requires, and the overlap is noted in the causal labels.
- **Evidence for the dates:** FACT records in `inputs/cases/panama_red_sea_2023/evidence.yaml`: the Panama Canal Authority's advisories cutting capacity (July and October 2023) and restoring it (June and August 2024), and the carriers' Red Sea pause (December 2023) and Cape diversion (January 2024). The carrier records cite news reports of the carriers' statements, because the carriers' own pages couldn't be retrieved.

## 5. Data

Read from `core` (and the distance seeds in `raw`) with the read-only analyst login:

| Table | Used for |
|---|---|
| `fct_chokepoint_transits_monthly` | Shock dating: monthly transits by chokepoint and ship type |
| `agg_voyage_lanes_monthly` | Observed voyage distance and duration by origin and US coast region |
| `agg_observed_sea_distances_monthly`, `seed_sea_distances` | Sea leg distances: observed per origin and arrival port, `searoute` per scenario (open, Panama closed, Red Sea closed, both) |
| `fct_imports_port_monthly` | Vessel and air tonnage by origin, port and coast region |
| `fct_imports_state_monthly` | Case-code vessel tonnage by state of destination |
| `fct_imports_state_port_quarterly` | All goods: state of destination × port of unlading, for the inland-routing check |
| `fct_imports_monthly` | Country-level tonnage and containerized share |
| `dim_nodes`, `fct_node_weights_monthly` | Each lane's departure ports, arrival seaports and destination states |
| `seed_road_distances`, `seed_rail_distances`, `seed_air_distances` | Inland and air legs |
| `ref_emission_factors` | Factors per tonne-km, chosen by `engine/config/leg_factors.yaml` |

## 6. Layout

Case 1's layout, with one change: the functions both notebooks use (loading windows, assigning months to windows, window shares, lane inputs, the supply mix) are in a shared `shockt_analysis/cases.py`, and `shockt_analysis/case2.py` keeps only what is Case 2's own. `lane_inputs` takes an arrival coast and destination states, and the engine's `lane_legs` takes the inland mode of a vessel lane (truck or rail).

| Path | Holds |
|---|---|
| `analysis/case2/case2_panama_red_sea.ipynb` | The notebook |
| `analysis/src/shockt_analysis/case2.py` | Case 2's data shaping |
| `inputs/cases/panama_red_sea_2023/` | `shock_windows.yaml`, `evidence.yaml`, `evidence_derived.yaml`, `causal_labels.proposed.yaml` |

## 7. Method

### 7.1 Shock dating

For each chokepoint, the monthly series against the baseline range; the windows follow from the rule in Section 4. The Cape of Good Hope's transits are shown as the mirror of Bab el-Mandeb's, not used to set windows.

### 7.2 Route length

- **Observed:** the mean and median voyage distance from Asia to the East and Gulf coasts by month (`agg_voyage_lanes_monthly`), and per origin and arrival port (`agg_observed_sea_distances_monthly`), by window.
- **Which passage a lane uses:** a rule in code, not a list. A departure port → arrival port pair uses Panama if its `searoute` distance with Panama closed is longer than its open distance, and Suez likewise with the Red Sea closed. The rule is tested against pairs whose route is unambiguous on a map, and it splits the lanes between the two shocks.
- **Modelled check:** for each pair, the closed-passage distance against the observed distance in the effective window. Observed distances near the closed-passage distance mean ships rerouted; near the open distance, they didn't.

### 7.3 Port of entry and inland routing

- **Port-of-entry shares:** each coast region's share of the gear's Asian vessel tonnage, by month and window (`fct_imports_port_monthly`).
- **Inland routing, the proposal's two DERIVED checks:**
  1. **All goods** (`fct_imports_state_port_quarterly`): each quarter, the share of vessel imports from Asia bound for the East-bound states (Virginia, Georgia, Ohio) that was unladen at West Coast ports, against the West Coast control states (California, Oregon, Washington, Arizona). Texas and Illinois are reported separately.
  2. **The case codes** (`fct_imports_state_monthly`): vessel tonnage bound for the East-bound states against the control states, by window.
- **Reading:** if the West Coast share of East-bound freight rose in the effective windows while the control states held, that supports "West Coast port + inland east" (an INFERENCE, as the proposal says). If the West Coast share rose because West-bound freight grew, the port shift is destination mix, and the causal label says so. The 2022–23 fall in the West Coast share of East-bound freight (ingestion plan, assumptions) is a pre-trend the baseline has to show.

### 7.4 Mode

The air share of the gear's tonnage from Asia by window, with diversion rates as in Case 1 (7.2 of its plan). Expected small; reported either way.

### 7.5 Delivery emissions per tonne, per lane

A lane is an origin × arrival coast region × inland mode, so all-water to the East Coast and West Coast plus rail east are separate lanes for the same origin. The lane method is Case 1's (7.3 of its plan), with the arrival seaport weights restricted to the lane's coast. The sea leg uses the window's observed distance, so the Red Sea effect enters through distance. For freight bound for the East-bound states, the notebook compares, per window:

- all-water to an East Coast port, then truck to the state;
- all-water to a Gulf port, then truck;
- West Coast port, then rail; and West Coast port, then truck.

These are the alternatives the calculator will offer; here they are measured, not recommended.

### 7.6 The supply mix and its decomposition

The emissions per tonne of the gear's Asian supply per window: each lane's share of tonnage × its intensity (Case 1, 7.4). The change from baseline to each effective window is split between four factors, each at its baseline or its window value:

- **route length:** the lanes' emissions per tonne, which move with the observed sea distance;
- **port of entry:** each origin's shares of arrival coasts;
- **origin:** the origins' shares of tonnage;
- **mode:** the air share within each origin and coast.

A factor's effect is its Shapley value: the change from switching it to its window value, averaged over every order of switching the four, so the effects sum to the whole change. A first try with one-at-a-time effects left a remainder as large as the effects for Case 2's gear, because small origins changed their mode mix as their share grew; the Shapley split has no remainder to explain.

### 7.7 Engine functions

New, each a pure function with tests pinned to hand-computed values:

| Function | Computes |
|---|---|
| `months_outside_range(series, baseline_first, baseline_last, side, max_gap)` | The runs of months below (or above) the baseline range: the shock windows |
| `passage_used(open_km, closed_km, tolerance_km)` | Whether a port pair's route uses a passage, from its open and closed distances |
| `mix_decomposition(baseline, window, dimensions)` | Each dimension's and the intensities' Shapley share of the change in the mix's emissions per tonne |

Reused from Case 1: `shares`, `share_change`, `diversion_rate`, `window_summary`, `weighted_leg_distance`, `sea_leg_distance`, `lane_legs`, `lane_intensity`, `mix_intensity`, `select_factors`. `mix_decomposition` also replaces the ad hoc split in Case 1's notebook.

## 8. Input files

As in Case 1 (8 of its plan), under `inputs/cases/panama_red_sea_2023/`:

- **`shock_windows.yaml`:** the baseline months and, per shock, method `rule` with the chokepoint, series, side, `max_gap` and `starts_by` as parameters. The windows the rules produce are recorded in `evidence_derived.yaml` on every run, not typed into this file.
- **`evidence.yaml`:** FACT records for the Panama Canal Authority advisories and the carrier announcements, each checked against its source.
- **`evidence_derived.yaml`:** written by the notebook.
- **`causal_labels.proposed.yaml`:** proposed by the notebook. Candidates: route length on Suez lanes (`DIRECT_CAUSAL` if observed distances match the Cape route, as the proposal expects), the West Coast share (`CONTRIBUTING_FACTOR` at most, given West-bound growth), air (likely no response).

## 9. Notebook outline

1. Setup: connect, load the windows and evidence.
2. Shock dating: transits by chokepoint and ship type, with the baseline range and the windows.
3. Route length: observed voyage distances, and which lanes use which passage.
4. Port of entry: coast shares, and the two inland-routing checks.
5. Mode: air share and diversion rates.
6. Lane intensities, including the East-bound alternatives.
7. The supply mix per window and its decomposition.
8. Results at a glance: sea-leg emissions per tonne on Suez and Panama lanes, the four routes to the East-bound states, and the decomposition as a waterfall.
9. Findings: DERIVED, INFERENCE, and what the data can't say.
10. Write `evidence_derived.yaml` and draft causal labels.

## 10. Open questions

1. **Is Panama a shock for this freight?** Container transits barely fell, and the Canal Authority gave full container vessels priority for Panamax slots from August 2023 (`ev_panama_acp_a35_2023_capacity_cut`). If container lanes kept their Panama slots, the Panama shock may show only for non-container freight (half of 850423). The notebook reports it either way; the proposal's framing may need to put the Red Sea first.
2. **Confounders in the same months:** AI-driven growth in West-bound gear (the control states' tenfold growth), the 2025 tariffs on the gear (Case 1 found its origin shares barely moved), and the 2024 East Coast port labor dispute risk the proposal names. Each goes in the causal labels as a competing explanation.
3. **Non-container gear:** `fct_voyages` keeps container ships only. Half of 850423 moves on other ships, whose distances the raw Climate TRACE table also holds; whether to add them depends on how much of the result rests on 850423.
4. **Transit time:** the proposal's comparison shows transit time beside emissions. `agg_voyage_lanes_monthly` has voyage duration, so the sea leg's time is measurable; inland and port dwell times aren't.
5. **State of destination** is the destination known at entry filing, not necessarily where the goods are used (proposal, Data constraints).
6. **Inland mode from the West Coast:** rail or truck. The notebook shows both; no loaded source splits them for the case codes.

## 11. Verification

- Engine functions: pytest, against hand-computed values; `passage_used` against port pairs with known routes.
- Coast shares reconcile with `fct_imports_monthly` vessel totals (within the unplaced-port tolerance of the ingestion plan, 7.4).
- Each lane's leg weights sum to 1.
- The notebook runs top to bottom from a clean kernel.
