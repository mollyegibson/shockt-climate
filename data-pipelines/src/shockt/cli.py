import time
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Annotated

import httpx
import typer

from shockt import dbt, http, manifest
from shockt.archive import NeonArchive, object_key
from shockt.config import hs_codes_config, sources_config
from shockt.db import connect
from shockt.http import make_client
from shockt.loading import ParsedSource, Target
from shockt.reference import census_schedules, config_seeds, emission_factors
from shockt.settings import PROJECT_ROOT, get_settings
from shockt.sources import (
    bts_transborder,
    census_api,
    census_concordance,
    climatetrace,
    denue,
    portwatch,
    reference,
)

app = typer.Typer(no_args_is_help=True, help="ShockT Climate ingestion pipelines.")
ingest_app = typer.Typer(no_args_is_help=True, help="Fetch a source into the raw schema.")
loads_app = typer.Typer(no_args_is_help=True, help="Inspect raw.load_manifest.")
app.add_typer(ingest_app, name="ingest")
app.add_typer(loads_app, name="loads")
ref_app = typer.Typer(no_args_is_help=True, help="Generate reference seeds in dbt/seeds/.")
app.add_typer(ref_app, name="ref")


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
        bool, typer.Option(help="Skip month × HS prefix partitions that already have a load.")
    ] = False,
    from_archive: Annotated[
        bool, typer.Option(help="Re-parse archived responses instead of calling the API.")
    ] = False,
) -> None:
    """Load Census International Trade API imports for the case HS codes, one partition per
    month × HS prefix."""
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
                for prefix in (p.prefix for p in hs_codes.prefixes):
                    key = census_api.partition_key(month, prefix)
                    if key in done:
                        typer.echo(f"{spec.manifest_dataset} {key}: skipped (already loaded)")
                        continue
                    started = time.monotonic()

                    fetch = partial(
                        census_api.fetch_bundle,
                        client,
                        spec,
                        month,
                        prefix,
                        config.census_api,
                        api_key,
                    )
                    result = census_api.load_month(
                        conn,
                        archive,
                        spec,
                        month,
                        prefix,
                        None if from_archive else fetch,
                        config.census_api.filters[spec.endpoint],
                    )
                    note = " (replaced earlier load)" if result.superseded_load_id else ""
                    typer.echo(
                        f"{spec.manifest_dataset} {key}: {result.row_count:,} rows kept "
                        f"in {time.monotonic() - started:.1f}s{note}"
                    )


@ingest_app.command("bts-transborder")
def ingest_bts_transborder(
    from_dir: Annotated[
        Path | None,
        typer.Option(help="Folder of downloaded monthly ZIPs. Default: manual_dir in config."),
    ] = None,
    start: Annotated[str | None, typer.Option("--from", help="First month, YYYY-MM.")] = None,
    end: Annotated[str | None, typer.Option("--to", help="Last month, YYYY-MM.")] = None,
    skip_existing: Annotated[
        bool, typer.Option(help="Skip months that already have a succeeded load.")
    ] = False,
    from_archive: Annotated[
        bool, typer.Option(help="Re-parse archived ZIPs instead of reading the folder.")
    ] = False,
) -> None:
    """Load BTS TransBorder dot2 and dot3 tables from monthly ZIPs downloaded from bts.gov."""
    settings = get_settings()
    config = sources_config().bts_transborder
    archive = NeonArchive(settings)
    failures: list[str] = []

    def in_range(month: str) -> bool:
        return (start is None or month >= start) and (end is None or month <= end)

    with connect(settings) as conn:
        if from_archive:
            files: dict[str, bts_transborder.MonthFile | None] = dict.fromkeys(
                manifest.archived_partitions(conn, bts_transborder.DATASET)
            )
        else:
            directory = from_dir or PROJECT_ROOT / config.manual_dir
            scanned, failures = bts_transborder.scan_dir(directory, config.tables)
            files = dict(scanned)
            typer.echo(f"{len(scanned)} months found in {directory}")
        done = (
            manifest.succeeded_partitions(conn, bts_transborder.DATASET) if skip_existing else set()
        )
        for month in sorted(m for m in files if in_range(m)):
            if month in done:
                typer.echo(f"{bts_transborder.DATASET} {month}: skipped (already loaded)")
                continue
            month_file = files[month]
            started = time.monotonic()
            try:
                result = bts_transborder.load_month(
                    conn,
                    archive,
                    month,
                    month_file.path.read_bytes if month_file else None,
                    config,
                    original_filename=month_file.path.name if month_file else None,
                )
            except Exception as exc:
                failures.append(f"{month}: {type(exc).__name__}: {exc}")
                typer.echo(f"{bts_transborder.DATASET} {month}: FAILED ({exc})")
                continue
            note = " (replaced earlier load)" if result.superseded_load_id else ""
            typer.echo(
                f"{bts_transborder.DATASET} {month}: {result.row_count:,} rows kept "
                f"in {time.monotonic() - started:.1f}s{note}"
            )
    if failures:
        typer.echo(f"\n{len(failures)} problem(s):")
        for failure in failures:
            typer.echo(f"  {failure}")
        raise typer.Exit(1)


