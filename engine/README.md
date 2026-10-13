# engine

The ShockT Climate emissions engine: pure functions with plain values in and out, and no database access. Notebooks import it today; later the engine runs the same functions to write the `outputs` schema. See the [Case 1](../docs/plans/case-1-analysis.md) and [Case 2](../docs/plans/case-2-analysis.md) analysis plans and the [architecture](../docs/domain-driven-design.md).

| Module | Holds |
|---|---|
| `shockt_engine.factors` | Which emission factor each mode uses (`config/leg_factors.yaml`), applied to the factors in `core.ref_emission_factors` |
| `shockt_engine.shares` | Shares, share changes, diversion rates and window summaries |
| `shockt_engine.emissions` | Leg distances averaged over node pairs, and emissions per tonne of a lane and of a supply mix |
| `shockt_engine.lanes` | The legs of a lane in each delivery mode, and its emissions per tonne |
| `shockt_engine.shocks` | Shock windows as runs of months outside a baseline range, and whether a route uses a passage |
| `shockt_engine.decomposition` | A supply mix's change in emissions per tonne, split between its dimensions and the lanes' intensities (Shapley values) |

`config/leg_factors.yaml` names each mode's factor by its attributes (`vehicle_type`, `size_class`, `haul`, `radiative_forcing`); `select_factors` fails if a mode matches no factor or several.

Build, lint, and test before pushing:
```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
