# Engine API: `shockt_engine`

Pure functions, no database. All imports come from `shockt_engine` directly.

## Shares and windows

### `shares(values: dict[K, float]) → dict[K, float]`
Each key's share of the total. Raises `ShareError` if total is not positive.

### `ShareError`
Raised when a share, diversion or window computation receives non-positive totals.

### `share_change(baseline: dict[K, float], window: dict[K, float]) → dict[K, float]`
Each category's change in share from baseline to window. A category missing from one
side has a share of 0 there.

### `diversion_rate(s_from_baseline, s_to_baseline, s_to_response) → float`
The fraction of the `from` category's baseline tonnage that moved to the `to`
category.

### `Window(name: str, first: date, last: date)`
A named range of whole months (both ends included). `first` and `last` must be the
first of a month.

### `WindowSummary`
Fields: `mean`, `low`, `high`, `months`. Returned by `window_summary`.

### `window_summary(values, windows, weights=None) → dict[str, WindowSummary]`
For each window, the weighted mean, low and high of the monthly values inside it.
`WindowSummary` has fields: `mean`, `low`, `high`, `months`.

## Emissions

### `EmissionsError`
Raised when a distance or intensity can't be formed from the given values.

### `LegDistance`
Fields: `km`, `covered_share` (share of weight on node pairs that have a distance).

### `pair_weighted_distance(distances, pair_weights) → LegDistance`
A leg's distance averaged over node pairs with known weights. Pairs with no distance
are left out and the rest renormalised.

### `weighted_leg_distance(distances, origin_weights, destination_weights) → LegDistance`
A leg's distance averaged over node pairs when no source links origins to destinations:
each pair's weight is the product of the two ends' weights.

### `SeaLegDistance`
Fields: `km`, `observed_share` (share from real voyages), `covered_share`.

### `sea_leg_distance(observed, modelled, departure_weights, arrival_weights) → SeaLegDistance`
A sea leg's distance averaged over arrival ports. Ports with an observed distance (from
the origin's voyages) use it; otherwise the modelled distances from departure ports.

### `Leg(km: float, kg_co2e_per_tkm: float)`
One segment of a lane. `kg_co2e_per_t` = `km * kg_co2e_per_tkm`.

### `lane_intensity(legs: Iterable[Leg]) → float`
Emissions per tonne of a lane: sum of `km * kg_co2e_per_tkm` over its legs.

### `mix_intensity(lane_shares, lane_intensities) → float`
Emissions per tonne of a supply mix: each lane's share of tonnage times its intensity.
Shares must sum to 1.

### `break_even_km(advantage_kg_per_t, kg_co2e_per_tkm) → float`
How far a tonne must travel at the given factor to emit the given advantage: the
component leg that would cancel a route's advantage.

## Lanes

### `LaneMode`
Type alias: `Literal["air", "vessel", "truck", "rail"]`.

### `InlandMode`
Type alias: `Literal["truck", "rail"]`.

### `lane_legs(mode, inputs, inland="truck") → LaneResult`
The legs of a lane in the given mode, with their distances and factors.
`mode` is `"air"`, `"vessel"`, `"truck"` or `"rail"`.
`inputs` is a `LaneInputs` (weights, distances, factors, observed_sea, crossing_plants).
`inland` is `"truck"` or `"rail"` (only for vessel lanes).
Returns `LaneResult` with `.legs` (tuple of `LegResult`), `.missing_legs` and
`.kg_co2e_per_t`.

### `LaneInputs(weights, distances, factors, observed_sea={}, crossing_plants={})`
What a lane's legs need for one origin, group of HS codes and window. See
`references/data-access.md` for how `cases.lane_inputs()` builds this from the reader.

### `LaneResult`
Fields: `mode`, `legs` (tuple of `LegResult`), `missing_legs`, property `kg_co2e_per_t`.

### `LegResult`
Fields: `name`, `factor_mode`, `km`, `kg_co2e_per_tkm`, `covered_share`,
`observed_share` (sea legs only). Property `kg_co2e_per_t`.

## Factors

### `FactorSelectionError`
Raised when a mode's settings match no emission factor, or more than one.

### `Factor`
Fields: `source`, `source_row_id`, `mode`, `variant`, `vehicle_type`, `size_class`,
`haul`, `radiative_forcing`, `wtw_kg_co2e_per_tkm`.

### `LegFactor`
Which factor a mode's legs use, by the factor's attributes. Fields: `source`,
`vehicle_type`, `size_class`, `haul`, `radiative_forcing`.

