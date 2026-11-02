# Apparel and Footwear Analysis

**Status:** Draft · **Workstream:** Analysis · **Date:** 2026-11-02

This plan covers the apparel and footwear notebook (`analysis/apparel/apparel_tariffs_2025.ipynb`). It follows the [Case 1](./case-1-analysis.md) and [Case 2](./case-2-analysis.md) plans: it reads `core`, computes with engine functions, and reuses both cases' windows. It doesn't add engine functions or input files.

## 1. Goal

Apparel was proposed as the lead product because it was exposed to both shocks: it paid the 2025 tariffs, and its South Asian origins ship via Suez. The notebook answers:

1. **Tariffs, origin:** did China's share of supply fall from 2025, and which origins gained? Is the change visible by value as well as tonnage, and across every HS-6 code?
2. **Tariffs, emissions:** how much did emissions per tonne of supply change, compared with the same months a year earlier, and how much came from origin and mode?
3. **Red Sea:** did the air share rise, or the East Coast share of sea tonnage fall, for the origins whose East Coast routes use the Red Sea, compared with the origins whose routes don't?

## 2. Scope

- **Products:** the ten apparel and footwear HS-6 codes in `config/hs_codes.yaml` under `apparel_footwear`.
- **Origins:** the configured origins (`region <> 'other'` in `dim_country`): Asia and Mexico. Central American origins are not configured, so shares are shares of supply from Asia and Mexico, not of all US apparel imports.
- **Windows:**
  - **Tariffs:** the Case 1 windows (`inputs/cases/tariffs_2025/shock_windows.yaml`). They were drawn for the reciprocal tariffs. China's own tariffs began earlier, inside the anticipation window, so for China that window isn't anticipation.
  - **Red Sea:** the Case 2 baseline and the `red_sea_diversions` window from its rule (`inputs/cases/panama_red_sea_2023/shock_windows.yaml`), cut at the end of the tariff baseline so the two shocks don't overlap.

## 3. Comparisons

Apparel is seasonal: emissions per tonne are higher from May to December than from January to April in every loaded year. Each comparison therefore covers the same calendar months.

- **Tariffs:** the response window against the same months a year earlier. Both lie inside the Red Sea window, so the comparison holds the Red Sea constant.
- **Red Sea:** each window's full calendar years, 2022 (baseline) against 2024 (Red Sea, before the tariffs).

The notebook also shows the full-baseline comparison, labelled as mixing seasons.

## 4. Known gaps

The emissions mix leaves out lanes that have no computable legs. In the response window about a fifth of tonnage is left out, and the gap grows as the gaining origins grow.

| Gap | Lanes | Cause |
|---|---|---|
| No departure ports | Bangladesh and Cambodia by sea | Departure-port weights come from Climate TRACE container voyages to the US, and neither country has any |
| No departure airports | Sri Lanka and Pakistan by air, among others | The air leg has no departure-airport weights for these origins. The cause is unconfirmed; a likely one is that their air freight reaches the US through hubs in third countries |

How to source these is open (Section 5).

## 5. Open questions

1. **Bangladesh and Cambodia sea routes.** **Proposed (2026-11-02):** feeder voyages from Climate TRACE and a two-part sea leg through the hub ([ingestion plan](./data-ingestion-pipelines.md), Section 5.7.1). The same fix covers Jordan and Myanmar.
2. **Sri Lanka and Pakistan air routes.** Which source gives the departure airports, or hub routings, of their US-bound air freight?
3. **Evidence records** for China's 2025 tariffs, with their dates, so that the windows can be cited for China.
4. **Causal labels:** the notebook proposes none yet.
