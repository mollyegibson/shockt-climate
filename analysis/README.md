# analysis

Notebooks for the case studies. They read `core` with the read-only analyst login, compute with the engine (`../engine`), and write draft input files under `../inputs/`. See the [Case 1 analysis plan](../docs/plans/case-1-analysis.md).

| Path | Holds |
|---|---|
| `src/shockt_analysis/core.py` | The only module that reads the database: `core`, the distance seeds and the load manifest, into data frames |
| `src/shockt_analysis/case1.py` | Case 1's steps: supply by window, shares, lane emissions per tonne, the supply mix and the derived evidence records |
| `case1/case1_tariffs_2025.ipynb` | The Case 1 notebook |

## Setup

```sh
cp .env.example .env        # then set ANALYST_DATABASE_URL (read-only shockt_analyst login)
uv sync
uv run jupyter lab          # open case1/case1_tariffs_2025.ipynb
```

To run a notebook top to bottom without opening it:

```sh
uv run jupyter nbconvert --to notebook --execute --inplace case1/case1_tariffs_2025.ipynb
```

Lint and test before pushing:

```sh
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
