#!/usr/bin/env python3
"""One-shot, additive import from local SJARACNe worktrees with per-file provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


REPO = Path(__file__).resolve().parents[1]
TRACKED = (
    ("SJARACNe-dream5-benchmark", "benchmarks/dream5_network1", "benchmarks/dream5_network1"),
    ("SJARACNe-pr68-develop", "benchmarks/brca100_pr67_threshold_sweep", "benchmarks/brca100_pr67_threshold_sweep"),
    ("SJARACNe-pr68-develop", "benchmarks/brca100_netbid_qc", "benchmarks/brca100_netbid_qc"),
    ("SJARACNe-min-recurrence-develop", "benchmarks/brca100_consensus_recurrence_sweep", "benchmarks/brca100_consensus_recurrence_sweep"),
    ("SJARACNe-hub-dpi-analysis", "benchmarks/brca100_hub_size_dpi_pilot", "benchmarks/brca100_hub_size_dpi_pilot"),
    ("SJARACNe-hub-dpi-analysis", "benchmarks/brca100_kdpi_witness_screen", "benchmarks/brca100_kdpi_witness_screen"),
    ("SJARACNe-hub-dpi-analysis", "benchmarks/brca100_hub_size_dpi_analysis", "benchmarks/brca100_hub_size_dpi_analysis"),
    ("SJARACNe-luad-gdc", "benchmarks/tcga_luad_gdc", "archive/tcga_luad_gdc"),
)
EVIDENCE = (
    "bootstrap_tp_fp_20261013", "sampling_comparison_20261013", "three_populations_20261012",
    "eligible_epr_20261012", "fixed_universe_20261012_verified", "eligible_fig6a_20261012",
    "sampling_scoring_20261013/three_populations", "sampling_scoring_20261013/eligible_epr",
    "sampling_scoring_20261013/fixed_universe",
)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-c", "safe.directory=" + root.resolve().as_posix(),
                                    "-C", str(root), *args], text=True).strip()


def execute(workspace):
    manifest_path = REPO / "provenance/import_manifest.json"
    if manifest_path.exists():
        raise FileExistsError("Import manifest exists; this import never adopts/overwrites an earlier migration")
    records, omitted, contexts, git_tables = [], [], {}, {}

    def context(root):
        name = root.name
        if name not in contexts:
            contexts[name] = {"source_repository": "https://github.com/adamdingliang/SJARACNe",
                              "checkout_path": str(root.resolve()), "checkout_commit": git(root, "rev-parse", "HEAD")}
        return contexts[name]

    def copy(root, relative, destination, tracked, kind):
        source, target = root / relative, REPO / destination
        if target.exists():
            raise FileExistsError(f"Refuse to overwrite {target}")
        if source.suffix.lower() in {".adj", ".exe", ".h5ad", ".rds", ".rdata", ".f64", ".bin"}:
            raise ValueError(f"Large/native artifact unexpectedly selected: {source}")
        if source.stat().st_size >= 50 * 1024**2:
            raise ValueError(f"Selected file exceeds 50 MiB: {source}")
        source_sha = digest(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(target) != source_sha or digest(source) != source_sha:
            raise ValueError("Source/copy changed during import")
        row = {"destination": destination, "source_checkout": root.name,
                        "source_relative_path": relative, "source_sha256": source_sha,
                        "imported_sha256": source_sha, "bytes": target.stat().st_size,
                        "source_tracked": tracked, "kind": kind, "adapted_for_new_repo": False}
        if tracked:
            if root.name not in git_tables:
                entries = subprocess.check_output(["git", "-c", "safe.directory=" + root.resolve().as_posix(),
                                                   "-C", str(root), "ls-files", "--stage", "-z"]).decode("utf-8")
                git_tables[root.name] = {}
                for entry in entries.split("\0"):
                    if entry:
                        metadata, name = entry.split("\t", 1)
                        mode, blob, _ = metadata.split()
                        git_tables[root.name][name] = (mode, blob)
            row["source_git_mode"], row["source_git_blob"] = git_tables[root.name][relative]
        records.append(row)
        context(root)

    for checkout, prefix, destination in TRACKED:
        root = workspace / checkout
        if git(root, "status", "--porcelain", "--", prefix):
            raise ValueError(f"Canonical tracked source package is dirty: {checkout}/{prefix}")
        files = git(root, "ls-files", "--", prefix).splitlines()
        if not files:
            raise ValueError(f"Empty source package: {prefix}")
        for relative in files:
            suffix = relative.removeprefix(prefix)
            copy(root, relative, destination + suffix, True, "tracked benchmark package")

    root = workspace / "SJARACNe"
    for prefix in ("benchmarks/thp1_perturbseq", "benchmarks/tcga_luad_download"):
        for path in sorted((root / prefix).rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            below = path.relative_to(root / prefix).parts
            if any(part in {"results", "__pycache__", ".pytest_cache", "work", ".ipynb_checkpoints"} for part in below):
                continue
            if path.name == "sampling_only_backport.patch":
                omitted.append({"source_checkout": root.name, "source_relative_path": relative,
                                "source_sha256": digest(path), "reason": "native engine patch stays external"})
                continue
            copy(root, relative, relative, False, "previously untracked scientific workflow")
    result_prefix = "benchmarks/thp1_perturbseq/results/author_reconstruction_20261011"
    for name in EVIDENCE:
        source_folder = root / result_prefix / name
        for path in sorted(source_folder.iterdir()):
            if not path.is_file() or path.suffix == ".log":
                continue
            relative = path.relative_to(root).as_posix()
            copy(root, relative, "benchmarks/thp1_perturbseq/evidence/author_reconstruction_20261011/" + name + "/" + path.name,
                 False, "compact historical result; dependency closure remains external")
    copy(root, "LICENSE.md", "provenance/licenses/SJARACNe_LICENSE.md", True, "original license notice")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump({"schema": 1, "migration_date": "2026-10-13", "status": "imported",
                   "policy": "additive copy; no source mutations or inference; preserve historical provenance",
                   "source_contexts": contexts, "files": records, "omitted": omitted}, stream, indent=2)
        stream.write("\n")
    return {"files": len(records), "bytes": sum(row["bytes"] for row in records), "omitted": omitted}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    print(json.dumps(execute(parser.parse_args().workspace.resolve())))