### `LegFactors`
The factor choices for all four modes. Fields: `ocean`, `air`, `truck`, `rail`.
Method `for_mode(mode)` returns the `LegFactor` for that mode.

### `select_factor(factors, mode, choice) → Factor`
The one factor that matches `choice` for `mode`. Raises `FactorSelectionError` if
none or several match.

### `select_factors(factors, choices) → dict[Mode, Factor]`
The emission factor each mode uses, from the `leg_factors.yaml` configuration.
Call `load_leg_factors()` for the choices, `core.factors(conn)` for the rows.

### `load_leg_factors() → LegFactors`
Reads `engine/config/leg_factors.yaml`.

## Decomposition

### `mix_decomposition(baseline, window, dimensions) → MixDecomposition`
Shapley decomposition of the change in a supply mix's emissions per tonne: splits the
change between each dimension (e.g. origin, coast, mode) and each intensity component
(e.g. international, inland). Each factor's effect is its Shapley value; effects sum
to the full change.

### `MixCell(tonnes: float, intensity: dict[str, float])`
One cell of a supply mix: its tonnage and its emissions per tonne broken into named
components (e.g. `{"international": 12.3, "inland": 4.5}`).

### `MixDecomposition`
Fields: `baseline` (kg CO2e/t), `window` (kg CO2e/t), `effects` (dict of factor name
to its contribution in kg CO2e/t).

## Shock dating

### `ShockDatingError`
Raised when shock windows can't be found from the values given.

### `OutsideRange`
Fields: `baseline_low`, `baseline_high`, `runs` (tuple of `(first_month, last_month)`
pairs).

### `months_outside_range(series, baseline_first, baseline_last, side, max_gap) → OutsideRange`
Finds runs of months after the baseline whose value falls outside the baseline range.
`side` is `"below"` or `"above"`. Up to `max_gap` consecutive months back inside the
range don't end a run. Returns `OutsideRange` with `baseline_low`, `baseline_high`,
and `runs` (tuple of `(first_month, last_month)` pairs).

### `passage_used(open_km, closed_km, tolerance_km) → bool`
Whether a route uses a passage: closing it makes the route longer by more than
`tolerance_km`.

## Analysis helpers (in `shockt_analysis.cases`)

These are not in the engine but are available to analysis scripts:

### `cases.load_windows(path) → list[Window]`
Reads a `shock_windows.yaml` file.

### `cases.with_window(df, windows, column="month") → DataFrame`
Adds a `window` column naming the window each month falls in, or null.

### `cases.with_origin_group(df, named) → DataFrame`
Adds an `origin_group` column: the ISO3 code for named origins, else `other`.

### `cases.monthly_supply(supply, codes, named) → DataFrame`
Tonnes by month, origin group and mode for selected HS codes.

### `cases.window_shares(monthly, windows, by) → DataFrame`
Tonnes and share of each category within each window.

### `cases.share_changes(window_share_frame, baseline, window, key) → dict[str, float]`
Each category's change in share from baseline to window.

### `cases.LaneContext(weights, observed_sea, distances, factors, crossing_plants)`
Everything the lanes need besides the lane itself.

### `cases.lane_inputs(context, census_cty_code, iso3, codes, mode, window, coast=None, states=None) → LaneInputs`
Builds `LaneInputs` for one origin's lane.

### `cases.lane_intensities(supply, codes, windows, context) → (DataFrame, DataFrame)`
Emissions per tonne of every origin's lane with tonnage in each window, and its legs.

### `cases.mix_by_month(supply, codes, windows, lanes, tonnes="weight_t") → DataFrame`
Emissions per tonne of the whole supply mix, by month.

### `cases.lane_mix_cells(supply, codes, window, legs) → dict[(str, str), MixCell]`
The supply mix's cells for one window, origin × mode.

### `cases.leg_frame_parts(legs) → dict[str, float]`
A lane's emissions per tonne in two parts from a legs frame: `international` and
`inland`.

### `cases.suspect_air_months(air, low, high) → DataFrame`
Origin × HS-6 × months whose air value per kg falls in the imputed-weight band.

### `cases.origin_air_ratios(air, before) → DataFrame`
Each origin's air value per kg over the months before `before`, with p10 and p90.

### `cases.all_origins_air_ratio(air, before) → float`
Air value per kg across all origins' months before `before`.

### `cases.reweight_air(supply, suspect, usd_per_kg, default=None) → DataFrame`
`supply` with suspect months' air tonnes recomputed as value ÷ `usd_per_kg`.

### `cases.plot_waterfall(ax, decomposition, labels, title, window_label="window")`
A waterfall chart from baseline mix to window's, one bar per Shapley effect.
