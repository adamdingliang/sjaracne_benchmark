#!/usr/bin/env python3
"""Descriptively compare two immutable moderate-tail calibration packages.

Only recorded GPD cutoffs and held-out actual/nominal ratios are compared.
No fitting, threshold selection, empirical fallback, or acceptance override.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys


SCHEMA = "sjaracne-apmi-5m-to-expanded-10m-descriptive-comparison-v1"
PREVIOUS_SCHEMA = "sjaracne-exact-m-moderate-tail-summary-v1"
CURRENT_SCHEMA = "sjaracne-exact-m-moderate-tail-summary-10m-v1"
PREVIOUS_M = [30, 50, 80, 90, 100, 150, 300, 1000, 644, 516, 725]
NEW_M = [200, 250, 400, 500, 600, 700, 800, 900]
CURRENT_M = sorted(PREVIOUS_M + NEW_M)
PROBABILITIES = ((1e-3, "1e_3"), (5e-4, "5e_4"))
STATUSES = ("accepted", "rejected", "failed", "incomplete", "not_started")
COMMON_CONFIG = {
    "npar": 40, "tail_quantile": 0.995, "min_tail_count": 20_000,
    "p_min": 5e-4, "p_max": 1e-3, "default_p": 5e-4,
    "validation_p": [1e-3, 5e-4], "stability_relative_tolerance": 0.10,
    "min_stability_fits": 3, "validation_family_confidence": 0.99,
    "validation_family_comparisons": 10,
}
CAUTION = (
    "Descriptive comparison only. The previous package used 5M fitting plus 5M held-out draws "
    "per m (base seeds 20261015/20261016); the expanded package used 10M plus 10M draws "
    "and fresh base seeds 20261017/20261018. Both simulation count and random streams changed: "
    "this is not a matched causal test of sample-size effects, precision improvement, or why "
    "acceptance changed. A status transition is not proof of improvement or regression. "
    "Recorded accepted/rejected/failed/incomplete statuses are preserved, never selected by "
    "this comparison. No threshold refitting, held-out tuning, empirical fallback, interpolation, "
    "biological validation, or biological FDR claim is made. Pointwise confidence is 99.9% under "
    "the unchanged per-model family design, not simultaneous coverage across the m grid."
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: " + str(path))
    return value


def verify_manifest(package):
    """Check the complete compact package, not merely the summary being read."""
    if package.is_symlink():
        raise ValueError("symlink package directory is not accepted")
    manifest_path = package / "package_sha256.json"
    manifest = read_object(manifest_path)
    if not manifest:
        raise ValueError("empty package manifest")
    for name, digest in manifest.items():
        relative = PurePosixPath(name)
        if (not name or relative.is_absolute() or ".." in relative.parts or
                ":" in name or "\\" in name or name != relative.as_posix() or
                name == "package_sha256.json"):
            raise ValueError("unsafe/noncanonical package manifest path")
        if not isinstance(digest, str) or re.fullmatch("[0-9a-f]{64}", digest) is None:
            raise ValueError("invalid SHA256 in package manifest")
    actual = {}
    for path in sorted(package.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink in package evidence")
        if path.is_file() and path != manifest_path:
            actual[path.relative_to(package).as_posix()] = sha256(path)
    if actual != manifest:
        raise ValueError("package files/hashes do not match package_sha256.json")
    if "summary.json" not in manifest:
        raise ValueError("package manifest does not contain summary.json")
    return sha256(manifest_path)


def finite_number(value, name, minimum=0.0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid numeric field " + name)
    if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        raise ValueError("numeric field outside valid range: " + name)
    return float(value)


def load_package(package, current):
    manifest_hash = verify_manifest(package)
    summary = read_object(package / "summary.json")
    expected_schema = CURRENT_SCHEMA if current else PREVIOUS_SCHEMA
    if summary.get("format") != expected_schema:
        raise ValueError("unexpected summary schema for " + ("current" if current else "previous") + " package")
    draws = 10_000_000 if current else 5_000_000
    first_seed = 20261017 if current else 20261015
    config = {**COMMON_CONFIG, "fit_draws": draws, "validation_draws": draws,
              "fit_seed": first_seed, "validation_seed": first_seed + 1}
    if summary.get("config") != config:
        raise ValueError("package config does not match its frozen draw counts, seeds, and gates")
    results = summary.get("results")
    if not isinstance(results, list) or any(not isinstance(row, dict) for row in results):
        raise ValueError("invalid results container")
    expected_m = set(CURRENT_M if current else PREVIOUS_M)
    by_m = {}
    for row in results:
        m = row.get("m")
        if isinstance(m, bool) or not isinstance(m, int) or m not in expected_m or m in by_m:
            raise ValueError("invalid, duplicate, or unplanned m in package")
        status = row.get("status")
        if status not in STATUSES or row.get("accepted") is not (status == "accepted"):
            raise ValueError("inconsistent recorded status/acceptance")
        diagnostics = row.get("gpd")
        if not isinstance(diagnostics, list) or any(not isinstance(d, dict) for d in diagnostics):
            raise ValueError("invalid recorded GPD diagnostics")
        by_p = {}
        for diagnostic in diagnostics:
            p = diagnostic.get("nominal_p")
            if isinstance(p, bool) or p not in (1e-3, 5e-4) or p in by_p:
                raise ValueError("unplanned/duplicate GPD probability")
            by_p[p] = {
                "cutoff": finite_number(diagnostic.get("cutoff"), "cutoff"),
                "ratio": finite_number(diagnostic.get("ratio_observed_to_nominal"), "ratio", maximum=1 / p),
            }
        if ((status in {"accepted", "rejected"} and set(by_p) != {1e-3, 5e-4}) or
                (status not in {"accepted", "rejected"} and by_p)):
            raise ValueError("recorded GPD diagnostic availability disagrees with job status")
        by_m[m] = {"status": status, "gpd": by_p}
    if set(by_m) != expected_m:
        raise ValueError("package does not contain its exact predeclared m membership")
    counts = {status: sum(row["status"] == status for row in by_m.values()) for status in STATUSES}
    if summary.get("counts") != counts:
        raise ValueError("package status counts disagree with result rows")
    return by_m, {"path": str(package), "manifest_sha256": manifest_hash,
                  "summary_sha256": sha256(package / "summary.json"),
                  "format": expected_schema, "config": config, "counts": counts}


def comparison_rows(previous, current):
    rows = []
    for m in CURRENT_M:
        old = previous.get(m, {"status": "not_run", "gpd": {}})
        new = current[m]
        row = {"m": m, "previous_status": old["status"], "current_status": new["status"]}
        for p, suffix in PROBABILITIES:
            before, after = old["gpd"].get(p), new["gpd"].get(p)
            row["previous_gpd_cutoff_p_" + suffix] = None if before is None else before["cutoff"]
            row["current_gpd_cutoff_p_" + suffix] = None if after is None else after["cutoff"]
            row["cutoff_change_percent_p_" + suffix] = (
                None if before is None or after is None or before["cutoff"] == 0 else
                100 * (after["cutoff"] - before["cutoff"]) / before["cutoff"])
            row["previous_actual_to_nominal_p_" + suffix] = None if before is None else before["ratio"]
            row["current_actual_to_nominal_p_" + suffix] = None if after is None else after["ratio"]
        rows.append(row)
    return rows


def write_json_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def short(value):
    return "n/a" if value is None else format(value, ".8g")


def write_report(path, result):
    lines = ["# Descriptive 5M versus expanded 10M calibration comparison", "", CAUTION, "",
             "Previous package: 11 exact m sizes. Current package: 19 exact m sizes; 8 are newly run.", "",
             "Cutoff change is 100 * (current - previous) / previous. Missing diagnostics and zero previous cutoffs have no percentage change. A new size has previous_status=not_run. Rejected GPD cutoffs are diagnostic only, not usable models.", "",
             "Recorded status transitions (including new sizes):"]
    lines.extend("- %s: %s" % (transition, count) for transition, count in result["transitions"].items())
    lines += ["", "| m | Previous -> current status | GPD cutoff p=.001, previous -> current (change %) | Actual/nominal p=.001, previous -> current | GPD cutoff p=.0005, previous -> current (change %) | Actual/nominal p=.0005, previous -> current |",
              "|---:|:---|:---|:---|:---|:---|"]
    for row in result["results"]:
        cells = [str(row["m"]), row["previous_status"] + " -> " + row["current_status"]]
        for _, suffix in PROBABILITIES:
            cells.append("%s -> %s (%s)" % (short(row["previous_gpd_cutoff_p_" + suffix]),
                                               short(row["current_gpd_cutoff_p_" + suffix]),
                                               short(row["cutoff_change_percent_p_" + suffix])))
            cells.append("%s -> %s" % (short(row["previous_actual_to_nominal_p_" + suffix]),
                                       short(row["current_actual_to_nominal_p_" + suffix])))
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "CSV and JSON retain unrounded values. Both source package checksum manifests were verified. This comparison does not emit or install any model.", ""]
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))


def compare_packages(previous, current, out):
    previous_path, current_path = Path(previous), Path(current)
    if previous_path.is_symlink() or current_path.is_symlink():
        raise ValueError("symlink source package is not accepted")
    previous_path, current_path = previous_path.resolve(strict=True), current_path.resolve(strict=True)
    out = Path(out).resolve()
    if out.exists():
        raise ValueError("output must be a fresh nonexistent directory")
    for source in (previous_path, current_path):
        if source == out or source in out.parents or out in source.parents:
            raise ValueError("comparison output and source packages must not contain each other")
    old, old_provenance = load_package(previous_path, current=False)
    new, new_provenance = load_package(current_path, current=True)
    rows = comparison_rows(old, new)
    result = {"format": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
              "comparison_code_sha256": sha256(__file__), "caution": CAUTION,
              "previous": old_provenance, "current": new_provenance,
              "common_m": sorted(set(old) & set(new)), "new_m": sorted(set(new) - set(old)),
              "transitions": dict(sorted(Counter(r["previous_status"] + " -> " + r["current_status"] for r in rows).items())),
              "results": rows}
    out.mkdir(parents=True, exist_ok=False)
    write_json_new(out / "comparison.json", result)
    with (out / "comparison.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_report(out / "REPORT.md", result)
    hashes = {p.name: sha256(p) for p in sorted(out.iterdir()) if p.is_file()}
    write_json_new(out / "package_sha256.json", hashes)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_packages(args.previous, args.current, args.out)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Calibration package comparison failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result["transitions"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
