# Next Step: Cost Calculator

**Status:** Future; not in the MVP · **Workstream:** Data engineering, engine · **Date:** 2026-10-13

The MVP compares routes by emissions and transit time; freight cost is out of scope. A director deciding whether to fly or ship weighs cost against carbon, so a cost column would make the comparison more useful. This plan records what the sources already support, what they don't, and what adding it would take, so the decision can be made after `dim_nodes` and the distance tables are built.

## 1. What the data supports

**International legs, by origin country, HS-10, mode and month.** The Census `hs` endpoint (the one already loaded for country-level imports) reports charges alongside value and weight. The port (`porths`) and state (`statehs`) endpoints don't ([variable lists](https://api.census.gov/data/timeseries/intltrade/imports/hs/variables.json), checked 2026-10-13):

| Variable | Label |
|---|---|
| `AIR_CHA_MO` | Air Charges |
| `VES_CHA_MO` | Vessel Charges |
| `CNT_CHA_MO` | Containerized Vessel Charges |
| `GEN_CHA_MO` | General Imports, Charges |
| `GEN_CIF_MO` | General Imports, CIF Value |

- **Definition:** import charges are the freight, insurance and other costs of bringing goods from the carrier at the foreign port of export to the first US port of entry, excluding duties. For overland shipments from Canada or Mexico they run from the point of origin in that country to the first US port of entry ([UN Expert Group on International Merchandise Trade Statistics, USA country note](https://unstats.un.org/unsd/trade/EG-IMTS/Web%20documents/Country%20Notes/USA%20-%20Country%20Note.pdf); [Census presentation on CIF and FOB imports](https://unstats.un.org/unsd/trade/EG-IMTS/Web%20documents/Papers%20and%20presentations/USA%20-%20Item%209%20-%20Imports%20CIF%20and%20FOB.pdf)). Both are older documents; confirm against current Census documentation before relying on them.
- **What it gives:** charges per kilogram by mode, `AIR_CHA_MO / AIR_WGT_MO` and `VES_CHA_MO / VES_WGT_MO`, for each origin, case code and month. That is the cost side of "fly it or ship it", and it would show freight rates moving in the shock windows.
- **Overland:** `GEN_CHA_MO − AIR_CHA_MO − VES_CHA_MO` is the charge for overland imports, which for Mexico covers the leg from the point of origin in Mexico to the border. Its per-kilogram figure would use the estimated overland weight (`fct_mexico_overland_monthly`), and so carry its range.
- **Charges are reported by filers,** and may be prorated across a shipment's lines or estimated when unknown at entry (same Census presentation). They are an average for the code, origin and month, not a quote for a lane.

**Mexico land crossings, by crossing, HS-2 chapter, mode and month.** BTS TransBorder's `FREIGHT_CHARGES` is already loaded (`raw.bts_transborder.freight_charges`) and is filled for imports from Mexico. Over the loaded months: truck $2.93B on $914B of value (about 0.3%), rail $0.32B on $27.7B (about 1.1%). Its definition isn't in the documents read so far; check the [TransBorder codes document](https://www.bts.gov/sites/bts.dot.gov/files/docs/browse-statistical-products-and-data/transborder-freight-data/220171/all-codes-north-american-transborder-freight-raw-data.pdf) before use. It would cross-check the Census overland charge at chapter level.

## 2. What it doesn't support

- **US inland legs** (port, gateway or crossing to the destination state): no loaded source has a cost. Trucking and rail rate sources would be new data.
- **Port-level or state-level cost:** charges exist only at country level (`hs`), so a lane through Los Angeles and one through Savannah get the same per-kilogram charge for an origin, code and mode.
- **Door-to-door cost:** without inland legs, a route's cost covers the international leg only. The comparison screen would have to say so.

## 3. What adding it would take

1. Add `AIR_CHA_MO`, `VES_CHA_MO`, `CNT_CHA_MO` and `GEN_CHA_MO` to the `hs` loader's request and to `raw.census_hs` (a new migration).
2. Reload the `hs` endpoint from the API for the date range: the archived responses hold only the fields requested, so `--from-archive` can't add them.
3. A core model of charges per kilogram by month × HS-6 × country × mode, with the overland range, and a reconciliation test that `GEN_CHA_MO` ≥ air plus vessel charges.
4. In the engine, a cost per tonne for each route's international leg, next to its emissions and transit time.

## 4. Open questions

1. Confirm the Census definition of charges in current documentation.
2. Confirm what TransBorder's `FREIGHT_CHARGES` covers for imports.
3. How should the app present a cost that covers only part of the route?
4. Is a country-level average charge useful for a user's own lane, or only for showing how charges moved in a shock?
