# data-pipelines

Ingestion pipelines and dbt models that build the `raw` and `core` layers of the ShockT Climate database. Design: [../docs/plans/data-ingestion-pipelines.md](../docs/plans/data-ingestion-pipelines.md).

## Local setup

1. **Install uv** (`brew install uv`, or see the [uv docs](https://docs.astral.sh/uv/getting-started/installation/)). uv installs the Python version this project pins.
2. **Install the dependencies:**
  ```sh
   cd data-pipelines
   uv sync
   cp .env.example .env
  ```
3. **Ask Molly for the credentials** and paste them into `.env`. The team shares one login per database role, so everyone uses the same values:

  | Variable                                                                     | What it is                                                          |
  | ---------------------------------------------------------------------------- | ------------------------------------------------------------------- |
  | `DATABASE_URL`                                                               | Postgres connection string for `shockt_ingest`, used by the loaders |
  | `DBT_DATABASE_URL`                                                           | Postgres connection string for `shockt_transform`, used by dbt      |
  | `NEON_S3_ENDPOINT_URL`, `NEON_S3_ACCESS_KEY_ID`, `NEON_S3_SECRET_ACCESS_KEY` | The archive bucket where loaders store every downloaded file        |

   Keep `NEON_S3_REGION` and `ARCHIVE_BUCKET` as they are in `.env.example`.
4. **Get a Census API key** at [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html) and set `CENSUS_API_KEY`. It's free; click the activation link in the email before using it, and allow a few minutes for it to take effect.
5. **Check the setup** by listing recent loads:
  ```sh
   uv run shockt loads list
  ```

`.env` is gitignored. Never commit it, and don't paste credentials into chat or issues.

Values in `.env` take priority over variables exported in your shell, so a `DATABASE_URL` or `AWS_PROFILE` you use for other work won't redirect this project.

**Analysts** working only in notebooks don't need this setup. Ask Molly for the read-only `shockt_analyst` connection string instead.

### Database roles


| Role               | Access                                                    |
| ------------------ | --------------------------------------------------------- |
| `shockt_ingest`    | Reads and writes `raw`                                    |
| `shockt_transform` | Reads `raw`, creates `raw.seed_*` and builds `core` (dbt) |
| `shockt_analyst`   | Reads `raw` and `core`                                    |
| `shockt_app`       | Reads `core`                                              |




## Migrations

Alembic manages the `raw` schema, the load manifest, roles and grants. Migrations run as the database owner (`MIGRATIONS_DATABASE_URL`), so Molly applies them; open a pull request with the new migration and ask her to run it.

```sh
uv run alembic upgrade head          # apply
uv run alembic upgrade head --sql    # print the SQL without connecting
```



## Loading data

Loaders connect as `shockt_ingest` (`DATABASE_URL`), archive each response in the bucket, then
parse it into `raw`. Reloading a month replaces its earlier load.

```sh
uv run shockt ingest census --from 2022-01                  # all three endpoints, through the latest month
uv run shockt ingest census -d hs --from 2024-12 --to 2024-12
uv run shockt ingest census --from 2022-01 --skip-existing   # resume after a failure
uv run shockt ingest census --from 2022-01 --from-archive    # re-parse archived responses, e.g. after a filter change
uv run shockt loads list                                     # recent loads and raw table sizes
```

BTS TransBorder data can't be downloaded by script (bts.gov blocks it), so download each month's ZIP from the [raw data page](https://www.bts.gov/topics/transborder-raw-data) in a browser into `data/manual/bts/`, unchanged. File names don't matter; the loader reads the month from the files inside. It reports any ZIP it can't read, which usually means the download was cut short.

```sh
uv run shockt ingest bts-transborder                  # every month in data/manual/bts
uv run shockt ingest bts-transborder --skip-existing  # only months not loaded yet
uv run shockt ingest bts-transborder --from-archive   # re-parse archived ZIPs, e.g. after a filter change
```

IMF PortWatch daily chokepoint transits come from a public API, one chokepoint-year per load. The current year is always reloaded, since PortWatch keeps adding days:

```sh
uv run shockt ingest portwatch                       # all configured chokepoints, config start year to now
uv run shockt ingest portwatch --skip-existing       # only the current year and anything not yet loaded
```

Climate TRACE ship voyages come from its public BigQuery dataset, one year per load, billed to your sandbox project (`GCP_PROJECT_ID`, after `gcloud auth application-default login`). Every query is dry-run first and refused above `BQ_MAX_BYTES`; the full 2022-onward load scans about 30 GB of the free 1 TB a month:

```sh
uv run shockt ingest climatetrace-voyages --dry-run        # bytes each year would scan; no quota used
uv run shockt ingest climatetrace-voyages                  # load every year from the config start
uv run shockt ingest climatetrace-voyages --from-archive   # re-parse archived Parquet; no quota used
```

Rows dropped while loading (country groups, all-zero rows, and for the port and state
endpoints, countries outside Asia and Mexico) are set in `config/sources.yaml` and recorded in
each load's manifest `params`.

## Building `core`

dbt builds the `core` schema from `raw`, connecting as `shockt_transform` (`DBT_DATABASE_URL`). Run it after loading data; it reads only succeeded loads, so it's safe to run while a load is in progress.

```sh
uv run shockt build                               # install dbt packages, load seeds, build models, run tests
uv run shockt dbt build -s fct_imports_monthly    # any dbt command, e.g. one model
uv run shockt dbt test                            # tests only
```

Seeds (reference CSVs) live in `dbt/seeds/` and load into `raw.seed_*`. `seed_emission_factors.csv` is generated from the official UK and EPA factor workbooks, which are archived in the bucket; regenerate it when either publishes a new edition:

```sh
uv run shockt ref emission-factors
```

 `seed_port_regions.csv` assigns each port a coast region by customs district; review it before relying on port-level results.

## Tests

```sh
uv run pytest
```

Integration tests need `TEST_DATABASE_URL`, a superuser URL for a throwaway database; they're skipped without it. Never point it at Neon: the tests reset the schema. With Docker running:

```sh
docker compose up -d
TEST_DATABASE_URL=postgresql://shockt:shockt@localhost:5432/shockt uv run pytest
```



## Layout

```
config/       source settings and case HS codes
dbt/          dbt project: seeds, staging views (core_staging) and core tables
migrations/   Alembic migrations for raw, roles and grants
src/shockt/   Python package: CLI, archive, manifest and source loaders
tests/        unit and integration tests, with fixtures from real responses
```

