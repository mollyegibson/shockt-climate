"""ISO3 codes of the origin countries in `config/origins.yaml`, from the Census Schedule C seed."""

import csv
from pathlib import Path

from shockt.config import OriginsConfig
from shockt.settings import PROJECT_ROOT

COUNTRIES_SEED = PROJECT_ROOT / "dbt" / "seeds" / "seed_census_countries.csv"


class OriginsError(Exception):
    """The origin countries can't all be given ISO3 codes."""


def origin_iso3(origins: OriginsConfig, seed: Path = COUNTRIES_SEED) -> list[str]:
    """Sorted ISO3 codes of every Schedule C country in an origin region."""
    with seed.open(newline="") as f:
        countries = [row for row in csv.DictReader(f) if origins.region_of(row["census_cty_code"])]
    if not countries:
        raise OriginsError(f"no country in {seed.name} falls in an origin region")
    missing = [row["census_cty_code"] for row in countries if not row["iso3"]]
    if missing:
        raise OriginsError(f"origin countries without an ISO3 code in {seed.name}: {missing}")
    return sorted({row["iso3"] for row in countries})
