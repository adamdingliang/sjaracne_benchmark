#!/usr/bin/env python3
"""One-shot byte-preserving import of the retired engine benchmark tree."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "edf7a2fdf3c5ff866f4fea30fe1ca010c00e6a3a"
FOLDERS = {
    "adjacency_lookup", "ap_quadrant_scatter", "ap_workspace",
    "compact_adjacency", "dpi_intersection", "dpi_skip", "rank_cache",
    "unused_bandwidth", "without_replacement_sampling",
}


def git(checkout, *arguments):
    return subprocess.check_output([
        "git", "-c", "safe.directory=" + checkout.resolve().as_posix(),
        "-C", str(checkout), *arguments,
    ])


def safe_destination(relative):
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or "\\" in relative:
        raise ValueError("Unsafe archive destination")
    target = ROOT.joinpath(*parts.parts)
    if not target.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Archive destination escapes repository")
    for parent in (target, *target.parents):
        if parent == ROOT:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("Archive destination contains a link")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-repo", required=True, type=Path)
    args = parser.parse_args()
    engine = args.engine_repo.resolve(strict=True)
    manifest_path = ROOT / "provenance/engine_archive_manifest.json"
    if manifest_path.exists():
        raise FileExistsError("Archive manifest exists; never overwrite an earlier import")
    tree = git(engine, "ls-tree", "-r", "-z", "--full-tree", SOURCE_COMMIT,
               "--", "benchmarks/")
    entries = []
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        metadata, source = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split()
        source = source.decode("utf-8")
        if mode != "100644" or kind != "blob":
            raise ValueError("Unexpected non-regular archive entry")
        relative = source.removeprefix("benchmarks/")
        if relative.split("/", 1)[0] not in FOLDERS:
            raise ValueError("Unexpected engine benchmark folder")
        entries.append((source, "engine_performance/" + relative, mode, blob, False))
    if len(entries) != 60 or {row[0].split("/")[1] for row in entries} != FOLDERS:
        raise ValueError("Expected exactly the pinned 60 files across nine folders")
    test_source = "tests/test_rank_benchmark_generator.py"
    metadata = git(engine, "ls-tree", SOURCE_COMMIT, "--", test_source).split(b"\t", 1)[0]
    mode, kind, blob = metadata.decode("ascii").split()
    if mode != "100644" or kind != "blob":
        raise ValueError("Unexpected mixed test module entry")
    entries.append((test_source,
                    "engine_performance/provenance/test_rank_benchmark_generator.py.txt",
                    mode, blob, True))

    # Validate and load the whole small snapshot before creating any outputs.
    pending = []
    for source, destination, mode, blob, source_test in entries:
        target = safe_destination(destination)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Refuse to overwrite {target}")
        content = git(engine, "show", SOURCE_COMMIT + ":" + source)
        if len(content) >= 50 * 1024**2:
            raise ValueError("Unexpected large source artifact")
        git_object = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
        if hashlib.sha1(git_object).hexdigest() != blob:
            raise ValueError("Source content differs from pinned Git blob")
        row = {"source_path": source, "destination": destination,
               "git_mode": mode, "git_blob": blob, "bytes": len(content),
               "sha256": hashlib.sha256(content).hexdigest()}
        pending.append((target, content, row, source_test))

    files, source_tests = [], []
    for target, content, row, source_test in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)
        if hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Imported content failed verification")
        (source_tests if source_test else files).append(row)
    manifest = {
        "schema": 1,
        "migration_date": "2026-10-14",
        "source_repository": "https://github.com/adamdingliang/SJARACNe",
        "source_commit": SOURCE_COMMIT,
        "notes": [
            "Exact Git blob bytes, not checkout line-ending conversions.",
            "Historical native runners retain their original paths and assumptions.",
            "The mixed source test module is retained as text; runnable generator tests are split separately.",
            "Engine numerical regression fixtures remain independently in engine tests.",
        ],
        "files": files,
        "source_tests": source_tests,
    }
    with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "imported", "files": len(files),
                      "source_tests": len(source_tests),
                      "bytes": sum(row["bytes"] for row in files)}))


if __name__ == "__main__":
    main()
