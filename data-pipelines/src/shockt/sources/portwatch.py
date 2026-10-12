"""IMF PortWatch daily chokepoint transits, from the public ArcGIS FeatureServer.

One partition is one chokepoint for one calendar year. Its pages are archived as one JSON
bundle, then parsed from the archived copy, keeping only the days inside the requested months.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import psycopg

from shockt import http
from shockt.archive import Archive, object_key
from shockt.config import PortwatchConfig
from shockt.loading import ParsedSource, Target, load_partition
from shockt.manifest import LoadResult
from shockt.months import MonthRange

DATASET = "portwatch_chokepoints"
BUNDLE_FILENAME = "responses.json"

_COUNTS = (
    "n_container",
    "n_dry_bulk",
    "n_general_cargo",
    "n_roro",
    "n_tanker",
    "n_cargo",
    "n_total",
)
_CAPACITIES = (
    "capacity_container",
    "capacity_dry_bulk",
    "capacity_general_cargo",
    "capacity_roro",
    "capacity_tanker",
    "capacity_cargo",
    "capacity",
)
TARGET = Target(
    dataset=DATASET,
    table="portwatch_chokepoints",
    columns=("load_id", "object_id", "date", "portid", "portname", *_COUNTS, *_CAPACITIES),
)


class PortwatchError(Exception):
    """PortWatch returned an error or rows that don't belong to the requested partition."""


def partition_key(portid: str, year: int) -> str:
    return f"{portid}:{year}"


def archive_key(portid: str, year: int) -> str:
    return object_key(DATASET, f"{portid}_{year}", BUNDLE_FILENAME)


@dataclass(frozen=True)
class LayerInfo:
    data_last_edited: str
    """When PortWatch last changed the layer's data, as an ISO timestamp."""
    max_record_count: int
    """The most records the layer returns per query page."""


def layer_info(client: httpx.Client, config: PortwatchConfig) -> LayerInfo:
    """The layer's last data edit and page size, from its metadata."""
    layer_url = config.query_url.removesuffix("/query")
    info = _json(http.get(client, layer_url, {"f": "json"}))
    editing = info.get("editingInfo")
    edited_ms = editing.get("dataLastEditDate") if isinstance(editing, dict) else None
    if not isinstance(edited_ms, int):
        raise PortwatchError("layer info has no editingInfo.dataLastEditDate")
    max_records = info.get("maxRecordCount")
    if not isinstance(max_records, int) or max_records < 1:
        raise PortwatchError(f"layer info has no usable maxRecordCount: {max_records!r}")
    return LayerInfo(
        data_last_edited=datetime.fromtimestamp(edited_ms / 1000, UTC).isoformat(
            timespec="seconds"
        ),
        max_record_count=max_records,
    )


def fetch_bundle(
    client: httpx.Client, config: PortwatchConfig, portid: str, year: int, layer: LayerInfo
) -> bytes:
    """Every page of one chokepoint-year, as a JSON bundle."""
    pages: list[dict[str, object]] = []
    offset = 0
    while True:
        params = {
            "where": f"portid='{portid}' AND year={year}",
            "outFields": "*",
            "returnGeometry": "false",
            "orderByFields": "date",
            "resultOffset": str(offset),
            "resultRecordCount": str(layer.max_record_count),
            "f": "json",
        }
        body = _json(http.get(client, config.query_url, params))
        features = body.get("features")
        if not isinstance(features, list):
            raise PortwatchError(f"{portid} {year}: response has no features list")
        pages.append({"params": params, "body": body})
        if not body.get("exceededTransferLimit"):
            break
        if not features:
            raise PortwatchError(
                f"{portid} {year}: more pages reported but page {len(pages)} is empty"
            )
        offset += len(features)
    bundle = {
        "source": "imf_portwatch_daily_chokepoints",
        "portid": portid,
        "year": year,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_last_edited": layer.data_last_edited,
        "pages": pages,
    }
    return json.dumps(bundle).encode()


def parse_bundle(bundle: bytes, months: MonthRange) -> ParsedSource:
    """Rows for `raw.portwatch_chokepoints` from an archived bundle, for days in `months`."""
    data = json.loads(bundle)
    portid, year = data["portid"], data["year"]
    rows: list[tuple[object, ...]] = []
    seen: set[int] = set()
    for page in data["pages"]:
        for feature in page["body"]["features"]:
            attributes = feature["attributes"]
            day = date.fromisoformat(attributes["date"])
            if attributes["portid"] != portid or day.year != year:
                raise PortwatchError(
                    f"row {attributes['ObjectId']} is {attributes['portid']} {day}, "
                    f"not {portid} {year}"
                )
            object_id = int(attributes["ObjectId"])
            if object_id in seen:
                continue
            seen.add(object_id)
            if not months.contains(day):
                continue
            rows.append(
                (
                    object_id,
                    day,
                    attributes["portid"],
                    attributes["portname"],
                    *(_int(attributes, name) for name in (*_COUNTS, *_CAPACITIES)),
                )
            )
    return ParsedSource(
        rows=rows,
        rows_received=len(seen),
        source_version=f"data last edited {data['data_last_edited']}",
    )


def load_year(
    conn: psycopg.Connection,
    archive: Archive,
    portid: str,
    year: int,
    months: MonthRange,
    fetch: Callable[[], bytes] | None,
) -> LoadResult:
    """Archive one chokepoint-year (or reuse the archived copy when `fetch` is None) and load
    the days in `months`, which must fall in `year`."""
    if months.years() != range(year, year + 1):
        raise PortwatchError(f"months {months.first}..{months.last} are not all in {year}")
    return load_partition(
        conn,
        archive,
        TARGET,
        partition_key(portid, year),
        key=archive_key(portid, year),
        content_type="application/json",
        params={"portid": portid, "year": year, **months.as_params()},
        obtain=fetch,
        parse=lambda body: parse_bundle(body, months),
    )


def _json(response: httpx.Response) -> dict[str, object]:
    body = response.json()
    if not isinstance(body, dict):
        raise PortwatchError("response is not a JSON object")
    if "error" in body:
        # ArcGIS reports query errors with HTTP 200 and an error object.
        raise PortwatchError(f"PortWatch error: {body['error']}")
    return body


def _int(attributes: dict[str, object], name: str) -> int | None:
    value = attributes.get(name)
    if value is None:
        return None
    if not isinstance(value, int | float):
        raise PortwatchError(f"{name} is not numeric: {value!r}")
    return int(value)
