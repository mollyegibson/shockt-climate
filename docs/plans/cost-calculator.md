# Next Step: Cost Calculator

**Status:** Future; not in the MVP. Steps 1, 2 and 4 of Section 3 are built (2026-10-13); the reload (step 3) is next, and the engine (step 5) waits on the team · **Workstream:** Data engineering, engine · **Date:** 2026-10-13

The MVP compares routes by emissions and transit time; freight cost is out of scope. A director deciding whether to fly or ship weighs cost against carbon, so a cost column would make the comparison more useful. This plan records what the sources already support, what they don't, and what adding it would take.

## 1. What the data supports

**International legs, by origin country, HS-10, mode and month.** The Census `hs` endpoint (the one already loaded for country-level imports) reports charges and duty alongside value and weight. The port (`porths`) and state (`statehs`) endpoints report neither ([`hs` variable list](https://api.census.gov/data/timeseries/intltrade/imports/hs/variables.json), [`porths`](https://api.census.gov/data/timeseries/intltrade/imports/porths/variables.json), [`statehs`](https://api.census.gov/data/timeseries/intltrade/imports/statehs/variables.json), checked 2026-10-13):

| Variable | Label |
|---|---|
| `AIR_CHA_MO` | Air Charges |
| `VES_CHA_MO` | Vessel Charges |
| `CNT_CHA_MO` | Containerized Vessel Charges |
| `GEN_CHA_MO` | General Imports, Charges |
| `GEN_CIF_MO` | General Imports, CIF Value |
| `DUT_VAL_MO` | Imports for Consumption, Dutiable Value |
| `CAL_DUT_MO` | Imports for Consumption, Calculated Duty |
| `RP` | Rate Provision Code |

- **Definition:** import charges are the freight, insurance and other costs of bringing goods from the carrier at the foreign port of export to the first US port of entry, excluding duties. For overland shipments from Canada or Mexico they run from the point of origin in that country to the first US port of entry ([UN Expert Group on International Merchandise Trade Statistics, USA country note](https://unstats.un.org/unsd/trade/EG-IMTS/Web%20documents/Country%20Notes/USA%20-%20Country%20Note.pdf); [Census presentation on CIF and FOB imports](https://unstats.un.org/unsd/trade/EG-IMTS/Web%20documents/Papers%20and%20presentations/USA%20-%20Item%209%20-%20Imports%20CIF%20and%20FOB.pdf)). Both are older documents; confirm against current Census documentation before relying on them.
- **What it gives:** charges per kilogram by mode, `AIR_CHA_MO / AIR_WGT_MO` and `VES_CHA_MO / VES_WGT_MO`, for each origin, case code and month. That is the cost side of "fly it or ship it", and it would show freight rates moving in the shock windows.
- **Overland:** `GEN_CHA_MO − AIR_CHA_MO − VES_CHA_MO` is the charge for overland imports, which for Mexico covers the leg from the point of origin in Mexico to the border. Its per-kilogram figure would use the estimated overland weight (`fct_mexico_overland_monthly`), and so carry its range.
- **Duty:** `CAL_DUT_MO` is the duty Census calculates on imports for consumption, and `CAL_DUT_MO / CON_VAL_MO` the duty rate actually paid on a code, origin and month. It answers whether a tariff changed the landed cost of a lane, which the published rate alone can't: most Mexican servers enter duty-free under a chapter 99 provision.
- **Charges are reported by filers,** and may be prorated across a shipment's lines or estimated when unknown at entry (same Census presentation). They are an average for the code, origin and month, not a quote for a lane.

**Spike (2026-10-13).** Adding the six fields `GEN_CHA_MO`, `AIR_CHA_MO`, `VES_CHA_MO`, `CNT_CHA_MO`, `DUT_VAL_MO` and `CAL_DUT_MO` to the loader's request returns the same rows as today's request (847150 for 2025-06: 113 rows; 8504 for 2024-03: 2,429). On the detail rows of both, general charges are never below air plus vessel charges, containerized charges never exceed vessel charges, and dutiable value never exceeds consumption value. For servers from Taiwan in June 2025, air charges were $59.6M on $6.70B of air value (0.9%; $3.58 per kilogram); from Mexico, the overland charge (general minus air and vessel charges) was $0.90M on about $6.49B, about 0.014%, far below TransBorder's 0.3% for all trucked goods (below), which open question 5 has to explain before overland charges are used.

**`RP` is left out of the request.** Adding it splits each row by rate provision (for example duty-free under chapter 99, `19`, and dutiable under chapter 99, `69`; [Census rate provision codes](https://www.census.gov/foreign-trade/reference/codes/rp.html)), which changes the table's grain from month × HS-10 × country. The calculated duty already gives the rate paid; the split by provision, if needed, would be a separate dataset with its own grain.

**Mexico land crossings, by crossing, HS-2 chapter, mode and month.** BTS TransBorder's `FREIGHT_CHARGES` is already loaded (`raw.bts_transborder.freight_charges`) and is filled for imports from Mexico. Over the loaded months: truck $2.93B on $914B of value (about 0.3%), rail $0.32B on $27.7B (about 1.1%). Its definition isn't in the documents read so far; check the [TransBorder codes document](https://www.bts.gov/sites/bts.dot.gov/files/docs/browse-statistical-products-and-data/transborder-freight-data/220171/all-codes-north-american-transborder-freight-raw-data.pdf) before use. It would cross-check the Census overland charge at chapter level.

## 2. What it doesn't support

- **US inland legs** (port, gateway or crossing to the destination state): no loaded source has a cost. Trucking and rail rate sources would be new data.
- **Port-level or state-level cost:** charges exist only at country level (`hs`), so a lane through Los Angeles and one through Savannah get the same per-kilogram charge for an origin, code and mode.
- **Door-to-door cost:** without inland legs, a route's cost covers the international leg only. The comparison screen would have to say so.
- **Duty by mode:** duty is reported per code, origin and month, not per mode.

## 3. What adding it would take

1. **Built. Migration `0015`:** add `gen_cha_mo`, `air_cha_mo`, `ves_cha_mo`, `cnt_cha_mo`, `dut_val_mo` and `cal_dut_mo` (all `bigint`, USD) to `raw.census_hs`. Rows loaded before the migration keep nulls until reloaded.
2. **Built. Loader:** add the six fields to the `hs` request in `census_api.py` (Section 5.1 of the [ingestion plan](./data-ingestion-pipelines.md)). The port and state requests don't change.
3. **Reload** the `hs` endpoint from the API for the date range (`shockt ingest census -d hs`): the archived responses hold only the fields requested, so `--from-archive` can't add them. Each partition's new load supersedes the old one.
4. **Built. dbt:**
   - `stg_census_hs` renames the fields to `general_charges_usd`, `air_charges_usd`, `vessel_charges_usd`, `containerized_charges_usd`, `dutiable_value_usd` and `calculated_duty_usd`;
   - `unpivot_modes` gains a `charges_usd` column for the relations that have charges, with `other` = general − air − vessel charges, so `fct_imports_monthly` carries charges per mode;
   - `fct_import_duties_monthly` (month × HS-10 × country): consumption value, dutiable value and calculated duty;
   - tests: general charges ≥ air plus vessel charges, containerized ≤ vessel charges, and dutiable value ≤ consumption value, each an error.
5. **Engine:** a cost per tonne for each route's international leg, from charges per kilogram, next to its emissions and transit time, with the overland range where the weight is estimated.

## 4. Open questions

1. Confirm the Census definition of charges in current documentation.
2. Confirm what TransBorder's `FREIGHT_CHARGES` covers for imports.
3. How should the app present a cost that covers only part of the route?
4. Is a country-level average charge useful for a user's own lane, or only for showing how charges moved in a shock?
5. Why is the Census overland charge for Mexican servers (about 0.014% of value in June 2025) so far below TransBorder's truck charges (about 0.3% of all goods)? Candidates: filers not reporting charges for overland entries, or charges billed separately from the goods' value. Unverified.
6. Should the cost include duty (a landed cost), or freight only? Duty is per code and origin, not per mode, so it doesn't change the fly-or-ship choice but does change the choice of origin.
