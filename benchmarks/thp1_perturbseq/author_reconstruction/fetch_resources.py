#!/usr/bin/env python3
"""Fetch only the pinned annotation and three official SuperCell core sources.

This is not a package installer. Files are checked against SHA256 before any
resource is written; an existing output directory is never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


def fetch(output: Path, pins_path: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing existing resource directory: {output}")
    pins = json.loads(pins_path.read_text(encoding="utf-8"))
    downloads = []
    for resource in pins["resources"]:
        name = resource["filename"]
        if Path(name).name != name:
            raise ValueError("Pinned resource filename must be a basename")
        request = Request(resource["url"], headers={"User-Agent": "SJARACNe-THP1-reconstruction"})
        with urlopen(request, timeout=120) as response:
            payload = response.read()
        observed = hashlib.sha256(payload).hexdigest()
        if observed != resource["sha256"]:
            raise ValueError(f"SHA256 mismatch for {name}: {observed}")
        downloads.append((resource, payload))
    output.mkdir(parents=True, exist_ok=False)
    for resource, payload in downloads:
        with (output / resource["filename"]).open("xb") as handle:
            handle.write(payload)
    manifest = {
        "source_pins_sha256": hashlib.sha256(pins_path.read_bytes()).hexdigest(),
        "resources": [dict(resource, size_bytes=len(payload)) for resource, payload in downloads],
    }
    with (output / "resource_manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh resource directory")
    parser.add_argument("--pins", type=Path, default=Path(__file__).with_name("source_pins.json"))
    args = parser.parse_args()
    manifest = fetch(args.output.resolve(), args.pins.resolve(strict=True))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
