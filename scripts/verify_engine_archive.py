#!/usr/bin/env python3
"""Verify the byte-preserved engine-performance archive and its pinned provenance.

The optional source check reads immutable Git objects, never the source worktree.
The index check validates staged objects before a commit, including Git file modes.
Neither operation changes files, Git configuration, or the supplied manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "edf7a2fdf3c5ff866f4fea30fe1ca010c00e6a3a"
SOURCE_REPOSITORY = "https://github.com/adamdingliang/SJARACNe"
MIGRATION_DATE = "2026-10-14"
ARCHIVE = "engine_performance"
MANIFEST = "provenance/engine_archive_manifest.json"
SOURCE_TEST = "tests/test_rank_benchmark_generator.py"
TEST_DESTINATION = ARCHIVE + "/provenance/test_rank_benchmark_generator.py.txt"
EXPECTED_SOURCES = frozenset("benchmarks/" + relative for relative in """
adjacency_lookup/README.md
adjacency_lookup/generate_dense_adjacency.py
adjacency_lookup/raw_timings.csv
adjacency_lookup/run_benchmark.py
ap_quadrant_scatter/RESULTS_2026-08-08.md
ap_quadrant_scatter/raw_timings_2026-08-08.csv
ap_quadrant_scatter/summary_2026-08-08.csv
ap_workspace/RESULTS_2026-08-08.md
ap_workspace/raw_timings_2026-08-08.csv
ap_workspace/summary_2026-08-08.csv
compact_adjacency/README.md
compact_adjacency/RESULTS_2026-08-08.md
compact_adjacency/raw_timings.csv
compact_adjacency/run_benchmark.py
compact_adjacency/run_metadata.json
compact_adjacency/summary.csv
dpi_intersection/README.md
dpi_intersection/differential_fuzz.py
dpi_intersection/generate_benchmarks.py
dpi_intersection/raw_timings.csv
dpi_intersection/run_benchmark.py
dpi_intersection/summary.csv
dpi_skip/README.md
dpi_skip/generate_single_source_adjacency.py
dpi_skip/raw_timings.csv
rank_cache/README.md
rank_cache/RESULTS_2026-08-07.md
rank_cache/figures/rank_cache_memory_overhead.png
rank_cache/figures/rank_cache_memory_overhead.svg
rank_cache/figures/rank_cache_runtime_sweeps.png
rank_cache/figures/rank_cache_runtime_sweeps.svg
rank_cache/figures/rank_cache_speedup_sweeps.png
rank_cache/figures/rank_cache_speedup_sweeps.svg
rank_cache/fixtures/mixed_quadrant_counts.exp
rank_cache/fixtures/mixed_quadrant_hub.txt
rank_cache/fixtures/tied_conditional_bootstrap_seed17_reference.tsv
rank_cache/fixtures/tied_counts.exp
rank_cache/fixtures/tied_hubs.txt
rank_cache/fixtures/tied_seed17_reference.tsv
rank_cache/plot_rank_cache_results.py
rank_cache/prepare_rank_benchmarks.py
rank_cache/raw_timings_2026-08-07.csv
rank_cache/results_2026-08-07.csv
rank_cache/spec.json
unused_bandwidth/README.md
unused_bandwidth/raw_timings_2026-08-08.csv
unused_bandwidth/results_2026-08-08.csv
unused_bandwidth/run_benchmark.py
unused_bandwidth/validate_outputs.py
without_replacement_sampling/README.md
without_replacement_sampling/apmi_duplicate_partition_comparison.png
without_replacement_sampling/brca100_duplicate_permuted_null_summary.json
without_replacement_sampling/brca100_duplicate_real_summary.json
without_replacement_sampling/brca100_null_apmi_results.json
without_replacement_sampling/brca100_null_apmi_summary.csv
without_replacement_sampling/brca100_null_apmi_vs_m.png
without_replacement_sampling/brca100_subsample_per_run_metrics.csv
without_replacement_sampling/brca100_subsample_size_results.json
without_replacement_sampling/brca100_subsample_size_summary.csv
without_replacement_sampling/brca100_subsample_size_tradeoff.png
""".split())
EXPECTED_FOLDERS = frozenset(PurePosixPath(path).parts[1] for path in EXPECTED_SOURCES)


def git_blob(content):
    """Git's SHA-1 blob identifier includes the object header, not just bytes."""
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()


