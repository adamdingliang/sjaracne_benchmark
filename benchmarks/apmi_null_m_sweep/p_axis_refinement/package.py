#!/usr/bin/env python3
"""Package only compact, hash-verified refinement artifacts and execution code.

No generator, fitting routine, or large data copy is invoked. Snapshot paths are
repository-relative POSIX paths and retain their hierarchy under execution_code.
Every input is verified before the output directory is created.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil


FORMAT = "apmi-p-axis-refinement-v1"
OUTPUT_FILES = ("extraction.json", "predictions.json", "knot_diagnostics.json",
                "evaluation.csv", "old_result_reproduction.json", "summary.csv",
                "per_probability.csv", "refinement.png", "refinement.svg")
FILES = ("request.json", "completion.json") + OUTPUT_FILES
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _regular_file(root, relative):
    """Reject links/junctions or missing/non-file snapshot components."""
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("artifact paths must not contain links or junctions")
    if not current.is_file():
        raise ValueError("required artifact is not a regular file")
    return current


def _snapshot_relative(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("snapshot names must be safe repository-relative POSIX paths")
    relative = PurePosixPath(name)
    if (relative.is_absolute() or relative.as_posix() != name or
            any(part in (".", "..") for part in relative.parts) or
            relative.suffix not in (".py", ".md")):
        raise ValueError("snapshot names must be safe source-code paths")
    return relative


def _digest_matches(path, expected):
    return isinstance(expected, str) and _SHA256.fullmatch(expected) and sha256(path) == expected


def _exact_integer(mapping, name, expected):
    return type(mapping.get(name)) is int and mapping[name] == expected


def package(run, out):
    run, out = Path(run).resolve(strict=True), Path(out).resolve()
    if (not run.is_dir() or out.exists() or out == run or
            out.is_relative_to(run) or run.is_relative_to(out)):
        raise ValueError("package must be a new, nonoverlapping output directory")
    paths = {name: _regular_file(run, PurePosixPath(name)) for name in FILES}
    request = _read_json(paths["request.json"])
    completion = _read_json(paths["completion.json"])
    if not isinstance(request, dict) or not isinstance(completion, dict):
        raise ValueError("request and completion must be objects")
    if request.get("format") != FORMAT or completion.get("format") != FORMAT:
        raise ValueError("incorrect refinement artifact format")
    for metadata in (request, completion):
        if (not _exact_integer(metadata, "new_null_draws", 0) or
                not _exact_integer(metadata, "new_large_copies", 0)):
            raise ValueError("not a no-generation, no-large-copy refinement")
    expected_counts = {"m_count": 19, "query_probability_count": 49,
                       "evaluation_rows": 16758, "prediction_count": 8379}
    if any(not _exact_integer(completion, key, count) for key, count in expected_counts.items()):
        raise ValueError("not a complete nineteen-size, 49-probability refinement")
    if not _digest_matches(paths["request.json"], completion.get("request_sha256")):
        raise ValueError("request hash mismatch")
    output_hashes = completion.get("outputs_sha256")
    if not isinstance(output_hashes, dict) or set(output_hashes) != set(OUTPUT_FILES):
        raise ValueError("compact output hashes must cover exactly the output whitelist")
    for name in OUTPUT_FILES:
        if not _digest_matches(paths[name], output_hashes[name]):
            raise ValueError("compact output hash mismatch")
    code_hashes = request.get("code_sha256")
    if not isinstance(code_hashes, dict) or not code_hashes:
        raise ValueError("execution code hashes are required")
    code_paths = {}
    snapshot_root = run / "execution_code"
    if snapshot_root.is_symlink() or (hasattr(snapshot_root, "is_junction") and snapshot_root.is_junction()):
        raise ValueError("execution snapshot root must not be a link or junction")
    for name, digest in code_hashes.items():
        relative = _snapshot_relative(name)
        path = _regular_file(snapshot_root, relative)
        if not _digest_matches(path, digest):
            raise ValueError("execution snapshot code hash mismatch")
        code_paths[name] = path

    # No writes occur before this point. Only the explicit compact whitelist and
    # request-pinned source snapshots are copied, not arbitrary run-directory data.
    out.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(paths[name], out / name)
    for name, source in code_paths.items():
        target = out / "execution_code" / Path(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256(target) != code_hashes[name]:
            raise ValueError("copied execution snapshot hash mismatch")
    for name in OUTPUT_FILES:
        if sha256(out / name) != output_hashes[name]:
            raise ValueError("copied compact output hash mismatch")
    if sha256(out / "request.json") != completion["request_sha256"]:
        raise ValueError("copied request hash mismatch")
    manifest = {path.relative_to(out).as_posix(): sha256(path)
                for path in sorted(out.rglob("*")) if path.is_file()}
    with (out / "package_sha256.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    package(args.run, args.out)
