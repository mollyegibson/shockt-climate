# Ubiquitous Language

The agreed vocabulary for ShockT Climate. If a term is here, code and docs spell it this way. If the code needs a term that isn't here, add a row in the same PR.

## Shocks and analysis

| Term | Meaning |
|---|---|
| **Case** | One case study (e.g. 2025 tariffs; Panama and Red Sea 2023–24). A case has one baseline and one or more shocks. |
| **Shock** | A dated event that disrupted a supply chain: a policy shock (tariff) or a physical and climate shock (drought, conflict). |
| **Shock window** | A month range of a fixed type: `baseline`, `anticipation`, `effective` or `response`. Windows are whole calendar months. |
| **Causal label** | How strongly the team links an observed response to a shock, using the Shock-T vocabulary (`DIRECT_CAUSAL`, `CONTRIBUTING_FACTOR`, `TEMPORAL_ALIGNMENT`, …). |
| **Evidence** | A record that lets a reader check a claim. Its **basis** is `FACT` (a source says it), `DERIVED` (computed by an engine metric) or `INFERENCE` (the team's reasoning). |
| **Metric** | A named, tested function in the engine package that DERIVED evidence references, e.g. `air_share_by_weight`. |

## Shipments and emissions

| Term | Meaning |
|---|---|
| **Lane** | An origin-to-destination route, e.g. TW-US, Asia → US East Coast. |
| **Leg** | One mode-specific segment of a lane, door to door. A lane's emissions are the sum of its legs. |
| **Cell** | A slice of tonnage by origin × US port region × mode. |
| **Coast region** | The region of a US port of entry, by customs district: `east`, `west`, `gulf`, `border_north`, `border_south`, `inland`, `noncontiguous`, `other`. The calculator's port regions are East, West and Gulf. |
| **Mode** | `air`, `vessel` (with `vessel_containerized` as a subset), `other` (general imports value minus air and vessel; overland for Mexico and Canada, no Census weight), and later `truck` and `rail` from BTS TransBorder. |
| **Diversion rate** | The fraction of one category's tonnage that moved to another in a window: (s_to,response − s_to,baseline) / s_from,baseline. |
| **Market response** | A case's diversion rates applied to a user's tonnage, in a fixed order: origin, then port region, then mode. Shown as one row. |
| **Alternative** | A lever the user controls (e.g. land West Coast + rail), shown as its own row. |
| **Carbon Delta** | Market response minus baseline (positive = **amplified**), and alternative minus market response (negative = **avoided**). **Displaced** emissions move between legs or Scope 3 categories and are reported separately. |
| **Per-tonne intensity** | Emissions per tonne for one cell under the baseline, a market response or an alternative, precomputed by the engine. |

## Data platform

| Term | Meaning |
|---|---|
| **raw / core / inputs / outputs** | The four database layers: data as fetched; cleaned models; the team's analytical decisions; engine results. |
| **Load** | One fetch of one partition of one dataset, recorded as a row in `raw.load_manifest`. |
| **Partition** | The unit a load replaces, e.g. one month of one Census endpoint. |
| **Source version** | Which edition of a source a load came from, as the source exposes it (a release label, last-edited date, `Last-Modified` header or fetch time). Recorded in `raw.load_manifest.source_version`; the archived file's SHA-256 identifies the exact bytes. |
| **Superseded** | A load replaced by a newer load of the same partition; its rows are deleted, its manifest row kept. |
| **Archive** | The object storage bucket holding every downloaded source file, unchanged, at `raw/{dataset}/{partition}/{filename}`. |
| **Filter** | Rows dropped as a load is parsed, set in `config/sources.yaml` and recorded in the manifest `params`. |
| **HS-6 / HS-10** | International 6-digit Harmonized System code / US 10-digit extension. The Census port and state endpoints serve HS-6 at most. |
| **Concordance** | The Census import concordance: each year's mapping from HS-10 commodity to NAICS industry, SITC and end use. |
| **Case industries** | The industry codes (NAICS, cut to 5 digits, where Mexico's SCIAN agrees) that the concordance maps from the case HS codes; they select DENUE establishments. |
