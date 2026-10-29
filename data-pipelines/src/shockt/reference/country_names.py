"""Concordance of country-name variants → ISO 3166-1 alpha-3 codes, from three sources:

1. ISO 3166 (`pycountry`): the `name`, `official_name` and `common_name` of each entry.
2. Census Schedule C (`seed_census_countries.csv`): the `cty_name` for each country with an ISO3.
3. Config overrides (`config/sources.yaml` → `country_names.overrides`): source-specific spellings
   that neither ISO 3166 nor Census provides, such as "Ivory Coast" (CBAM) for CIV.
"""

import csv
from collections.abc import Mapping
from pathlib import Path

import pycountry


class CountryNameError(Exception):
    """The concordance has a conflict or an unverifiable override."""


def _iso3166_names() -> dict[str, str]:
    """Every name variant in ISO 3166-1 → alpha-3, from pycountry."""
    names: dict[str, str] = {}
    for country in pycountry.countries:
        iso3 = country.alpha_3
        for attr in ("name", "official_name", "common_name"):
            value = getattr(country, attr, None)
            if value is not None:
                _add(names, value, iso3, "ISO 3166")
    return names


def _census_names(seed_path: Path) -> dict[str, str]:
    """Census Schedule C country names → ISO3, from the existing seed."""
    names: dict[str, str] = {}
    with seed_path.open() as f:
        for row in csv.DictReader(f):
            iso3 = row["iso3"].strip()
            name = row["cty_name"].strip()
            if iso3 and name:
                _add(names, name, iso3, "Census Schedule C")
    return names


def _add(names: dict[str, str], name: str, iso3: str, source: str) -> None:
    existing = names.get(name)
    if existing is not None and existing != iso3:
        raise CountryNameError(f"{name!r} maps to {existing} and {iso3} ({source})")
    names[name] = iso3


def generate(census_seed: Path, overrides: Mapping[str, str]) -> list[tuple[str, str, str]]:
    """Rows of (variant_name, iso3, source) for the concordance seed."""
    iso_names = _iso3166_names()
    census_names = _census_names(census_seed)

    rows: dict[str, tuple[str, str]] = {}
    for name, iso3 in iso_names.items():
        rows[name] = (iso3, "iso_3166")
    for name, iso3 in census_names.items():
        if name in rows:
            if rows[name][0] != iso3:
                raise CountryNameError(
                    f"Census name {name!r} maps to {iso3} but ISO 3166 says {rows[name][0]}"
                )
        else:
            rows[name] = (iso3, "census_schedule_c")
    for name, iso3 in overrides.items():
        if name in rows and rows[name][0] != iso3:
            raise CountryNameError(
                f"Override {name!r} → {iso3} conflicts with "
                f"existing {rows[name][0]} ({rows[name][1]})"
            )
        if pycountry.countries.get(alpha_3=iso3) is None:
            raise CountryNameError(f"Override {name!r} → {iso3}: {iso3} is not a valid ISO3 code")
        rows[name] = (iso3, "config_override")

    return sorted(
        [(name, iso3, source) for name, (iso3, source) in rows.items()],
        key=lambda r: (r[1], r[0]),
    )


def write(rows: list[tuple[str, str, str]], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["variant_name", "iso3", "source"])
        for row in rows:
            writer.writerow(row)
