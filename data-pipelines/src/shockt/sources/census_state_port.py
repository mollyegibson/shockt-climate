"""Census State/Port Imports: quarterly fixed-width files of imports by state of destination, port
of unlading, port of entry and country, for all goods (plan section 5.4).

One partition is one quarter. Each quarter's ZIP is archived unchanged, then its single data file
(`IQ953_{YYYY}_Q{N}.dat` until 2025, `ISTPORT{YY}Q{N}.TXT` from 2026) is parsed from the archived
copy, keeping the configured origins and states, and rows with air or vessel weight.
"""

import io
import zipfile
from collections.abc import Callable

import httpx
import psycopg

from shockt import http
from shockt.archive import Archive, object_key
from shockt.config import CensusStatePortConfig, CountryFilter
from shockt.loading import ParsedSource, Target, load_partition
from shockt.manifest import LoadResult

DATASET = "census_state_port"
LINE_LENGTH = 104
FIELDS: tuple[tuple[str, int, int], ...] = (
    ("state", 0, 2),
    ("district_unlading", 3, 5),
    ("port_unlading", 5, 7),
    ("district_entry", 7, 9),
    ("port_entry", 9, 11),
    ("country", 11, 15),
    ("time_period", 15, 16),
    ("value", 16, 28),
    ("air_val", 28, 40),
    ("air_swt", 40, 52),
    ("ves_val", 52, 64),
    ("cnt_val", 64, 76),
    ("ves_swt", 76, 88),
    ("cnt_swt", 88, 100),
    ("stat_year", 100, 104),
)
"""Field name, start and end (0-based, end exclusive) per the Census ISTPORT record layout."""
AMOUNTS = ("value", "air_val", "air_swt", "ves_val", "cnt_val", "ves_swt", "cnt_swt")
TARGET = Target(
    dataset=DATASET,
    table=DATASET,
    columns=(
        "load_id",
        "stat_year",
        "time_period",
        "state",
        "district_unlading",
        "port_unlading",
        "district_entry",
        "port_entry",
        "country",
        *AMOUNTS,
    ),
)


class StatePortError(Exception):
    """A State/Port file doesn't have the expected layout or isn't for the requested quarter."""


def partition_key(year: int, quarter: int) -> str:
    return f"{year}Q{quarter}"


def url(config: CensusStatePortConfig, year: int, quarter: int) -> str:
    return config.url_template.format(yy=f"{year % 100:02d}", quarter=quarter)


def archive_key(year: int, quarter: int) -> str:
    return object_key(
        DATASET, partition_key(year, quarter), f"ISTPORT{year % 100:02d}Q{quarter}.ZIP"
    )


def fetch_quarter(
    client: httpx.Client, config: CensusStatePortConfig, year: int, quarter: int
) -> tuple[bytes, str] | None:
    """The quarter's ZIP and its Last-Modified header, or None when Census hasn't published it."""
    source = url(config, year, quarter)
    head = client.head(source)
    if head.status_code == httpx.codes.NOT_FOUND:
        return None
    head.raise_for_status()
    body = http.get(client, source, {}).content
    return body, head.headers.get("last-modified") or "no Last-Modified header"


def parse_zip(
    body: bytes,
    year: int,
    quarter: int,
    config: CensusStatePortConfig,
    countries: CountryFilter | None,
) -> ParsedSource:
    """Rows for `raw.census_state_port` from one quarter's ZIP, filtered as configured."""
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise StatePortError(f"expected one data file in the ZIP, found {names}")
        text = zf.read(names[0]).decode("latin-1")
    states = set(config.states)
    rows: list[tuple[object, ...]] = []
    received = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        received += 1
        if len(line) != LINE_LENGTH:
            raise StatePortError(f"line {number} is {len(line)} characters, not {LINE_LENGTH}")
        record = {name: line[start:end] for name, start, end in FIELDS}
        if not all(record[name].isdigit() for name in (*AMOUNTS, "stat_year", "time_period")):
            raise StatePortError(f"line {number} has a non-numeric amount: {line!r}")
        if (int(record["stat_year"]), int(record["time_period"])) != (year, quarter):
            raise StatePortError(
                f"line {number} is for {record['stat_year']} Q{record['time_period']}, "
                f"not {year} Q{quarter}"
            )
        if countries is not None and not (
            record["country"] in countries.codes
            or record["country"].startswith(tuple(countries.code_prefixes))
        ):
            continue
        if record["state"] not in states:
            continue
        amounts = {name: int(record[name]) for name in AMOUNTS}
        if (
            config.drop_rows_without_air_or_vessel_weight
            and amounts["air_swt"] == 0
            and amounts["ves_swt"] == 0
        ):
            continue
        rows.append(
            (
                year,
                record["time_period"],
                record["state"],
                record["district_unlading"],
                record["port_unlading"],
                record["district_entry"],
                record["port_entry"],
                record["country"],
                *amounts.values(),
            )
        )
    return ParsedSource(rows=rows, rows_received=received, source_version=None)


def load_quarter(
    conn: psycopg.Connection,
    archive: Archive,
    config: CensusStatePortConfig,
    countries: CountryFilter | None,
    year: int,
    quarter: int,
    fetch: Callable[[], bytes] | None,
    version: str | None,
) -> LoadResult:
    """Archive one quarter's ZIP (or reuse the archived copy when `fetch` is None) and load it."""

    def parse(body: bytes) -> ParsedSource:
        parsed = parse_zip(body, year, quarter, config, countries)
        return ParsedSource(parsed.rows, parsed.rows_received, version)

    return load_partition(
        conn,
        archive,
        TARGET,
        partition_key(year, quarter),
        key=archive_key(year, quarter),
        content_type="application/zip",
        params={
            "year": year,
            "quarter": quarter,
            "url": url(config, year, quarter),
            "filters": {
                **config.model_dump(include={"states", "drop_rows_without_air_or_vessel_weight"}),
                "countries": countries.model_dump() if countries is not None else None,
            },
        },
        obtain=fetch,
        parse=parse,
    )
