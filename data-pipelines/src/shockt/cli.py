import time
from enum import StrEnum
from functools import partial
from typing import Annotated

import typer

from shockt import manifest
from shockt.archive import NeonArchive
from shockt.config import hs_codes_config, sources_config
from shockt.db import connect
from shockt.http import make_client
from shockt.settings import get_settings
from shockt.sources import census_api

app = typer.Typer(no_args_is_help=True, help="ShockT Climate ingestion pipelines.")
ingest_app = typer.Typer(no_args_is_help=True, help="Fetch a source into the raw schema.")
loads_app = typer.Typer(no_args_is_help=True, help="Inspect raw.load_manifest.")
app.add_typer(ingest_app, name="ingest")
app.add_typer(loads_app, name="loads")


class CensusEndpoint(StrEnum):
    hs = "hs"
    porths = "porths"
    statehs = "statehs"


@ingest_app.command("census")
def ingest_census(
    dataset: Annotated[
        list[CensusEndpoint] | None,
        typer.Option("--dataset", "-d", help="Repeat for several. Default: all three."),
    ] = None,
    start: Annotated[str | None, typer.Option("--from", help="First month, YYYY-MM.")] = None,
    end: Annotated[
        str | None, typer.Option("--to", help="Last month, YYYY-MM. Default: latest published.")
    ] = None,
    skip_existing: Annotated[
        bool, typer.Option(help="Skip months that already have a succeeded load.")
    ] = False,
    from_archive: Annotated[
        bool, typer.Option(help="Re-parse archived responses instead of calling the API.")
    ] = False,
) -> None:
    """Load Census International Trade API imports for the case HS codes, one month at a time."""
    endpoints = dataset or list(CensusEndpoint)
    settings = get_settings()
    if settings.census_api_key is None and not from_archive:
        raise typer.BadParameter("CENSUS_API_KEY is not set")
    api_key = settings.census_api_key.get_secret_value() if settings.census_api_key else ""
    config = sources_config()
    hs_codes = hs_codes_config()
    first = start or config.date_range.start_month

    with make_client(config.census_api.timeout_seconds) as client, connect(settings) as conn:
        archive = NeonArchive(settings)
        last = end or config.date_range.end_month
        if last is None:
            last = census_api.latest_month(client, config.census_api, api_key, since=first)
            typer.echo(f"Latest published month: {last}")
        months = census_api.month_range(first, last)

        for endpoint in endpoints:
            spec = census_api.DATASETS[endpoint.value]
            done = (
                manifest.succeeded_partitions(conn, spec.manifest_dataset)
                if skip_existing
                else set()
            )
            for month in months:
                if month in done:
                    typer.echo(f"{spec.manifest_dataset} {month}: skipped (already loaded)")
                    continue
                started = time.monotonic()

                fetch = partial(
                    census_api.fetch_bundle,
                    client,
                    spec,
                    month,
                    config.census_api,
                    hs_codes,
                    api_key,
                )
                result = census_api.load_month(
                    conn,
                    archive,
                    spec,
                    month,
                    None if from_archive else fetch,
                    config.census_api.filters[spec.endpoint],
                )
                note = " (replaced earlier load)" if result.superseded_load_id else ""
                typer.echo(
                    f"{spec.manifest_dataset} {month}: {result.row_count:,} rows kept "
                    f"in {time.monotonic() - started:.1f}s{note}"
                )


@loads_app.command("list")
def loads_list(
    dataset: Annotated[str | None, typer.Option("--dataset", "-d")] = None,
    limit: Annotated[int, typer.Option()] = 30,
) -> None:
    """Recent loads, newest first, and the size of each raw table."""
    with connect(get_settings()) as conn:
        rows = conn.execute(
            "SELECT dataset, partition_key, status, row_count, started_at, error "
            "FROM raw.load_manifest WHERE %(dataset)s::text IS NULL OR dataset = %(dataset)s "
            "ORDER BY started_at DESC LIMIT %(limit)s",
            {"dataset": dataset, "limit": limit},
        ).fetchall()
        for ds, partition, status, row_count, started_at, error in rows:
            count = f"{row_count:,}" if row_count is not None else "-"
            line = f"{started_at:%Y-%m-%d %H:%M}  {ds:24} {partition:10} {status:10} {count:>9}"
            typer.echo(line + (f"  {error[:80]}" if error else ""))
        sizes = conn.execute(
            "SELECT c.relname, pg_total_relation_size(c.oid) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'raw' AND c.relkind = 'r' ORDER BY 2 DESC"
        ).fetchall()
        total = sum(size for _, size in sizes)
        typer.echo(f"\nraw tables: {total / 1e6:,.1f} MB")
        for table, size in sizes:
            typer.echo(f"  {table:28} {size / 1e6:8,.1f} MB")


if __name__ == "__main__":
    app()
