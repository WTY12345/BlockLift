'''Fetch the CoRe inputs listed in the SRIP artifact at its pinned commit.'''
from concurrent.futures import ThreadPoolExecutor
import csv
from pathlib import Path, PurePosixPath
from shutil import copyfileobj
from time import sleep
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent / "benchmark"
SOURCE = "https://raw.githubusercontent.com/TakehideSoh/KR2026/df807b6b6ea66b7ec37a5371c58967eecc5ce762/"


def download(relative):
    target = ROOT / "instances" / relative
    if target.is_file() and target.stat().st_size:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    upstream = PurePosixPath("benchmark/instances", *relative.parts[1:])
    request = Request(SOURCE + quote(upstream.as_posix()), headers={"User-Agent": "BlockLift-reproduction"})
    for retry in range(3):
        try:
            with urlopen(request, timeout=90) as response, partial.open("wb") as out:
                copyfileobj(response, out, length=1024 * 1024)
            partial.replace(target)
            return
        except OSError:
            partial.unlink(missing_ok=True)
            if retry == 2:
                raise
            sleep(2 ** retry)


def main():
    with (ROOT / "core-693.csv").open(encoding="utf-8-sig", newline="") as source:
        manifest = list(csv.reader(source))
    if len(manifest) != 693 or len({tuple(row) for row in manifest}) != 693:
        raise ValueError("Expected 693 unique case pairs")
    paths = sorted({PurePosixPath(name) for pair in manifest for name in pair})
    if any(not p.parts or p.parts[0] != "benchmark" or ".." in p.parts for p in paths):
        raise ValueError("Unexpected path in the case list")
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i, _ in enumerate(pool.map(download, paths), start=1):
            if i % 100 == 0 or i == len(paths):
                print(f"{i}/{len(paths)} input files ready", flush=True)


if __name__ == "__main__":
    main()
