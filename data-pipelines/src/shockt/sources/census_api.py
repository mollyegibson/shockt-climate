"""Census International Trade API loader for the `hs`, `porths` and `statehs` import endpoints.

One partition is one month of one case HS prefix of one endpoint, keyed `2025-03:847150`, so
adding a case's HS codes loads only the new prefix. Each partition makes one request, archives
the response as a JSON bundle, then parses the archived bundle into raw.
"""

import json
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import partial
from typing import Literal

import httpx
import psycopg

from shockt import http
from shockt.archive import Archive, object_key
from shockt.config import CensusApiConfig, CensusDataset, CensusRowFilter
from shockt.loading import ParsedSource, Target, load_partition
from shockt.manifest import LoadResult

FieldKind = Literal["text", "int"]

BUNDLE_FILENAME = "responses.json"


@dataclass(frozen=True)
class Field:
    api_name: str
    column: str
    kind: FieldKind


def _text(api_name: str) -> Field:
    return Field(api_name, api_name.lower(), "text")


def _int(api_name: str) -> Field:
    return Field(api_name, api_name.lower(), "int")


_VALUE_FIELDS = (
    _int("GEN_VAL_MO"),
    _int("AIR_VAL_MO"),
    _int("AIR_WGT_MO"),
    _int("VES_VAL_MO"),
    _int("VES_WGT_MO"),
    _int("CNT_VAL_MO"),
    _int("CNT_WGT_MO"),
)


@dataclass(frozen=True)
class DatasetSpec:
    endpoint: CensusDataset
    comm_lvl: str
    """The deepest HS level the endpoint serves; `porths` and `statehs` answer HS-10 requests with
    HTTP 204 (plan spike 1)."""
    requested: tuple[Field, ...]
    """Fields named in the `get` parameter, in request order."""
    predicates: tuple[Field, ...]
    """Fields Census appends to each row from the query predicates."""

    @property
    def manifest_dataset(self) -> str:
        return f"census_{self.endpoint}"

    @property
    def table(self) -> str:
        return f"census_{self.endpoint}"

    @property
    def columns(self) -> tuple[str, ...]:
        return ("load_id", *(f.column for f in (*self.requested, *self.predicates)))

    @property
    def target(self) -> Target:
        return Target(dataset=self.manifest_dataset, table=self.table, columns=self.columns)


DATASETS: dict[str, DatasetSpec] = {
    "hs": DatasetSpec(
        endpoint="hs",
        comm_lvl="HS10",
        requested=(
            _text("I_COMMODITY"),
            _text("I_COMMODITY_SDESC"),
            _text("CTY_CODE"),
            _text("CTY_NAME"),
            _text("SUMMARY_LVL"),
            *_VALUE_FIELDS,
            _int("CON_VAL_MO"),
            _int("GEN_QY1_MO"),
            _text("UNIT_QY1"),
            _int("GEN_QY2_MO"),
            _text("UNIT_QY2"),
            _text("LAST_UPDATE"),
        ),
        predicates=(Field("time", "time", "text"),),
    ),
    "porths": DatasetSpec(
        endpoint="porths",
        comm_lvl="HS6",
        requested=(
            _text("I_COMMODITY"),
            _text("CTY_CODE"),
            _text("CTY_NAME"),
            _text("PORT"),
            _text("PORT_NAME"),
            _text("SUMMARY_LVL"),
            *_VALUE_FIELDS,
            _text("LAST_UPDATE"),
        ),
        predicates=(Field("time", "time", "text"), Field("COMM_LVL", "comm_lvl", "text")),
    ),
    "statehs": DatasetSpec(
        endpoint="statehs",
        comm_lvl="HS6",
        requested=(
            _text("I_COMMODITY"),
            _text("CTY_CODE"),
            _text("CTY_NAME"),
            _text("STATE"),
            _text("SUMMARY_LVL"),
            *_VALUE_FIELDS,
            _int("CON_VAL_MO"),
            _text("LAST_UPDATE"),
        ),
        predicates=(Field("time", "time", "text"), Field("COMM_LVL", "comm_lvl", "text")),
    ),
}


class CensusResponseError(Exception):
    """Census returned something other than JSON rows or an empty 204."""


