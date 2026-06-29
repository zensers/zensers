import tomllib
from pathlib import Path

__version__ = tomllib.load(
    (Path(__file__).resolve().parent.parent / "pyproject.toml").open("rb")
)["project"]["version"]
