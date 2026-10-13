"""ISO codes of the origin countries in `config/origins.yaml`, from the Census Schedule C seed."""

import csv
from pathlib import Path
from typing import Literal

from shockt.config import OriginsConfig
from shockt.settings import PROJECT_ROOT

COUNTRIES_SEED = PROJECT_ROOT / "dbt" / "seeds" / "seed_census_countries.csv"


class OriginsError(Exception):
    """The origin countries can't all be given ISO codes."""


def origin_iso3(origins: OriginsConfig, seed: Path = COUNTRIES_SEED) -> list[str]:
    """Sorted ISO3 codes of every Schedule C country in an origin region."""
    return _origin_codes(origins, seed, "iso3")


def origin_iso2(origins: OriginsConfig, seed: Path = COUNTRIES_SEED) -> list[str]:
    """Sorted ISO2 codes of every Schedule C country in an origin region."""
    return _origin_codes(origins, seed, "iso2")


def _origin_codes(origins: OriginsConfig, seed: Path, column: Literal["iso2", "iso3"]) -> list[str]:
    with seed.open(newline="") as f:
        countries = [row for row in csv.DictReader(f) if origins.region_of(row["census_cty_code"])]
    if not countries:
        raise OriginsError(f"no country in {seed.name} falls in an origin region")
    missing = [row["census_cty_code"] for row in countries if not row[column]]
    if missing:
        raise OriginsError(
            f"origin countries without an {column.upper()} code in {seed.name}: {missing}"
        )
    return sorted({row[column] for row in countries})
