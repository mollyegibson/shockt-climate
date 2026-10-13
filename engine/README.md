# engine

The ShockT Climate emissions engine: pure functions with plain values in and out, and no database access. Notebooks import it today; later the engine runs the same functions to write the `outputs` schema. See the [Case 1 analysis plan](../docs/plans/case-1-analysis.md) and the [architecture](../docs/domain-driven-design.md).

| Module | Holds |
|---|---|
| `shockt_engine.factors` | Which emission factor each mode uses (`config/leg_factors.yaml`), applied to the factors in `core.ref_emission_factors` |
| `shockt_engine.shares` | Shares, share changes, diversion rates and window summaries |
| `shockt_engine.emissions` | Leg distances averaged over node pairs, and emissions per tonne of a lane and of a supply mix |

`config/leg_factors.yaml` names each mode's factor by its attributes (`vehicle_type`, `size_class`, `haul`, `radiative_forcing`); `select_factors` fails if a mode matches no factor or several.

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
