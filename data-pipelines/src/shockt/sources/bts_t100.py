"""BTS T-100 International Segment (All Carriers): freight on nonstop flight segments to and from
the US, by US and foreign carriers, by month, carrier and airport pair (plan section 5.8).

One partition is one calendar year. TranStats has no file download or API for this table, so the
year's ZIP is requested through its download form (an ASP.NET page: the form's hidden fields are
read from a GET and posted back with the year and the requested fields). The ZIP is archived
unchanged, then its CSV is parsed from the archived copy, keeping the requested months, the
configured origin countries and segments that carried freight.
"""

import csv
import io
import zipfile
from collections.abc import Callable
from datetime import date
from html.parser import HTMLParser

import httpx
import psycopg

from shockt import http
from shockt.archive import Archive, object_key
from shockt.config import BtsT100Config
from shockt.loading import ParsedSource, Target, load_partition
from shockt.manifest import LoadResult
from shockt.months import MonthRange

DATASET = "bts_t100_segments"
DATA_FILE = "T_T100I_SEGMENT_ALL_CARRIER.csv"
DOCUMENTATION_FILE = "Documentation.csv"
FORM_ID = "form1"
INTEGERS = (
    "YEAR",
    "MONTH",
    "ORIGIN_AIRPORT_ID",
    "ORIGIN_WAC",
    "DEST_AIRPORT_ID",
    "DEST_WAC",
    "AIRCRAFT_GROUP",
    "AIRCRAFT_TYPE",
    "AIRCRAFT_CONFIG",
)
TEXTS = ("UNIQUE_CARRIER", "ORIGIN", "ORIGIN_COUNTRY", "DEST", "DEST_COUNTRY", "CLASS")
AMOUNTS = ("DEPARTURES_PERFORMED", "FREIGHT", "MAIL", "DISTANCE")
FIELDS = (*INTEGERS, *TEXTS, *AMOUNTS)
"""The form fields requested, which are also the CSV's columns."""
TARGET = Target(
    dataset=DATASET,
    table=DATASET,
    columns=(
        "load_id",
        "line_number",
        "year",
        "month",
        "unique_carrier",
        "origin_airport_id",
        "origin",
        "origin_country",
        "origin_wac",
        "dest_airport_id",
        "dest",
        "dest_country",
        "dest_wac",
        "aircraft_group",
        "aircraft_type",
        "aircraft_config",
        "class",
        "departures_performed",
        "freight",
        "mail",
        "distance",
    ),
)


class T100Error(Exception):
    """The download form or file doesn't have the expected shape, or is for another year."""


