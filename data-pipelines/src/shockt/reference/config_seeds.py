"""Seeds generated from declared choices in `config/`, so the config file is the only place
they're edited."""

import csv
from pathlib import Path

from shockt.config import HsCodesConfig


def write_hs_case_codes(config: HsCodesConfig, path: Path) -> int:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["hs_prefix", "cases", "source"])
        for prefix in config.prefixes:
            writer.writerow([prefix.prefix, "|".join(prefix.cases), "config/hs_codes.yaml"])
    return len(config.prefixes)