@ingest_app.command("portwatch")
def ingest_portwatch(
    start: Annotated[
        int | None, typer.Option("--from", help="First year. Default: config start.")
    ] = None,
    end: Annotated[int | None, typer.Option("--to", help="Last year. Default: this year.")] = None,
    chokepoint: Annotated[
        list[str] | None,
        typer.Option(help="PortWatch portid, e.g. chokepoint2; repeat for several. Default: all."),
    ] = None,
    skip_existing: Annotated[
        bool,
        typer.Option(help="Skip loaded chokepoint-years. The current year is always reloaded."),
    ] = False,
    from_archive: Annotated[
        bool, typer.Option(help="Re-parse archived responses instead of calling PortWatch.")
    ] = False,
) -> None:
    """Load IMF PortWatch daily transits for the configured chokepoints, one year at a time."""
    settings = get_settings()
    config = sources_config()
    portwatch_config = config.portwatch
    unknown = sorted(set(chokepoint or []) - set(portwatch_config.chokepoints))
    if unknown:
        raise typer.BadParameter(f"not in config: {', '.join(unknown)}", param_hint="--chokepoint")
    portids = chokepoint or list(portwatch_config.chokepoints)
    this_year = date.today().year
    years = range(start or int(config.date_range.start_month[:4]), (end or this_year) + 1)
    archive = NeonArchive(settings)

    with make_client(timeout_seconds=120) as client, connect(settings) as conn:
        data_edited = None if from_archive else portwatch.data_last_edited(client, portwatch_config)
        done = manifest.succeeded_partitions(conn, portwatch.DATASET) if skip_existing else set()
        for portid in portids:
            for year in years:
                key = portwatch.partition_key(portid, year)
                if key in done and year != this_year:
                    typer.echo(f"{portwatch.DATASET} {key}: skipped (already loaded)")
                    continue
                started = time.monotonic()
                fetch = (
                    None
                    if data_edited is None
                    else partial(
                        portwatch.fetch_bundle, client, portwatch_config, portid, year, data_edited
                    )
                )
                result = portwatch.load_year(conn, archive, portid, year, fetch)
                note = " (replaced earlier load)" if result.superseded_load_id else ""
                typer.echo(
                    f"{portwatch.DATASET} {key} ({portwatch_config.chokepoints[portid]}): "
                    f"{result.row_count:,} days in {time.monotonic() - started:.1f}s{note}"
                )


