"""OECD maritime transport CO2 emissions (experimental): monthly CO2 of large vessels.

Emissions are allocated to the country where the operating company resides. Each partition is
one calendar year; one SDMX-CSV request carries every area, ship type and month in it.
Quarterly and annual series are not requested, so each month is counted once. Archived as the
raw CSV response.
"""

import csv
import io
import re
from collections.abc import Callable

import httpx
import psycopg

from shockt import http
from shockt.archive import Archive, object_key
from shockt.config import OecdMaritimeConfig
from shockt.loading import LoadResult, ParsedSource, Target, load_partition
from shockt.months import MonthRange

DATASET = "oecd_maritime_emissions"
FREQUENCY = "M"
KEY_DIMENSIONS = 8
"""REF_AREA, FREQ, MEASURE, UNIT_MEASURE, ADJUSTMENT, POLLUTANT, SOURCE, VESSEL."""
MONTH = re.compile(r"\d{4}-\d{2}")

TARGET = Target(
    dataset=DATASET,
    table="oecd_maritime_emissions",
    columns=(
        "load_id",
        "time_period",
        "ref_area",
        "measure",
        "unit_measure",
        "adjustment",
        "pollutant",
        "source",
        "vessel",
        "obs_status",
        "unit_mult",
        "obs_value",
    ),
)

CSV_COLUMNS = (
    "REF_AREA",
    "FREQ",
    "MEASURE",
    "UNIT_MEASURE",
    "ADJUSTMENT",
    "POLLUTANT",
    "SOURCE",
    "VESSEL",
    "TIME_PERIOD",
    "OBS_VALUE",
    "OBS_STATUS",
    "UNIT_MULT",
)


class OecdMaritimeError(Exception):
    """The OECD response doesn't have the structure the parser expects."""


def partition_key(year: int) -> str:
    return str(year)


def sdmx_key() -> str:
    """The SDMX key: every value of every dimension except the monthly frequency."""
    fields = [""] * KEY_DIMENSIONS
    fields[1] = FREQUENCY
    return ".".join(fields)


def fetch_year(client: httpx.Client, config: OecdMaritimeConfig, months: MonthRange) -> bytes:
    """Fetch the monthly series for `months` as SDMX-CSV."""
    params = {
        "startPeriod": months.first,
        "endPeriod": months.last,
        "dimensionAtObservation": "AllDimensions",
        "format": "csv",
    }
    return http.get(
        client, f"{config.base_url}/data/{config.dataflow}/{sdmx_key()}", params
    ).content


def parse_csv(body: bytes) -> ParsedSource:
    """Parse the SDMX-CSV response into rows for raw.oecd_maritime_emissions."""
    reader = csv.DictReader(io.StringIO(body.decode("utf-8")))
    if reader.fieldnames is None:
        raise OecdMaritimeError("empty response: no header row")
    missing = [c for c in CSV_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise OecdMaritimeError(f"SDMX-CSV header missing columns: {missing}")
    rows: list[tuple[object, ...]] = []
    for record in reader:
        if record["FREQ"] != FREQUENCY or not MONTH.fullmatch(record["TIME_PERIOD"]):
            freq, period = record["FREQ"], record["TIME_PERIOD"]
            raise OecdMaritimeError(f"row is not monthly: FREQ={freq!r}, TIME_PERIOD={period!r}")
        value = record["OBS_VALUE"].strip()
        rows.append(
            (
                record["TIME_PERIOD"],
                record["REF_AREA"],
                record["MEASURE"],
                record["UNIT_MEASURE"],
                record["ADJUSTMENT"],
                record["POLLUTANT"],
                record["SOURCE"],
                record["VESSEL"],
                record["OBS_STATUS"].strip() or None,
                int(record["UNIT_MULT"]),
                float(value) if value else None,
            )
        )
    if not rows:
        raise OecdMaritimeError("response has no observations")
    return ParsedSource(rows=rows, rows_received=len(rows), source_version=None)


def load_year(
    conn: psycopg.Connection,
    archive: Archive,
    config: OecdMaritimeConfig,
    year: int,
    months: MonthRange,
    obtain: Callable[[], bytes] | None,
) -> LoadResult:
    """Archive one year's SDMX-CSV response (or reuse the archived copy when `obtain` is None) and
    load the months in `months`, which must fall in `year`."""
    if months.years() != range(year, year + 1):
        raise OecdMaritimeError(f"months {months.first}..{months.last} are not all in {year}")
    return load_partition(
        conn,
        archive,
        TARGET,
        partition_key(year),
        key=object_key(DATASET, partition_key(year), f"{year}.csv"),
        content_type="text/csv",
        params={"dataflow": config.dataflow, "year": year, **months.as_params()},
        obtain=obtain,
        parse=parse_csv,
    )
