# Refrigeration Analysis: 2025 Trade-Policy Shocks and Refrigerator Component Supply

**Status:** Draft · **Workstream:** Analysis, engine · **Date:** 2026-11-02

This plan covers the refrigeration case notebook: US imports of refrigerator components (compressors and stainless steel sheet) under the 2025 trade-policy shocks, and what the tariffs did to the transport emissions of delivering a tonne to the US.

## 1. Goal

Show where US supply of refrigerator components moved between origins and modes around the 2025 trade-policy shocks, and what that did to the transport emissions of delivering a tonne to the US. Unlike servers (heading 8471, excluded from the reciprocal tariffs within nine days), neither heading 8414 (compressors) nor heading 7219 (steel sheet) was excluded, so both stayed exposed.

The notebook answers five questions:

1. **Origin shares:** how much of US refrigerator component tonnage came from China, Taiwan, Mexico, Thailand, Vietnam and South Korea, by month and by window?
2. **Mode shares:** within each origin, how much came by air, vessel, truck and rail?
3. **Per-family comparison:** do compressors (841430) and steel sheet (721934, candidate) move alike? If not, the steel family may serve a different supply chain.
4. **Delivery emissions per tonne:** for each origin and mode, how much CO₂e does delivering a tonne to its US destination emit?
5. **The supply mix:** what was the emissions per tonne of the whole US refrigerator component supply in each window, and what moved it?

**Business context.** GE Appliances (Haier) manufactures refrigerators using steel cabinets and compressors, with supply chains running from Chinese manufacturers to US ports. The 2025 tariffs created a component backlog. Competitors (manufacturing in the US and Sweden) expected a demand surge. Census trade data is aggregate and does not prove a GE Appliances or Haier supplier, shipment, or destination.

## 2. What the policy record says

The refrigeration components face the same 2025 reciprocal tariffs as the other cases. The evidence file (`inputs/cases/refrigeration/evidence.yaml`) records the relevant official documents, checked against their source text. Key points:

- **Neither 841430 nor 721934 appears on the CBP exclusion list** (CSMS #64724565, April 11, 2025). Both stayed subject to the reciprocal tariffs from April 5, 2025.
- **721934 (steel sheet)** is likely also subject to the 2018 Section 232 steel duties (Proclamation 9705). This needs verification against the HTSUS treatment.
- **The USMCA exemption** (EO 14232, March 7, 2025) applies to USMCA-qualifying goods of Mexico, but whether refrigerator components assembled in Mexico qualify depends on their rules of origin.

## 3. Scope

- **Products:** two HS families under the `refrigeration` case.
  - Compressors, HS 841430 — reviewed family, runnable aggregate context.
  - Stainless steel flat-rolled sheet, HS 721934 — **candidate, REVIEW_REQUIRED**. Confirm exact commodity mapping to refrigerator cabinet sheet before reporting. Kept as a separate product group in the notebook.
- **Origins:** China, Taiwan, Mexico, Thailand, Vietnam, South Korea (the six from the handover).
- **Months:** January 2024 to the latest loaded month.
- **Legs:** the delivery into the US only (same as Case 1).

## 4. Windows

The same illustrative windows as Case 1, since the tariff timeline is shared:

| Window | Months | Rests on |
|---|---|---|
| Baseline | 2024-01 to 2025-01 | 12 months before EO 14194 (February 1, 2025) |
| Anticipation | 2025-02 to 2025-04 | Mexico duty through reciprocal tariff announcement |
| Response | 2025-05 to 2025-12 | Post-announcement through end of 2025 |

## 5. Data

The notebook reads the same `core` tables as the other case notebooks:

- `fct_imports_monthly` — monthly imports by hs10 × country × mode
- `dim_country`, `dim_hs` — dimensions
- `fct_node_weights_monthly` — node weights for distance averaging
- `seed_sea_distances`, `seed_air_distances`, `seed_road_distances`, `seed_rail_distances`
- `ref_emission_factors` — UK DESNZ and EPA GHG Hub factors

## 6. Notebook outline

| Section | Contents |
|---|---|
| 1. Setup | Product groups, windows, imports |
| 2. Monthly supply | Tonnes by origin with window shading; compressors and steel separately |
| 3. Origin shares | Share of tonnage per window, change from baseline |
| 4. By HS family | Per-family origin-share comparison; validates or weakens the steel candidate |
| 5. Lane intensities | Emissions per tonne by origin × mode |
| 6. Supply mix | Monthly emissions per tonne, central and Mexico range |
| 7. Decomposition | Shapley: origin mix vs mode vs legs |
| 8. Results at a glance | Three summary charts |
| 9. Findings | DERIVED statements, candidate caveat, company-attribution caveat |

## 7. Input files

| File | Contents |
|---|---|
| `shock_windows.yaml` | Three windows (baseline, anticipation, response) |
| `evidence.yaml` | FACT records for tariff events; INFERENCE for GE/Haier context |
| `evidence_derived.yaml` | Generated by the notebook |
| `causal_labels.proposed.yaml` | Proposed by the notebook after analysis |

## 8. Open questions

1. **Steel candidate 721934.** The handover marks it REVIEW_REQUIRED. The per-family comparison in the notebook (Section 4) is part of the evidence needed to validate it. Classification evidence connecting 721934 to refrigerator cabinet sheet is required before reporting.
2. **Section 232 steel duties.** HS 721934 (primary steel sheet) was likely already subject to the 2018 Section 232 steel tariffs (Proclamation 9705). Verify against the HTSUS treatment before finalising the evidence file.
3. **Mexico overland data.** If BTS TransBorder has no truck/rail entries for HS 841430, Mexico overland tonnage is negligible and any break-even analysis is empty.
4. **Future HS families.** The handover lists electronics and resins/plastics as HOLD with no approved HS families. Do not add them to `config/hs_codes.yaml` until reviewed — the system loads every configured prefix.

## 9. Verification

- `uv run shockt ref config-seeds` regenerates the seed; `test_committed_config_seeds_match_their_generator` enforces it.
- `uv run ruff check . && uv run ruff format --check . && uv run pytest` in each context.
- The Census data load and dbt build require credentials; commands are in `data-pipelines/README.md`.
- Run the notebook after loading data and verify the supply rows match `fct_imports_monthly` for the two HS families.