@ingest_app.command("climatetrace-voyages")
def ingest_climatetrace_voyages(
    start: Annotated[
        int | None, typer.Option("--from", help="First year. Default: config start.")
    ] = None,
    end: Annotated[int | None, typer.Option("--to", help="Last year. Default: this year.")] = None,
    dry_run: Annotated[
        bool, typer.Option(help="Print the bytes each year would scan; load nothing.")
    ] = False,
    skip_existing: Annotated[
        bool, typer.Option(help="Skip loaded years. The current year is always reloaded.")
    ] = False,
    from_archive: Annotated[
        bool, typer.Option(help="Re-parse archived Parquet instead of querying BigQuery.")
    ] = False,
) -> None:
    """Load Climate TRACE ship voyages on the configured lanes from BigQuery, one year at a time."""
    settings = get_settings()
    config = sources_config()
    this_year = date.today().year
    years = range(start or int(config.date_range.start_month[:4]), (end or this_year) + 1)
    runner: climatetrace.BigQueryRunner | None = None
    if not from_archive:
        if settings.gcp_project_id is None:
            raise typer.BadParameter("GCP_PROJECT_ID is not set")
        runner = climatetrace.GoogleBigQueryRunner(settings.gcp_project_id)

    if dry_run:
        if runner is None:
            raise typer.BadParameter("--dry-run queries BigQuery; drop --from-archive")
        total = 0
        for year in years:
            estimate = climatetrace.estimate_bytes(runner, config.climatetrace, year)
            total += estimate
            typer.echo(f"{climatetrace.DATASET} {year}: would scan {estimate / 1e9:.1f} GB")
        typer.echo(
            f"total {total / 1e9:.1f} GB; cap per query (BQ_MAX_BYTES) "
            f"{settings.bq_max_bytes / 1e9:.0f} GB"
        )
        return

    archive = NeonArchive(settings)
    with connect(settings) as conn:
        done = manifest.succeeded_partitions(conn, climatetrace.DATASET) if skip_existing else set()
        for year in years:
            if str(year) in done and year != this_year:
                typer.echo(f"{climatetrace.DATASET} {year}: skipped (already loaded)")
                continue
            started = time.monotonic()
            fetch = (
                None
                if runner is None
                else partial(
                    climatetrace.fetch_year,
                    runner,
                    config.climatetrace,
                    year,
                    settings.bq_max_bytes,
                )
            )
            result = climatetrace.load_year(conn, archive, config.climatetrace, year, fetch)
            note = " (replaced earlier load)" if result.superseded_load_id else ""
            typer.echo(
                f"{climatetrace.DATASET} {year}: {result.row_count:,} voyages "
                f"in {time.monotonic() - started:.1f}s{note}"
            )


def _load_reference(
    target: Target,
    url: str,
    filename: str,
    content_type: str,
    params: dict[str, object],
    parse: Callable[[bytes], ParsedSource],
    from_archive: bool,
    fetch: Callable[[httpx.Client], bytes] | None = None,
) -> None:
    settings = get_settings()
    archive = NeonArchive(settings)
    started = time.monotonic()
    with make_client(timeout_seconds=300) as client, connect(settings) as conn:
        version = None if from_archive else reference.last_modified(client, url)

        def download(c: httpx.Client) -> bytes:
            return http.get(c, url, {}).content

        obtain = None if from_archive else partial(fetch or download, client)
        result = reference.load(
            conn, archive, target, filename, content_type, params, obtain, parse, version
        )
    note = " (replaced earlier load)" if result.superseded_load_id else ""
    typer.echo(
        f"{target.dataset}: {result.row_count:,} rows in {time.monotonic() - started:.1f}s{note}"
    )


ARCHIVE_OPTION = typer.Option(help="Re-parse the archived download instead of fetching it.")


@ingest_app.command("ourairports")
def ingest_ourairports(from_archive: Annotated[bool, ARCHIVE_OPTION] = False) -> None:
    """Load OurAirports airports with an IATA code."""
    config = sources_config().reference_sources.ourairports
    _load_reference(
        reference.OURAIRPORTS,
        config.url,
        "airports.csv",
        "text/csv",
        {"filter": "iata_code is not empty"},
        reference.parse_ourairports,
        from_archive,
    )