class _FormReader(HTMLParser):
    """The hidden inputs of the download form and the years its year menu offers. The page nests
    a search form inside the download form, so forms are tracked by depth."""

    def __init__(self) -> None:
        super().__init__()
        self.hidden: dict[str, str] = {}
        self.years: list[str] = []
        self._form_depth = 0
        self._in_year_menu = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "form":
            if self._form_depth or attributes.get("id") == FORM_ID:
                self._form_depth += 1
        elif not self._form_depth:
            return
        elif (
            tag == "input"
            and self._form_depth == 1
            and attributes.get("type") == "hidden"
            and attributes.get("name")
        ):
            self.hidden[attributes["name"] or ""] = attributes.get("value") or ""
        elif tag == "select":
            self._in_year_menu = attributes.get("name") == "cboYear"
        elif tag == "option" and self._in_year_menu and attributes.get("value"):
            self.years.append(attributes["value"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form_depth:
            self._form_depth -= 1
        elif tag == "select":
            self._in_year_menu = False


def partition_key(year: int) -> str:
    return str(year)


def archive_key(year: int) -> str:
    return object_key(DATASET, partition_key(year), "T_T100I_SEGMENT_ALL_CARRIER.zip")


def read_form(page: str) -> tuple[dict[str, str], list[str]]:
    """The download form's hidden fields and the years it offers."""
    reader = _FormReader()
    reader.feed(page)
    if not reader.hidden or not reader.years:
        raise T100Error("the download page has no form with hidden fields and a year menu")
    return reader.hidden, reader.years


def fetch_year(client: httpx.Client, config: BtsT100Config, year: int) -> bytes | None:
    """The year's ZIP from the download form, or None when the form doesn't offer the year yet."""
    hidden, years = read_form(http.get(client, config.form_url, {}).text)
    if str(year) not in years:
        return None
    form = {
        **hidden,
        "cboGeography": "All",
        "cboYear": str(year),
        "cboPeriod": "All",
        "chkDownloadZip": "on",
        "btnDownload": "Download",
        **dict.fromkeys(FIELDS, "on"),
    }
    response = http.post_form(client, config.form_url, form)
    if not response.content.startswith(b"PK"):
        raise T100Error(
            f"the form returned {response.headers.get('content-type')}, not a ZIP, for {year}"
        )
    return response.content


def parse_zip(
    body: bytes,
    year: int,
    months: MonthRange,
    config: BtsT100Config,
    origin_countries: list[str] | None,
) -> ParsedSource:
    """Rows for `raw.bts_t100_segments` from one year's ZIP, for `months`, filtered as
    configured. The source version is the latest month in the file."""
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = set(zf.namelist())
        if names - {DOCUMENTATION_FILE} != {DATA_FILE}:
            raise T100Error(f"expected {DATA_FILE} in the ZIP, found {sorted(names)}")
        text = zf.read(DATA_FILE).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    missing = sorted(set(FIELDS) - set(reader.fieldnames or ()))
    if missing:
        raise T100Error(f"{DATA_FILE} lacks the requested columns {missing}")
    countries = set(origin_countries) if origin_countries is not None else None
    rows: list[tuple[object, ...]] = []
    received = 0
    latest_month = 0
    for line_number, record in enumerate(reader, start=2):
        received += 1
        try:
            integers = {name: int(record[name]) for name in INTEGERS}
            amounts = {name: float(record[name]) for name in AMOUNTS}
        except ValueError as exc:
            raise T100Error(f"line {line_number}: {exc}") from None
        if integers["YEAR"] != year:
            raise T100Error(f"line {line_number} is for {integers['YEAR']}, not {year}")
        month = integers["MONTH"]
        if not 1 <= month <= 12:
            raise T100Error(f"line {line_number} has month {record['MONTH']!r}")
        latest_month = max(latest_month, month)
        if not months.contains(date(year, month, 1)):
            continue
        if countries is not None and record["ORIGIN_COUNTRY"] not in countries:
            continue
        if config.drop_rows_without_freight and amounts["FREIGHT"] <= 0:
            continue
        rows.append(
            (
                line_number,
                year,
                month,
                record["UNIQUE_CARRIER"],
                integers["ORIGIN_AIRPORT_ID"],
                record["ORIGIN"],
                record["ORIGIN_COUNTRY"],
                integers["ORIGIN_WAC"],
                integers["DEST_AIRPORT_ID"],
                record["DEST"],
                record["DEST_COUNTRY"],
                integers["DEST_WAC"],
                integers["AIRCRAFT_GROUP"],
                integers["AIRCRAFT_TYPE"],
                integers["AIRCRAFT_CONFIG"],
                record["CLASS"],
                amounts["DEPARTURES_PERFORMED"],
                amounts["FREIGHT"],
                amounts["MAIL"],
                amounts["DISTANCE"],
            )
        )
    if received == 0:
        raise T100Error(f"{DATA_FILE} has no rows")
    return ParsedSource(
        rows=rows,
        rows_received=received,
        source_version=f"data through {year}-{latest_month:02d}",
    )


def load_year(
    conn: psycopg.Connection,
    archive: Archive,
    config: BtsT100Config,
    origin_countries: list[str] | None,
    year: int,
    months: MonthRange,
    fetch: Callable[[], bytes] | None,
) -> LoadResult:
    """Archive one year's ZIP (or reuse the archived copy when `fetch` is None) and load the
    rows in `months`, which must fall in `year`."""
    if months.years() != range(year, year + 1):
        raise T100Error(f"months {months.first}..{months.last} are not all in {year}")
    return load_partition(
        conn,
        archive,
        TARGET,
        partition_key(year),
        key=archive_key(year),
        content_type="application/zip",
        params={
            "year": year,
            "url": config.form_url,
            **months.as_params(),
            "filters": {
                "drop_rows_without_freight": config.drop_rows_without_freight,
                "origin_countries": origin_countries,
            },
        },
        obtain=fetch,
        parse=lambda body: parse_zip(body, year, months, config, origin_countries),
    )