def _relative(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or "\0" in value or any(part in {"", ".", ".."} for part in value.split("/"))
            or PurePosixPath(value).is_absolute()):
        raise ValueError(f"Noncanonical or escaping archive path: {value!r}")
    return value


def _reject_link(path):
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise ValueError(f"Archive path must not be a symlink or junction: {path}")


def _file(root, relative):
    relative = _relative(relative)
    candidate = root
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        _reject_link(candidate)
    if not candidate.is_file():
        raise ValueError(f"Missing archive file: {relative}")
    resolved = candidate.resolve(strict=True)
    if root not in resolved.parents:
        raise ValueError(f"Archive path escapes repository: {relative}")
    return candidate


def _git(checkout, *arguments, input=None):
    checkout = checkout.resolve()
    return subprocess.check_output(
        ["git", "-c", "safe.directory=" + checkout.as_posix(), "-C", str(checkout), *arguments],
        input=input,
    )


def _blobs(checkout, identifiers):
    identifiers = sorted(set(identifiers))
    output = io.BytesIO(_git(checkout, "cat-file", "--batch",
                           input=("\n".join(identifiers) + "\n").encode("ascii")))
    result = {}
    for expected in identifiers:
        header = output.readline().rstrip(b"\n").split()
        if len(header) != 3 or header[0].decode("ascii") != expected or header[1] != b"blob":
            raise ValueError("Missing or non-blob Git archive object")
        try:
            size = int(header[2])
        except ValueError as error:
            raise ValueError("Malformed Git blob size") from error
        content = output.read(size)
        if len(content) != size or output.read(1) != b"\n" or git_blob(content) != expected:
            raise ValueError("Git archive blob content differs from its identifier")
        result[expected] = content
    if output.read():
        raise ValueError("Unexpected data after Git archive objects")
    return result


def _validate_content(row, content, label):
    if (len(content) != row["bytes"] or hashlib.sha256(content).hexdigest() != row["sha256"]
            or git_blob(content) != row["git_blob"]):
        raise ValueError(f"Archive bytes, SHA-256, or Git blob differ: {label}")


def _archive_files(root):
    """Reject extras and links in the nine byte-preserved archival subtrees."""
    archive = root / ARCHIVE
    _reject_link(archive)
    if not archive.is_dir():
        raise ValueError("Missing engine-performance archive")
    for child in archive.iterdir():
        _reject_link(child)
        if child.name == "README.md" and child.is_file():
            continue
        if child.name not in EXPECTED_FOLDERS | {"tests", "provenance"} or not child.is_dir():
            raise ValueError(f"Unexpected top-level archive entry: {child.name}")
    result = set()
    for folder in EXPECTED_FOLDERS:
        directory = archive / folder
        if not directory.is_dir():
            raise ValueError(f"Missing archive directory: {folder}")
        pending = [directory]
        while pending:
            for entry in pending.pop().iterdir():
                _reject_link(entry)
                if entry.is_dir():
                    pending.append(entry)
                elif entry.is_file():
                    result.add(entry.relative_to(root).as_posix())
                else:
                    raise ValueError(f"Nonregular archive entry: {entry}")
    return result


def _check_git(root, rows, engine_repo, git_index):
    if engine_repo is not None:
        tree = _git(engine_repo, "ls-tree", "-r", "-z", "--full-tree", SOURCE_COMMIT,
                    "--", "benchmarks", SOURCE_TEST)
        source = {}
        for entry in tree.split(b"\0"):
            if entry:
                metadata, raw_path = entry.split(b"\t", 1)
                mode, kind, blob = metadata.decode("ascii").split()
                path = raw_path.decode("utf-8")
                if kind != "blob":
                    raise ValueError(f"Pinned source is not a blob: {path}")
                source[path] = (mode, blob)
        if set(source) != EXPECTED_SOURCES | {SOURCE_TEST}:
            raise ValueError("Pinned engine source file set differs from the declared 60-file archive")
        contents = _blobs(engine_repo, (entry[1] for entry in source.values()))
        for row in rows:
            if source[row["source_path"]] != (row["git_mode"], row["git_blob"]):
                raise ValueError(f"Pinned source Git metadata differs: {row['source_path']}")
            _validate_content(row, contents[row["git_blob"]], row["source_path"])
    if git_index:
        index = {}
        for entry in _git(root, "ls-files", "--stage", "-z", "--", ARCHIVE, MANIFEST).split(b"\0"):
            if entry:
                metadata, raw_path = entry.split(b"\t", 1)
                mode, blob, stage = metadata.decode("ascii").split()
                path = raw_path.decode("utf-8")
                if stage != "0":
                    raise ValueError(f"Archive index has an unresolved merge: {path}")
                index[path] = (mode, blob)
        expected = {row["destination"] for row in rows}
        for path in index:
            parts = PurePosixPath(path).parts
            if len(parts) > 1 and parts[1] in EXPECTED_FOLDERS and path not in expected:
                raise ValueError(f"Unmanifested archive file remains in Git index: {path}")
        for row in rows:
            if index.get(row["destination"]) != (row["git_mode"], row["git_blob"]):
                raise ValueError(f"Staged archive bytes or mode differ: {row['destination']}")
        manifest_content = _file(root, MANIFEST).read_bytes()
        manifest_blob = git_blob(manifest_content)
        if index.get(MANIFEST) != ("100644", manifest_blob):
            raise ValueError("Staged archive manifest differs from the verified working manifest")
        contents = _blobs(root, [row["git_blob"] for row in rows] + [manifest_blob])
        if contents[manifest_blob] != manifest_content:
            raise ValueError("Staged archive manifest bytes differ")
        for row in rows:
            _validate_content(row, contents[row["git_blob"]], row["destination"])


