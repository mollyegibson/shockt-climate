"""Eurostat Comext DS-059334: extra-EU trade by mode of transport, at HS-6.

Monthly imports from extra-EU partners, with transport mode, weight in kg and value in EUR.
Each partition is one month × HS-6 code; one SDMX-CSV request carries all reporters, partners
and modes. Archived as the raw CSV response.
"""

import csv
import io
from collections.abc import Callable, Sequence

import httpx
import psycopg

from shockt import http
from shockt.archive import Archive, object_key
from shockt.config import ComextConfig
from shockt.loading import LoadResult, ParsedSource, Target, load_partition

DATASET = "comext_trade"

TARGET = Target(
    dataset=DATASET,
    table="comext_trade",
    columns=(
        "load_id",
        "time_period",
        "reporter",
        "partner",
        "product",
        "flow",
        "transport_mode",
        "indicator",
        "obs_value",
    ),
)

SDMX_CSV_COLUMNS = (
    "DATAFLOW",
    "LAST UPDATE",
    "freq",
    "reporter",
    "partner",
    "product",
    "flow",
    "transport_mode",
    "indicators",
    "TIME_PERIOD",
    "OBS_VALUE",
    "OBS_FLAG",
)


class ComextSourceError(Exception):
    """The Comext response doesn't have the structure the parser expects."""


def partition_key(month: str, hs6: str) -> str:
    return f"{month}:{hs6}"


def _sdmx_key(
    reporters: Sequence[str],
    partners: Sequence[str],
    hs6: str,
    flow: str,
    indicators: Sequence[str],
) -> str:
    """The SDMX key: freq.reporter.partner.product.flow.transport_mode.indicators."""
    return ".".join(
        [
            "M",
            "+".join(reporters),
            "+".join(partners),
            hs6,
            flow,
            "",  # all transport modes
            "+".join(indicators),
        ]
    )


def fetch_month(
    client: httpx.Client,
    config: ComextConfig,
    reporters: Sequence[str],
    partners: Sequence[str],
    hs6: str,
    month: str,
) -> bytes:
    """Fetch one month × HS-6 from Comext as SDMX-CSV."""
    key = _sdmx_key(reporters, partners, hs6, config.flow, config.indicators)
    url = f"{config.base_url}/data/{config.dataset}/{key}"
    params = {
        "startPeriod": month,
        "endPeriod": month,
        "format": "SDMX-CSV",
    }
    response = http.get(client, url, params)
    return response.content


def parse_csv(body: bytes) -> ParsedSource:
    """Parse the SDMX-CSV response into rows for raw.comext_trade."""
    text = body.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ComextSourceError("empty response: no header row")
    expected = (
        "TIME_PERIOD",
        "OBS_VALUE",
        "reporter",
        "partner",
        "product",
        "flow",
        "transport_mode",
        "indicators",
    )
    missing = [c for c in expected if c not in reader.fieldnames]
    if missing:
        raise ComextSourceError(f"SDMX-CSV header missing columns: {missing}")

    rows: list[tuple[object, ...]] = []
    for row in reader:
        obs_raw = row["OBS_VALUE"].strip() if row["OBS_VALUE"] else None
        obs_value = None if obs_raw in (None, "", ":") else float(obs_raw)
        rows.append(
            (
                row["TIME_PERIOD"],
                row["reporter"],
                row["partner"],
                row["product"],
                row["flow"],
                row["transport_mode"],
                row["indicators"],
                obs_value,
            )
        )
    return ParsedSource(rows=rows, rows_received=len(rows), source_version=None)


def load_month(
    conn: psycopg.Connection,
    archive: Archive,
    config: ComextConfig,
    reporters: Sequence[str],
    partners: Sequence[str],
    hs6: str,
    month: str,
    obtain: Callable[[], bytes] | None,
) -> LoadResult:
    """Archive the SDMX-CSV response, parse it and load one month × HS-6 partition."""
    key = object_key(DATASET, partition_key(month, hs6), f"{month}_{hs6}.csv")
    params: dict[str, object] = {
        "dataset": config.dataset,
        "month": month,
        "hs6": hs6,
        "flow": config.flow,
        "reporters": list(reporters),
        "partners": list(partners),
        "indicators": config.indicators,
    }
    return load_partition(
        conn,
        archive,
        TARGET,
        partition_key(month, hs6),
        key=key,
        content_type="text/csv",
        params=params,
        obtain=obtain,
        parse=parse_csv,
    )