@ingest_app.command("geonames-cities")
def ingest_geonames_cities(from_archive: Annotated[bool, ARCHIVE_OPTION] = False) -> None:
    """Load GeoNames cities (population 5,000 and over) in the configured countries."""
    config = sources_config().reference_sources.geonames_cities
    _load_reference(
        reference.GEONAMES,
        config.url,
        "cities5000.zip",
        "application/zip",
        {"countries": config.countries, "dropped_columns": ["alternatenames"]},
        partial(reference.parse_geonames, config=config),
        from_archive,
    )


@ingest_app.command("bts-border-crossings")
def ingest_bts_border_crossings(from_archive: Annotated[bool, ARCHIVE_OPTION] = False) -> None:
    """Load BTS Border Crossing Entry Data for the configured border, from the start month."""
    config = sources_config()
    crossings = config.reference_sources.bts_border_crossings
    start_month = config.date_range.start_month
    _load_reference(
        reference.BORDER_CROSSINGS,
        crossings.url,
        "border_crossings.json",
        "application/json",
        {"border": crossings.border, "from_month": start_month},
        reference.parse_border_crossings,
        from_archive,
        fetch=partial(reference.fetch_border_crossings, config=crossings, start_month=start_month),
    )


@ingest_app.command("census-concordance")
def ingest_census_concordance(
    years: Annotated[
        list[int] | None,
        typer.Option("--year", help="Repeat for several. Default: start year through this year."),
    ] = None,
    from_archive: Annotated[bool, ARCHIVE_OPTION] = False,
) -> None:
    """Load the Census import concordance (HS-10 to NAICS), one workbook per year."""
    config = sources_config()
    concordance = config.reference_sources.census_import_concordance
    first = int(config.date_range.start_month[:4])
    settings = get_settings()
    archive = NeonArchive(settings)
    with make_client(timeout_seconds=300) as client, connect(settings) as conn:
        for year in years or range(first, date.today().year + 1):
            started = time.monotonic()
            url = census_concordance.url(concordance, year)
            version = None if from_archive else reference.last_modified(client, url)

            def download(u: str = url) -> bytes:
                return http.get(client, u, {}).content

            result = census_concordance.load_year(
                conn, archive, concordance, year, None if from_archive else download, version
            )
            note = " (replaced earlier load)" if result.superseded_load_id else ""
            typer.echo(
                f"{census_concordance.DATASET} {year}: {result.row_count:,} commodities "
                f"in {time.monotonic() - started:.1f}s{note}"
            )


@ingest_app.command("denue")
def ingest_denue(from_archive: Annotated[bool, ARCHIVE_OPTION] = False) -> None:
    """Load DENUE establishments in the industries the case HS codes map to."""
    config = sources_config().reference_sources.denue
    prefixes = [p.prefix for p in hs_codes_config().prefixes]
    settings = get_settings()
    archive = NeonArchive(settings)
    started = time.monotonic()
    with make_client(timeout_seconds=600) as client, connect(settings) as conn:
        version = None if from_archive else reference.last_modified(client, config.url)

        def download() -> bytes:
            return http.get(client, config.url, {}).content

        result = denue.load(
            conn, archive, config, prefixes, None if from_archive else download, version
        )
    note = " (replaced earlier load)" if result.superseded_load_id else ""
    typer.echo(
        f"{denue.DATASET}: {result.row_count:,} establishments "
        f"in {time.monotonic() - started:.1f}s{note}"
    )


@ref_app.command("config-seeds")
def ref_config_seeds() -> None:
    """Write seed_hs_case_codes.csv from config/."""
    seeds = dbt.DBT_DIR / "seeds"
    n = config_seeds.write_hs_case_codes(hs_codes_config(), seeds / "seed_hs_case_codes.csv")
    typer.echo(f"seed_hs_case_codes.csv: {n} HS prefixes from config/hs_codes.yaml")


