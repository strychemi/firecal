"""Load firecal.toml and resolve paths."""
import pathlib
import tomllib
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    raw: dict

    @classmethod
    def load(cls, path: pathlib.Path | None = None) -> "Config":
        return cls(tomllib.loads((path or ROOT / "firecal.toml").read_text()))

    def __getitem__(self, key):
        return self.raw[key]

    @property
    def raw_dir(self) -> pathlib.Path:
        return ROOT / self.raw["data"]["raw_dir"]

    @property
    def out(self) -> pathlib.Path:
        return ROOT / self.raw["data"]["out_dir"]

    def dir(self, name: str) -> pathlib.Path:
        p = self.out / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def bbox(self) -> list[float]:
        return self.raw["data"]["clip_bbox"]

    @property
    def calibration_years(self) -> list[int]:
        h = self.raw["harmonization"]
        return list(range(h["calibration_first_year"], h["calibration_last_year"] + 1))


def connect(path=":memory:"):
    import duckdb
    con = duckdb.connect(str(path))
    try:
        con.execute("LOAD h3")  # already installed: no network needed
    except duckdb.Error:
        con.execute("INSTALL h3 FROM community; LOAD h3;")
    return con
