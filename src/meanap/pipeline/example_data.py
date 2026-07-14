"""Download the shared example dataset used by the MATLAB and Python test pipelines.

Mirrors ``downloadExampleData.m`` (Dropbox source only).
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Callable

DROPBOX_LINKS = {
    "exampleData.csv": "https://www.dropbox.com/scl/fi/w3no80utz1onjf5d6tu1n/exampleData.csv?rlkey=xm80c5pr1xrgvwngitrez9fw2&st=ie22e58n&dl=1",
    "NGN2_20230208_P1_DIV14_A2.mat": "https://www.dropbox.com/scl/fi/0puoqefido0yef12roxlu/NGN2_20230208_P1_DIV14_A2.mat?rlkey=ap7ipbzgh2vqkf3b1e57wzxns&st=2xs1h1ci&dl=1",
    "NGN2_20230208_P1_DIV14_A3.mat": "https://www.dropbox.com/scl/fi/wduekpzvrmqc16h6ima1h/NGN2_20230208_P1_DIV14_A3.mat?rlkey=4agamhx7r8u6d5shxfugoiwaj&st=r22bpn2u&dl=1",
}


def download_example_data(home_dir: Path, log: Callable[[str], None] | None = None) -> Path:
    """Download the example recordings into ``home_dir/ExampleData``.

    Skips files that already exist. Returns the path to the ExampleData folder.
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)

    example_dir = Path(home_dir) / "ExampleData"
    example_dir.mkdir(parents=True, exist_ok=True)

    for name, url in DROPBOX_LINKS.items():
        dest = example_dir / name
        if dest.exists():
            _log(f"  already present: {name}")
            continue
        _log(f"  downloading {name} …")
        urllib.request.urlretrieve(url, dest)
        _log(f"  done: {name}")

    return example_dir