@ref_app.command("census-schedules")
def ref_census_schedules() -> None:
    """Download and archive Census Schedules C and D; write the country and port seeds."""
    settings = get_settings()
    config = sources_config().census_schedules
    archive = NeonArchive(settings)
    fetched = date.today().isoformat()
    bodies: dict[str, bytes] = {}
    with make_client(timeout_seconds=120) as client:
        for name, url in (
            ("schedule_c", config.schedule_c_url),
            ("schedule_d", config.schedule_d_url),
        ):
            body = http.get(client, url, {}).content
            key = object_key(f"reference_census_{name}", fetched, url.rsplit("/", 1)[-1])
            archive.put(key, body, "text/plain")
            typer.echo(f"{name}: {len(body):,} bytes archived at {key}")
            bodies[name] = body
    seeds = dbt.DBT_DIR / "seeds"
    countries = census_schedules.parse_schedule_c(bodies["schedule_c"].decode("utf-8", "replace"))
    census_schedules.write_countries(
        countries, seeds / "seed_census_countries.csv", f"Census Schedule C, fetched {fetched}"
    )
    ports = census_schedules.parse_schedule_d(bodies["schedule_d"].decode("utf-8", "replace"))
    census_schedules.write_ports(
        ports, seeds / "seed_census_ports.csv", f"Census Schedule D, fetched {fetched}"
    )
    missing_iso3 = [c.census_code for c in countries if c.iso2 and not c.iso3]
    typer.echo(
        f"seed_census_countries.csv: {len(countries)} countries; ISO2 without ISO3: {missing_iso3}"
    )
    typer.echo(f"seed_census_ports.csv: {len(ports)} ports")


@ref_app.command("emission-factors")
def ref_emission_factors() -> None:
    """Download and archive the UK and EPA factor workbooks; write seed_emission_factors.csv."""
    settings = get_settings()
    sources = sources_config().emission_factors
    archive = NeonArchive(settings)
    workbooks: dict[str, bytes] = {}
    with make_client(timeout_seconds=120) as client:
        for name, source in (("uk_desnz", sources.uk), ("epa_hub", sources.epa)):
            body = http.get(client, source.url, {}).content
            key = object_key(
                f"reference_{name}", source.version.split()[0], source.url.rsplit("/", 1)[-1]
            )
            digest = archive.put(key, body, "application/vnd.ms-excel")
            typer.echo(f"{name}: {len(body):,} bytes archived at {key} (sha256 {digest[:12]})")
            workbooks[name] = body
    rows = emission_factors.build_seed_rows(
        emission_factors.read_uk_rows(workbooks["uk_desnz"]),
        emission_factors.read_epa_factors(workbooks["epa_hub"]),
        uk_version=sources.uk.version,
        epa_version=sources.epa.version,
    )
    path = dbt.DBT_DIR / "seeds" / "seed_emission_factors.csv"
    emission_factors.write_seed(rows, path)
    typer.echo(f"Wrote {len(rows)} factors to {path.relative_to(PROJECT_ROOT)}")
    for row in rows:
        typer.echo(f"  {row.factor_id:32} {row.ttw + row.wtt:.4f} kg CO2e/tkm well-to-wheel")


@app.command()
def build() -> None:
    """Install dbt packages, then seed, build and test the core schema."""
    settings = get_settings()
    if not (dbt.DBT_DIR / "dbt_packages").exists() and not dbt.run(settings, ["deps"]):
        raise typer.Exit(1)
    if not dbt.run(settings, ["build"]):
        raise typer.Exit(1)


@app.command("dbt", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def dbt_command(ctx: typer.Context) -> None:
    """Run any dbt command, e.g. `shockt dbt test -s fct_imports_monthly`."""
    if not dbt.run(get_settings(), list(ctx.args)):
        raise typer.Exit(1)


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
