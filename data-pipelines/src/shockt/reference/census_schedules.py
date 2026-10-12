"""Seeds from the Census reference lists: country codes (Schedule C) and ports (Schedule D).

The seeds hold the published lists as-is, plus ISO3 codes looked up from ISO2 in ISO 3166, or for
Census-specific ISO2 codes in `census_schedules.iso3_overrides` (config/sources.yaml). Regions are
assigned in dbt (`macros/census_regions.sql`), not here.
"""

import csv
import html
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pycountry

_COUNTRY_LINE = re.compile(r"^(\d{4})\s*\|\s*(.+?)\s*\|\s*([A-Z]{2})?\s*$")


class ScheduleError(Exception):
    """A Census schedule didn't parse into the expected shape."""


@dataclass(frozen=True)
class Country:
    census_code: str
    name: str
    iso2: str | None
    iso3: str | None


@dataclass(frozen=True)
class Port:
    port_code: str
    port_name: str
    district_code: str


def parse_schedule_c(text: str, iso3_overrides: Mapping[str, str]) -> list[Country]:
    countries = []
    for line in text.splitlines():
        match = _COUNTRY_LINE.match(line)
        if match is None:
            continue
        code, name, iso2 = match.groups()
        countries.append(Country(code, name, iso2, _iso3(iso2, iso3_overrides)))
    if len(countries) < 200:
        raise ScheduleError(f"Schedule C parsed to only {len(countries)} countries")
    return countries


def parse_schedule_d(page: str) -> list[Port]:
    """Ports from the Schedule D page, where each district is followed by its ports."""
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    ports: list[Port] = []
    for i, line in enumerate(lines[:-2]):
        code = lines[i + 2]
        if line in ("DISTRICT", "Port") and re.fullmatch(r"\d{4}", code):
            ports.append(Port(code, lines[i + 1], code[:2]))
    if len(ports) < 300:
        raise ScheduleError(f"Schedule D parsed to only {len(ports)} ports")
    return ports


def write_countries(countries: list[Country], path: Path, source: str) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["census_cty_code", "cty_name", "iso2", "iso3", "source"])
        for c in countries:
            writer.writerow([c.census_code, c.name, c.iso2 or "", c.iso3 or "", source])


def write_ports(ports: list[Port], path: Path, source: str) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["port_code", "port_name", "district_code", "source"])
        for p in ports:
            writer.writerow([p.port_code, p.port_name, p.district_code, source])


def _iso3(iso2: str | None, overrides: Mapping[str, str]) -> str | None:
    if iso2 is None:
        return None
    if iso2 in overrides:
        return overrides[iso2]
    country = pycountry.countries.get(alpha_2=iso2)
    return country.alpha_3 if country is not None else None
