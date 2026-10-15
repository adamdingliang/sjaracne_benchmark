#!/usr/bin/env python3
"""Verify imported bytes, recovering retired LUAD duplicates from fixed Git history."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ADAPTABLE_DOCS = {
    "benchmarks/dream5_network1/README.md",
    "benchmarks/thp1_perturbseq/README.md",
    "benchmarks/thp1_perturbseq/AUTHOR_RECONSTRUCTION.md",
}
# The only retired imports are the three superseded LUAD acquisition files.
# Their immutable import commit remains in this repository's reachable history;
# no scientific result or workflow is eligible for this exception.
LUAD_RETIREMENT_COMMIT = "55f974555cb02eef53d7b1802c3b4e2e8c7d9b9e"
RETIRED_LUAD_REPLACEMENTS = {
    "archive/tcga_luad_gdc/README.md": "benchmarks/tcga_luad_download/README.md",
    "archive/tcga_luad_gdc/download_luad_star_counts.py":
        "benchmarks/tcga_luad_download/download_tcga_luad.py",
    "archive/tcga_luad_gdc/test_download_luad_star_counts.py":
        "benchmarks/tcga_luad_download/test_download_tcga_luad.py",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(checkout, *args, **kwargs):
    # Per-command exception for this explicitly selected local checkout only;
    # do not change the user's global Git configuration or trust all paths.
    return subprocess.check_output(["git", "-c", "safe.directory=" + checkout.resolve().as_posix(),
                                    "-C", str(checkout), *args], **kwargs)


def verify_retired(root, row):
    """Verify one explicitly retired duplicate without rebinding imported bytes."""
    relative = row["destination"]
    if relative not in RETIRED_LUAD_REPLACEMENTS:
        raise ValueError(f"Undeclared imported artifact retirement: {relative}")
    retirement = row.get("retirement")
    if not isinstance(retirement, dict):
        raise ValueError("Retired import lacks retirement metadata")
    expected = {
        "date": "2026-10-14",
        "replacement": RETIRED_LUAD_REPLACEMENTS[relative],
        "recovery_commit": LUAD_RETIREMENT_COMMIT,
        "recovery_path": relative,
    }
    if any(retirement.get(key) != value for key, value in expected.items()):
        raise ValueError(f"Retirement recovery or replacement differs from declared policy: {relative}")
    if not isinstance(retirement.get("reason"), str) or not retirement["reason"].strip():
        raise ValueError("Retired import lacks a retirement reason")
    if row["adapted_for_new_repo"] or row["source_sha256"] != row["imported_sha256"]:
        raise ValueError("Retirement cannot change an original imported artifact")
    old = root / relative
    if old.exists() or old.is_symlink():
        raise ValueError(f"Retired imported artifact is still present: {relative}")
    replacement = (root / expected["replacement"]).resolve(strict=True)
    if root.resolve() not in replacement.parents or not replacement.is_file():
        raise ValueError("Retirement replacement is not a file within the repository")
    content = git(root, "show", LUAD_RETIREMENT_COMMIT + ":" + relative)
    if hashlib.sha256(content).hexdigest() != row["imported_sha256"] or len(content) != row["bytes"]:
        raise ValueError(f"Retired imported artifact differs from immutable recovery snapshot: {relative}")


def verify(root=ROOT, source_workspace=None, finalize_docs=False, record_git_metadata=False, git_index=False):
    path = root / "provenance/import_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    paths, git_tables = set(), {}
    adapted, retired = [], []
    for row in manifest["files"]:
        relative = row["destination"]
        if relative in paths:
            raise ValueError("Duplicate imported destination")
        paths.add(relative)
        lifecycle = row.get("lifecycle", "active")
        if lifecycle not in {"active", "retired"}:
            raise ValueError("Unknown imported artifact lifecycle")
        if lifecycle == "retired":
            verify_retired(root, row)
            retired.append(relative)
        else:
            if "retirement" in row:
                raise ValueError("Active imported artifact has retirement metadata")
            file = (root / relative).resolve(strict=True)
            if root.resolve() not in file.parents:
                raise ValueError("Imported path escapes repository")
            current = digest(file)
            if finalize_docs and current != row["imported_sha256"]:
                if relative not in ADAPTABLE_DOCS:
                    raise ValueError(f"Only declared navigation documents may be adapted: {relative}")
                row.update(imported_sha256=current, bytes=file.stat().st_size, adapted_for_new_repo=True,
                           adaptation="Navigation/status/external-engine instructions only; source hash retained")
            if current != row["imported_sha256"] or file.stat().st_size != row["bytes"]:
                raise ValueError(f"Imported artifact changed: {relative}")
            if row["adapted_for_new_repo"]:
                if relative not in ADAPTABLE_DOCS:
                    raise ValueError("Undeclared source adaptation")
                adapted.append(relative)
            elif current != row["source_sha256"]:
                raise ValueError("Preserved file differs from original source")
        if source_workspace:
            source = source_workspace / row["source_checkout"] / row["source_relative_path"]
            if digest(source) != row["source_sha256"]:
                raise ValueError(f"Original source changed since import: {source}")
            if record_git_metadata and row.get("source_tracked"):
                checkout = row["source_checkout"]
                if checkout not in git_tables:
                    entries = git(source_workspace / checkout, "ls-files", "--stage", "-z").decode("utf-8")
                    git_tables[checkout] = {}
                    for entry in entries.split("\0"):
                        if entry:
                            metadata, name = entry.split("\t", 1)
                            mode, blob, _ = metadata.split()
                            git_tables[checkout][name] = (mode, blob)
                row["source_git_mode"], row["source_git_blob"] = git_tables[checkout][row["source_relative_path"]]
        if git_index:
            if lifecycle == "retired":
                if git(root, "ls-files", "--stage", "--", relative, text=True).strip():
                    raise ValueError(f"Retired imported artifact is still staged: {relative}")
                continue
            content = git(root, "show", ":" + relative)
            if hashlib.sha256(content).hexdigest() != row["imported_sha256"]:
                raise ValueError(f"Git filters changed imported bytes: {relative}")
            staged = git(root, "ls-files", "--stage", "--", relative, text=True)
            expected_mode = row.get("source_git_mode", "100644")
            if not staged.startswith(expected_mode + " "):
                raise ValueError(f"Git mode differs from original: {relative}")
    if finalize_docs or record_git_metadata:
        manifest["status"] = "verified_import"
        with path.open("w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
            stream.write("\n")
    retired_bytes = sum(row["bytes"] for row in manifest["files"] if row.get("lifecycle") == "retired")
    imported_bytes = sum(row["bytes"] for row in manifest["files"])
    return {"status": "pass", "files": len(paths), "active_files": len(paths) - len(retired),
            "retired_files": len(retired), "bytes": imported_bytes,
            "active_bytes": imported_bytes - retired_bytes, "retired_bytes": retired_bytes,
            "retired_destinations": retired, "adapted_navigation_documents": adapted,
            "originals_verified": source_workspace is not None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-workspace", type=Path)
    parser.add_argument("--finalize-adapted-docs", action="store_true",
                        help="Record only the three permitted navigation-document adaptations")
    parser.add_argument("--record-source-git-metadata", action="store_true")
    parser.add_argument("--git-index", action="store_true",
                        help="Verify staged active bytes/modes and absence of retired paths")
    args = parser.parse_args()
    if args.record_source_git_metadata and args.source_workspace is None:
        parser.error("Recording original Git metadata requires --source-workspace")
    print(json.dumps(verify(source_workspace=args.source_workspace, finalize_docs=args.finalize_adapted_docs,
                            record_git_metadata=args.record_source_git_metadata, git_index=args.git_index)))
