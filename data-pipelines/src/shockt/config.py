from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from shockt.settings import PROJECT_ROOT

CONFIG_DIR = PROJECT_ROOT / "config"

CensusDataset = Literal["hs", "porths", "statehs"]


class DateRange(BaseModel):
    start_month: str
    end_month: str | None = None


class CountryFilter(BaseModel):
    """Keep only countries whose Census code starts with one of `code_prefixes` or is in `codes`."""

    code_prefixes: list[str] = []
    codes: list[str] = []


class CensusRowFilter(BaseModel):
    """Rows dropped as a Census response is parsed into raw."""

    drop_country_groups: bool
    drop_all_zero: bool
    countries: CountryFilter | None = None


class CensusApiConfig(BaseModel):
    base_url: str
    comm_lvl: dict[CensusDataset, str]
    timeout_seconds: float
    filters: dict[CensusDataset, CensusRowFilter]


class SourcesConfig(BaseModel):
    """The parts of `config/sources.yaml` the loaders read so far; other sections are ignored."""

    date_range: DateRange
    census_api: CensusApiConfig


class HsPrefix(BaseModel):
    prefix: str
    level: str
    label: str
    cases: list[str]


class HsCodesConfig(BaseModel):
    prefixes: list[HsPrefix]


def _load_yaml(path: Path) -> object:
    with path.open() as f:
        return yaml.safe_load(f)


@cache
def sources_config() -> SourcesConfig:
    return SourcesConfig.model_validate(_load_yaml(CONFIG_DIR / "sources.yaml"))


@cache
def hs_codes_config() -> HsCodesConfig:
    return HsCodesConfig.model_validate(_load_yaml(CONFIG_DIR / "hs_codes.yaml"))
