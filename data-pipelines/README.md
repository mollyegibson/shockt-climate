# data-pipelines

Ingestion pipelines and dbt models that build the `raw` and `core` layers of the ShockT Climate database. Design: [../docs/plans/data-ingestion-pipelines.md](../docs/plans/data-ingestion-pipelines.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs the Python version pinned in `.python-version`.

```sh
cd data-pipelines
uv sync
cp .env.example .env   # then fill in the three database URLs and the API settings
```

Values in `.env` take priority over variables exported in your shell, so a `DATABASE_URL` set for other work doesn't redirect this project. Without a `.env` (e.g. in CI), environment variables are used.

For a local database, start Postgres with `docker compose up -d` and set all three database URLs to the local URL shown in `.env.example`.

## Archive bucket

Every downloaded source file is archived in Neon Object Storage (S3-compatible) before it's parsed. One-time setup on the `main` branch:

1. In the Neon console, open the project's Object storage tab and create the bucket named in `ARCHIVE_BUCKET` (default `shockt-raw-archive`).
2. Create a credential on `main`. Put its `token_id` in `NEON_S3_ACCESS_KEY_ID` and its `s3_secret_access_key` in `NEON_S3_SECRET_ACCESS_KEY`; Neon shows the secret only once.
3. Set `NEON_S3_ENDPOINT_URL` to `main`'s storage endpoint (`https://br-<branch>-<hash>.storage.<cell>.us-east-2.aws.neon.tech`).

## Migrations

Alembic manages the `raw` schema, the load manifest, group roles and grants.

```sh
uv run alembic upgrade head          # apply
uv run alembic upgrade head --sql    # print the SQL without connecting
uv run alembic downgrade -1          # roll back one migration
```


| Group role | Access |
|---|---|
| `shockt_ingest` | Reads and writes `raw` |
| `shockt_transform` | Reads `raw`, creates `raw.seed_*` and builds `core` (dbt) |
| `shockt_analyst` | Reads `raw` and `core` |
| `shockt_app` | Reads `core` |

## Layout

```
config/       source settings and case HS codes
migrations/   Alembic migrations for raw, roles and grants
src/shockt/   Python package (CLI and loaders to come)
```
