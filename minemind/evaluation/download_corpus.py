"""Download the public DGMS benchmark corpus without committing source PDFs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SOURCES_PATH = ROOT / "corpus" / "sources.json"
RAW_DIR = ROOT / "corpus" / "raw"


def load_sources() -> list[dict[str, str]]:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))["sources"]


def download(source: dict[str, str], overwrite: bool) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destination = RAW_DIR / source["filename"]
    if destination.exists() and not overwrite:
        print(f"SKIP  {destination.name} (already exists)")
        return
    request = Request(source["url"], headers={"User-Agent": "MineMind-retrieval-evaluation/1.0 (academic benchmark)"})
    print(f"GET   {source['title']}")
    with urlopen(request, timeout=90) as response:
        body = response.read()
    if len(body) < 1_000 or not body.startswith(b"%PDF"):
        raise RuntimeError(f"{source['title']} did not return a usable PDF from {source['url']}")
    destination.write_bytes(body)
    print(f"SAVED {destination.name} ({len(body):,} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()
    for source in load_sources():
        download(source, overwrite=args.force)


if __name__ == "__main__":
    main()
