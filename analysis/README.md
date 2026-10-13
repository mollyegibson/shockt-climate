# analysis

Notebooks for the case studies. They read `core` with the read-only analyst login, compute with the engine (`../engine`), and write draft input files under `../inputs/`. See the [Case 1](../docs/plans/case-1-analysis.md) and [Case 2](../docs/plans/case-2-analysis.md) analysis plans.

| Path | Holds |
|---|---|
| `src/shockt_analysis/core.py` | The only module that reads the database: `core`, the distance seeds and the load manifest, into data frames |
| `src/shockt_analysis/cases.py` | The steps the notebooks share: supply by window, shares, lane inputs and emissions per tonne, the supply mix and the derived evidence records |
| `src/shockt_analysis/case2.py` | Case 2's own steps: shock windows from chokepoint transits, which lanes use which passage, coast-of-arrival lanes and the supply mix's cells |
| `case1/case1_tariffs_2025.ipynb` | The Case 1 notebook |
| `case2/case2_panama_red_sea.ipynb` | The Case 2 notebook |

## Setup

```sh
cp .env.example .env        # then set ANALYST_DATABASE_URL (read-only shockt_analyst login)
uv sync
uv run jupyter lab          # open a notebook under case1/ or case2/
```

To run a notebook top to bottom without opening it:

```sh
uv run jupyter nbconvert --to notebook --execute --inplace case1/case1_tariffs_2025.ipynb
```

Lint and test before pushing:

```sh
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
