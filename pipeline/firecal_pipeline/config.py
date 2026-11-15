"""Load firecal.toml and resolve paths.

Paths in the file are relative to the folder holding it: the repo root, or $FIRECAL_ROOT when set
(the API reads the same variable). scripts/check.sh points it at pipeline/tests/fixture/.
"""
import os
import pathlib
import tomllib
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    raw: dict
    base: pathlib.Path = ROOT

    @classmethod
    def load(cls, path: pathlib.Path | None = None) -> "Config":
        if path is None:
            path = pathlib.Path(os.environ.get("FIRECAL_ROOT") or ROOT) / "firecal.toml"
        path = path.resolve()
        return cls(tomllib.loads(path.read_text()), path.parent)

    def __getitem__(self, key):
        return self.raw[key]

    @property
    def raw_dir(self) -> pathlib.Path:
        return self.base / self.raw["data"]["raw_dir"]

    @property
    def out(self) -> pathlib.Path:
        return self.base / self.raw["data"]["out_dir"]

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
