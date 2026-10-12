from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MonthRange:
    """An inclusive range of calendar months, each 'YYYY-MM'."""

    first: str
    last: str

    def __post_init__(self) -> None:
        for month in (self.first, self.last):
            year, _, number = month.partition("-")
            if len(month) != 7 or not year.isdigit() or not number.isdigit():
                raise ValueError(f"{month!r} is not a YYYY-MM month")
            if not 1 <= int(number) <= 12:
                raise ValueError(f"{month!r} is not a YYYY-MM month")
        if self.first > self.last:
            raise ValueError(f"month range starts {self.first}, after it ends {self.last}")

    @classmethod
    def resolve(cls, first: str, last: str | None, today: date) -> "MonthRange":
        """The range from `first` to `last`, or to `today`'s month when `last` is None."""
        return cls(first, last or f"{today:%Y-%m}")

    def years(self) -> range:
        return range(int(self.first[:4]), int(self.last[:4]) + 1)

    def in_year(self, year: int) -> "MonthRange":
        """The part of this range that falls in `year`."""
        if year not in self.years():
            raise ValueError(f"{year} is outside {self.first}..{self.last}")
        return MonthRange(max(self.first, f"{year}-01"), min(self.last, f"{year}-12"))

    def contains(self, day: date) -> bool:
        return self.first <= f"{day:%Y-%m}" <= self.last

    def whole_quarters(self) -> list[tuple[int, int]]:
        """(year, quarter) of every calendar quarter whose three months all fall in the range."""
        quarters = []
        for year in self.years():
            for quarter in range(1, 5):
                first = f"{year}-{3 * quarter - 2:02d}"
                last = f"{year}-{3 * quarter:02d}"
                if self.first <= first and last <= self.last:
                    quarters.append((year, quarter))
        return quarters

    def as_params(self) -> dict[str, str]:
        return {"first_month": self.first, "last_month": self.last}