def month_range(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' months from `start` to `end`."""
    first = date.fromisoformat(f"{start}-01")
    last = date.fromisoformat(f"{end}-01")
    if first > last:
        raise ValueError(f"start month {start} is after end month {end}")
    months: list[str] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def latest_month(client: httpx.Client, config: CensusApiConfig, api_key: str, since: str) -> str:
    """The latest month Census has published, found from HS chapter 84 totals."""
    response = http.get(
        client,
        f"{config.base_url}/hs",
        {
            "get": "GEN_VAL_MO",
            "time": f"from {since}",
            "COMM_LVL": "HS2",
            "I_COMMODITY": "84",
            "key": api_key,
        },
        secrets=(api_key,),
    )
    rows = _parse_json_rows(response)
    if not rows or len(rows) < 2:
        raise CensusResponseError(f"No published months found since {since}")
    time_index = rows[0].index("time")
    return max(row[time_index] for row in rows[1:])


def partition_key(month: str, hs_prefix: str) -> str:
    return f"{month}:{hs_prefix}"


def fetch_bundle(
    client: httpx.Client,
    spec: DatasetSpec,
    month: str,
    hs_prefix: str,
    config: CensusApiConfig,
    api_key: str,
) -> bytes:
    """Request one month of one case HS prefix and return the response as a JSON bundle."""
    params = {
        "get": ",".join(f.api_name for f in spec.requested),
        "time": month,
        "COMM_LVL": spec.comm_lvl,
        "I_COMMODITY": f"{hs_prefix}*",
    }
    response = http.get(
        client,
        f"{config.base_url}/{spec.endpoint}",
        {**params, "key": api_key},
        secrets=(api_key,),
    )
    bundle = {
        "source": "census_international_trade_api",
        "endpoint": spec.endpoint,
        "month": month,
        "hs_prefix": hs_prefix,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "responses": [
            {"params": params, "status": response.status_code, "body": _parse_json_rows(response)}
        ],
    }
    return json.dumps(bundle, ensure_ascii=False).encode()


@dataclass(frozen=True)
class ParsedBundle:
    rows: list[tuple[object, ...]]
    """Rows kept by the filter, without the load_id column."""
    rows_received: int


class RowFilter:
    """Applies a `CensusRowFilter` to parsed rows of one endpoint."""

    def __init__(self, spec: DatasetSpec, config: CensusRowFilter) -> None:
        columns = spec.columns[1:]
        self._config = config
        self._summary_lvl = columns.index("summary_lvl")
        self._cty_code = columns.index("cty_code")
        self._numeric = [
            i for i, f in enumerate((*spec.requested, *spec.predicates)) if f.kind == "int"
        ]

    def keep(self, row: tuple[object, ...]) -> bool:
        if self._config.drop_country_groups and row[self._summary_lvl] == "CGP":
            return False
        if self._config.drop_all_zero and all(not row[i] for i in self._numeric):
            return False
        countries = self._config.countries
        if countries is not None:
            code = str(row[self._cty_code])
            return code in countries.codes or code.startswith(tuple(countries.code_prefixes))
        return True


def parse_bundle(spec: DatasetSpec, bundle: bytes, row_filter: CensusRowFilter) -> ParsedBundle:
    """Parse an archived bundle into rows for `spec.table`, applying `row_filter`."""
    data = json.loads(bundle)
    keep = RowFilter(spec, row_filter).keep
    rows: list[tuple[object, ...]] = []
    received = 0
    for response in data["responses"]:
        body = response["body"]
        if body is None:
            continue
        for row in parse_rows(spec, body):
            received += 1
            if keep(row):
                rows.append(row)
    return ParsedBundle(rows=rows, rows_received=received)


def parse_rows(spec: DatasetSpec, body: Sequence[Sequence[str]]) -> Iterator[tuple[object, ...]]:
    """Convert one Census response (a header row then data rows) into typed tuples.

    Census appends the query predicates to every row, which repeats `I_COMMODITY`, so each
    field is read from the first column with its name.
    """
    header = list(body[0])
    fields = (*spec.requested, *spec.predicates)
    indexes: list[int] = []
    for field in fields:
        if field.api_name not in header:
            raise CensusResponseError(f"{spec.endpoint}: response has no {field.api_name} column")
        indexes.append(header.index(field.api_name))
    for line, raw in enumerate(body[1:], start=2):
        try:
            yield tuple(_convert(raw[i], f.kind) for i, f in zip(indexes, fields, strict=True))
        except ValueError as exc:
            raise CensusResponseError(f"{spec.endpoint}: row {line}: {exc}") from exc


def load_month(
    conn: psycopg.Connection,
    archive: Archive,
    spec: DatasetSpec,
    month: str,
    hs_prefix: str,
    fetch: Callable[[], bytes] | None,
    row_filter: CensusRowFilter,
) -> LoadResult:
    """Load one month of one HS prefix: fetch and archive the bundle (or reuse the archived
    one), then parse it.

    With `fetch=None`, the bundle is read from the archive instead of requested again. The
    manifest params record the filter applied and how many rows Census returned before it.
    """
    key = partition_key(month, hs_prefix)
    return load_partition(
        conn,
        archive,
        spec.target,
        key,
        key=object_key(spec.manifest_dataset, key, BUNDLE_FILENAME),
        content_type="application/json",
        params=_params(spec, month, hs_prefix, row_filter),
        obtain=fetch,
        parse=partial(_parse_source, spec, row_filter=row_filter),
    )


def _params(
    spec: DatasetSpec, month: str, hs_prefix: str, row_filter: CensusRowFilter
) -> dict[str, object]:
    return {
        "endpoint": spec.endpoint,
        "month": month,
        "hs_prefix": hs_prefix,
        "filters": row_filter.model_dump(),
    }


def _parse_source(spec: DatasetSpec, bundle: bytes, row_filter: CensusRowFilter) -> ParsedSource:
    parsed = parse_bundle(spec, bundle, row_filter)
    return ParsedSource(
        rows=parsed.rows,
        rows_received=parsed.rows_received,
        source_version=f"fetched {json.loads(bundle)['fetched_at']}",
    )


def _parse_json_rows(response: httpx.Response) -> list[list[str]] | None:
    if response.status_code == 204 or not response.content.strip():
        return None
    try:
        data = response.json()
    except ValueError:
        # An invalid or inactive key returns HTTP 200 with an HTML page.
        title = "Invalid Key" if b"Invalid Key" in response.content else "non-JSON body"
        raise CensusResponseError(
            f"Census returned {title} (HTTP {response.status_code})"
        ) from None
    if not isinstance(data, list) or not data or not isinstance(data[0], list):
        raise CensusResponseError("Census response is not a list of rows")
    return data


def _convert(value: str | None, kind: FieldKind) -> object:
    if kind == "text":
        return value
    if value is None or value == "":
        return None
    return int(value)
