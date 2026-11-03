#!/usr/bin/env python3
"""Import or verify the compact, allowlisted K20 benchmark evidence.

This tool never executes SJARACNe, consensus, QC, or a network request. The
import subcommand reads completed local reports; validate needs only this
repository. Expression matrices, edge lists, and original QC HTMLs stay local.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil


DEFAULT_OUTPUT = Path(__file__).resolve().parent
MANIFEST = Path("evidence/package_manifest.json")


def read_json(path):
    """Read a UTF-8 JSON artifact."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    """Return a file's SHA256 without changing it."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_path(root, relative):
    """Resolve a portable relative artifact path inside its declared root."""
    raw = relative.as_posix() if isinstance(relative, Path) else str(relative)
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts or "\\" in raw or ":" in raw:
        raise ValueError(f"Nonportable or escaping artifact path: {relative}")
    root = Path(root).resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Artifact escapes root: {relative}")
    return target


def copy_immutable(source, destination, expected=None):
    """Copy a checked artifact, refusing an existing different destination."""
    source, destination = Path(source), Path(destination)
    digest = sha256(source)
    if expected is not None and digest != expected:
        raise ValueError(f"Source hash mismatch: {source.name}")
    if destination.exists():
        if sha256(destination) != digest:
            raise ValueError(f"Refusing different existing file: {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    if sha256(destination) != digest:
        raise ValueError(f"Copied file hash mismatch: {destination}")
    return digest


def verify_publication(overall):
    """Require a complete BLCA-inclusive report with all publication hashes."""
    latest = read_json(overall / "LATEST_OVERALL.json")
    if latest.get("state") != "complete" or latest.get("dataset") != "BLCA406":
        raise ValueError("Overall publication is not a completed BLCA extension")
    wanted = {"OVERALL.html", "OVERALL.md", "report_data.json", "overall_metrics.tsv"}
    if set(latest.get("published_sha256", {})) != wanted:
        raise ValueError("Incomplete publication hash set")
    for name, digest in latest["published_sha256"].items():
        if sha256(overall / name) != digest:
            raise ValueError(f"Published report hash mismatch: {name}")
    return latest


def check_metrics(output):
    """Check report completeness and all 400 DREAM recurrence metric rows."""
    report = read_json(output / "evidence/report_data.json")
    if report.get("state") != "complete" or report.get("B") != 100 or report.get("K") != 20:
        raise ValueError("Report is not complete K20/B100")
    if len(report["primary_bulk"]) != 12 or len(report["primary_dream"]) != 4:
        raise ValueError("Expected twelve bulk and four DREAM primary rows")
    if len(report["matched_dream"]) != 4 or len(report["matched_bulk"]) != 8:
        raise ValueError("Expected four DREAM and eight earlier bulk matched controls")
    blca = read_json(output / "evidence/blca_results.json")
    if blca.get("state") != "complete" or len(blca["arms"]) != 4:
        raise ValueError("BLCA results are incomplete")
    for arm in blca["arms"]:
        if arm["validation"].get("native_networks") != 100:
            raise ValueError("BLCA native resample count differs")
        if not arm["validation"].get("native_sha_signatures_checked"):
            raise ValueError("BLCA native signatures were not checked")
    with (output / "evidence/dream5_k_sweep.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    expected = {(dataset, version, k) for dataset in ("DREAM5_N1", "DREAM5_N3")
                for version in ("legacy", "current") for k in range(1, 101)}
    keys = {(r["dataset"], r["version"], int(r["K"])) for r in rows}
    if len(rows) != 400 or keys != expected:
        raise ValueError("DREAM sweep is not the complete unique K1-100 grid")
    for row in rows:
        tp, fp, fn, tn = (int(row[key]) for key in ("TP", "FP", "FN", "TN"))
        if tp + fn != int(row["reference_positives"]) or fp + tn != int(row["reference_negatives"]):
            raise ValueError("Inconsistent confusion-matrix denominator")
        for key, value in (("precision", tp / (tp + fp)), ("recall", tp / (tp + fn)),
                           ("F1", 2 * tp / (2 * tp + fp + fn))):
            if not math.isclose(float(row[key]), value, rel_tol=1e-12, abs_tol=1e-15):
                raise ValueError(f"Incorrect {key} in DREAM sweep")
    return {"primary_bulk_rows": 12, "primary_dream_rows": 4,
            "matched_bulk_rows": 8, "matched_dream_rows": 4, "dream_K_cases": 400}


def import_evidence(overall, original, sweep, blca, output):
    """Import the explicit evidence allowlist and byte-identical QC plots."""
    roots = {"overall": Path(overall).resolve(), "original": Path(original).resolve(),
             "sweep": Path(sweep).resolve(), "blca": Path(blca).resolve()}
    output = Path(output).resolve()
    latest = verify_publication(roots["overall"])
    if read_json(roots["sweep"] / "analysis.json").get("state") != "complete":
        raise ValueError("Full K sweep is incomplete")
    files = []

    def add(label, source_relative, destination_relative, expected=None, extra=None):
        source = safe_path(roots[label], source_relative)
        target = safe_path(output, destination_relative)
        digest = copy_immutable(source, target, expected)
        entry = {"path": destination_relative, "bytes": target.stat().st_size, "sha256": digest,
                 "source": {"snapshot": label, "path": source_relative, "sha256": digest}}
        if extra:
            entry.update(extra)
        files.append(entry)

    allowlist = [
        ("overall", "overall_metrics.tsv", "overall_metrics.tsv"),
        ("overall", "report_data.json", "report_data.json"),
        ("overall", "LATEST_OVERALL.json", "latest_overall.json"),
        ("overall", "legacy_gate_equivalents.json", "legacy_gate_equivalents.json"),
        ("original", "manifest.json", "original_manifest.json"),
        ("blca", "manifest.json", "blca_manifest.json"),
        ("blca", "results.json", "blca_results.json"),
        ("blca", "scientific_source_equivalence.json", "scientific_source_equivalence.json"),
        ("sweep", "metrics.tsv", "dream5_k_sweep.tsv"),
        ("sweep", "shared_K.tsv", "dream5_shared_K.tsv"),
        ("sweep", "analysis.json", "dream5_k_analysis.json"),
    ]
    for label, source, destination in allowlist:
        add(label, source, "evidence/" + destination)
    report = read_json(roots["overall"] / "report_data.json")
    for arm in report["primary_bulk"]:
        for kind in ("target_sizes", "scale_free"):
            figure = arm["figures"][kind]
            asset = figure["asset"]
            add("overall", asset, "figures/netbid2/" + Path(asset).name,
                figure["png_sha256"], {"arm": arm["id"], "figure_kind": kind,
                "source_html_sha256": figure["source_html_sha256"],
                "pixels_unchanged_from_source_html": True})
    for name in ("f1_vs_K.png", "precision_recall_vs_K.png", "tp_fp_vs_K.png"):
        add("sweep", "assets/" + name, "figures/k_sweep/" + name)
    checks = check_metrics(output)
    manifest = {
        "schema_version": 1, "state": "complete", "purpose": "Compact frozen benchmark evidence; no inference",
        "source_publication_utc": latest["published_utc"],
        "source_snapshots": {label: path.name for label, path in roots.items()},
        "excluded": ["expression and patient metadata", "adjacency and consensus edge lists",
                     "native binaries and environments", "original self-contained QC HTMLs"],
        "frozen_records_note": "Copied JSON retains original local provenance paths; those are not portable runtime dependencies.",
        "validation": checks, "files": sorted(files, key=lambda entry: entry["path"]),
    }
    target = output / MANIFEST
    content = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if target.exists() and target.read_bytes() != content:
        raise ValueError("Refusing different existing package manifest")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(content)
    return validate(output)


def validate(output):
    """Read-only verification of hashes, sizes, unique paths and metric checks."""
    output = Path(output).resolve()
    manifest = read_json(output / MANIFEST)
    if manifest.get("state") != "complete":
        raise ValueError("Evidence manifest is incomplete")
    paths = []
    total = 0
    for record in manifest["files"]:
        relative = record["path"]
        if not relative.startswith(("evidence/", "figures/")) or relative == MANIFEST.as_posix():
            raise ValueError("Unexpected evidence path")
        if Path(relative).suffix not in (".json", ".tsv", ".png"):
            raise ValueError("Non-allowlisted evidence file type")
        path = safe_path(output, relative)
        if path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
            raise ValueError(f"Evidence hash or size mismatch: {relative}")
        if record["source"]["sha256"] != record["sha256"]:
            raise ValueError("Imported bytes differ from source identity")
        paths.append(relative)
        total += record["bytes"]
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate evidence paths")
    if sum(path.startswith("figures/netbid2/") for path in paths) != 24:
        raise ValueError("Expected twenty-four original primary QC PNGs")
    return {"state": "verified", "files": len(paths), "bytes": total, **check_metrics(output)}


def main():
    """Parse explicit local source roots; validation is portable and read-only."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    importing = sub.add_parser("import")
    for name in ("overall", "original", "sweep", "blca"):
        importing.add_argument("--" + name, type=Path, required=True)
    for child in (importing, sub.add_parser("validate")):
        child.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.command == "import":
        result = import_evidence(args.overall, args.original, args.sweep, args.blca, args.output)
    else:
        result = validate(args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
