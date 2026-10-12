"""Reference datasets for placing nodes: OurAirports, GeoNames cities and BTS border crossings.

Each dataset is one `latest` partition: the downloaded file is archived unchanged, then parsed
from the archived copy, and a reload replaces the previous snapshot.
"""

import csv
import io
import json
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime

import httpx
import psycopg

from shockt import http
from shockt.archive import Archive, object_key
from shockt.config import BorderCrossingsConfig, GeonamesCitiesConfig
from shockt.loading import ParsedSource, Target, load_partition
from shockt.manifest import LoadResult

PARTITION = "latest"

OURAIRPORTS = Target(
    dataset="ourairports_airports",
    table="ourairports_airports",
    columns=(
        "load_id",
        "id",
        "ident",
        "type",
        "name",
        "latitude_deg",
        "longitude_deg",
        "elevation_ft",
        "continent",
        "iso_country",
        "iso_region",
        "municipality",
        "scheduled_service",
        "icao_code",
        "iata_code",
        "gps_code",
        "local_code",
    ),
)
GEONAMES = Target(
    dataset="geonames_cities",
    table="geonames_cities",
    columns=(
        "load_id",
        "geonameid",
        "name",
        "asciiname",
        "latitude",
        "longitude",
        "feature_class",
        "feature_code",
        "country_code",
        "admin1_code",
        "admin2_code",
        "population",
        "timezone",
        "modification_date",
    ),
)
BORDER_CROSSINGS = Target(
    dataset="bts_border_crossings",
    table="bts_border_crossings",
    columns=(
        "load_id",
        "port_name",
        "state",
        "port_code",
        "border",
        "date",
        "measure",
        "value",
        "latitude",
        "longitude",
    ),
)

# Column positions in the GeoNames cities file (tab-separated, no header). Position 3 is
# alternatenames, which is large and not loaded.
_GEONAMES_POSITIONS = (0, 1, 2, 4, 5, 6, 7, 8, 10, 11, 14, 17, 18)


class ReferenceSourceError(Exception):
    """A reference download didn't parse into the expected shape."""


def parse_ourairports(body: bytes) -> ParsedSource:
    """Airports with an IATA code; the rest (heliports, private strips) have no use as nodes."""
    reader = csv.DictReader(io.StringIO(body.decode("utf-8")))
    missing = {"id", "iata_code", "latitude_deg", "longitude_deg"} - set(reader.fieldnames or [])
    if missing:
        raise ReferenceSourceError(f"OurAirports file is missing columns {sorted(missing)}")
    rows: list[tuple[object, ...]] = []
    received = 0
    for record in reader:
        received += 1
        if not (record.get("iata_code") or "").strip():
            continue
        rows.append(
            (
                int(record["id"]),
                *(_text(record.get(c)) for c in ("ident", "type", "name")),
                float(record["latitude_deg"]),
                float(record["longitude_deg"]),
                _int(record.get("elevation_ft")),
                *(
                    _text(record.get(c))
                    for c in (
                        "continent",
                        "iso_country",
                        "iso_region",
                        "municipality",
                        "scheduled_service",
                        "icao_code",
                        "iata_code",
                        "gps_code",
                        "local_code",
                    )
                ),
            )
        )
    return ParsedSource(rows=rows, rows_received=received, source_version=None)


def parse_geonames(body: bytes, config: GeonamesCitiesConfig) -> ParsedSource:
    """Cities in the configured countries, without the alternate-names column."""
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        name = next((n for n in zf.namelist() if n.endswith(".txt")), None)
        if name is None:
            raise ReferenceSourceError("GeoNames ZIP has no .txt file")
        text = zf.read(name).decode("utf-8")
    rows: list[tuple[object, ...]] = []
    received = 0
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) != 19:
            raise ReferenceSourceError(f"GeoNames line has {len(fields)} fields, expected 19")
        received += 1
        if fields[8] not in config.countries:
            continue
        values = [fields[i] for i in _GEONAMES_POSITIONS]
        rows.append(
            (
                int(values[0]),
                values[1],
                values[2],
                float(values[3]),
                float(values[4]),
                *(_text(v) for v in values[5:10]),
                _int(values[10]),
                _text(values[11]),
                date.fromisoformat(values[12]) if values[12] else None,
            )
        )
    return ParsedSource(rows=rows, rows_received=received, source_version=None)


def fetch_border_crossings(
    client: httpx.Client, config: BorderCrossingsConfig, start_month: str
) -> bytes:
    """Every row for the configured border since `start_month`, as one JSON bundle of pages."""
    where = f"border = '{config.border}' AND date >= '{start_month}-01'"
    pages: list[object] = []
    offset = 0
    while True:
        params = {
            "$where": where,
            "$order": "port_code, date, measure",
            "$limit": str(config.page_size),
            "$offset": str(offset),
        }
        page = http.get(client, config.url, params).json()
        if not isinstance(page, list):
            raise ReferenceSourceError(
                f"BTS returned {type(page).__name__}, expected a list of rows"
            )
        pages.append({"params": params, "rows": page})
        if len(page) < config.page_size:
            break
        offset += len(page)
    bundle = {
        "source": "bts_border_crossing_entry_data",
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pages": pages,
    }
    return json.dumps(bundle).encode()


def parse_border_crossings(body: bytes) -> ParsedSource:
    data = json.loads(body)
    rows: list[tuple[object, ...]] = []
    seen: set[tuple[str, str, str]] = set()
    received = 0
    for page in data["pages"]:
        for record in page["rows"]:
            received += 1
            key = (record["port_code"], record["date"], record["measure"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                (
                    _text(record.get("port_name")),
                    _text(record.get("state")),
                    record["port_code"],
                    _text(record.get("border")),
                    date.fromisoformat(record["date"][:10]),
                    record["measure"],
                    _int(record.get("value")),
                    _float(record.get("latitude")),
                    _float(record.get("longitude")),
                )
            )
    return ParsedSource(
        rows=rows, rows_received=received, source_version=f"fetched {data['fetched_at']}"
    )


def load(
    conn: psycopg.Connection,
    archive: Archive,
    target: Target,
    filename: str,
    content_type: str,
    params: dict[str, object],
    obtain: Callable[[], bytes] | None,
    parse: Callable[[bytes], ParsedSource],
    version: str | None,
) -> LoadResult:
    """Archive one reference download (or reuse the archived copy) and load it as `latest`."""

    def parse_with_version(body: bytes) -> ParsedSource:
        parsed = parse(body)
        return ParsedSource(
            rows=parsed.rows,
            rows_received=parsed.rows_received,
            source_version=parsed.source_version or version,
        )

    return load_partition(
        conn,
        archive,
        target,
        PARTITION,
        key=object_key(target.dataset, PARTITION, filename),
        content_type=content_type,
        params=params,
        obtain=obtain,
        parse=parse_with_version,
    )


def last_modified(client: httpx.Client, url: str) -> str:
    """The server's Last-Modified header for a download, or today's date if it sends none."""
    response = client.head(url)
    return response.headers.get("last-modified") or f"fetched {date.today().isoformat()}"


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _int(value: str | None) -> int | None:
    value = _text(value)
    return int(float(value)) if value is not None else None


def _float(value: str | None) -> float | None:
    value = _text(value)
    return float(value) if value is not None else None