def verify(root=ROOT, engine_repo=None, git_index=False):
    root = Path(root).resolve(strict=True)
    manifest = json.loads(_file(root, MANIFEST).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Archive manifest must be an object")
    pinned = {"schema": 1, "migration_date": MIGRATION_DATE,
              "source_repository": SOURCE_REPOSITORY, "source_commit": SOURCE_COMMIT}
    if any(manifest.get(key) != value for key, value in pinned.items()) or type(manifest.get("schema")) is not int:
        raise ValueError("Archive manifest schema, migration date, repository, or source pin differs")
    if (not isinstance(manifest.get("files"), list) or len(manifest["files"]) != 60
            or not isinstance(manifest.get("source_tests"), list) or len(manifest["source_tests"]) != 1):
        raise ValueError("Archive requires exactly 60 original benchmark files and one original test snapshot")
    rows = manifest["files"] + manifest["source_tests"]
    sources, destinations = set(), set()
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("Archive file record must be an object")
        required = {"source_path", "destination", "git_mode", "git_blob", "bytes", "sha256"}
        if not required <= row.keys():
            raise ValueError("Archive file record lacks required provenance fields")
        source, destination = _relative(row["source_path"]), _relative(row["destination"])
        if source in sources or destination in destinations:
            raise ValueError("Duplicate archive source or destination")
        sources.add(source)
        destinations.add(destination)
        if position < 60:
            if source not in EXPECTED_SOURCES or destination != ARCHIVE + "/" + source.removeprefix("benchmarks/"):
                raise ValueError(f"Undeclared archive source or destination mapping: {source}")
        elif source != SOURCE_TEST or destination != TEST_DESTINATION:
            raise ValueError("Original test snapshot path differs from the declared policy")
        if (row["git_mode"] != "100644" or type(row["bytes"]) is not int or row["bytes"] < 0
                or not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
                or not isinstance(row["git_blob"], str) or not re.fullmatch(r"[0-9a-f]{40}", row["git_blob"])):
            raise ValueError(f"Invalid archive mode, size, or digest metadata: {source}")
        _validate_content(row, _file(root, destination).read_bytes(), destination)
    if sources != EXPECTED_SOURCES | {SOURCE_TEST}:
        raise ValueError("Archive source set differs from the declared migration")
    archive_destinations = {row["destination"] for row in manifest["files"]}
    if _archive_files(root) != archive_destinations:
        raise ValueError("Archive has missing or unmanifested files in its nine original directories")
    _check_git(root, rows, Path(engine_repo) if engine_repo is not None else None, git_index)
    return {"status": "pass", "files": 60, "source_tests": 1, "folders": len(EXPECTED_FOLDERS),
            "bytes": sum(row["bytes"] for row in manifest["files"]),
            "source_test_bytes": manifest["source_tests"][0]["bytes"],
            "source_verified": engine_repo is not None, "git_index_verified": bool(git_index)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-repo", type=Path, help="Verify original objects at the fixed source commit")
    parser.add_argument("--git-index", action="store_true", help="Verify staged Git bytes and modes")
    arguments = parser.parse_args()
    try:
        print(json.dumps(verify(engine_repo=arguments.engine_repo, git_index=arguments.git_index)))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Archive verification failed: {error}\n")
