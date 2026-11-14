"""Shared helper for reading FIRMS zip archives in the rule-check scripts."""
import pathlib
import shutil


def extract_csv(z, name, tmp):
    """Copy one zip member to a fixed file name inside tmp.

    The member's own name is never used as a path, so entries like '../x' or
    '/etc/x' cannot write outside tmp, and a quote in the name cannot break the
    SQL string the path is placed in.
    """
    dest = pathlib.Path(tmp) / "member.csv"
    with z.open(name) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out)
    return dest
