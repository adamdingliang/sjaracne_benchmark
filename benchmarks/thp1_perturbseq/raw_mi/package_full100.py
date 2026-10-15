"""Validate and package compact full-100 raw-MI evidence, without new inference.

The five original evaluation budgets and primary k=5,000 remain unchanged.
Additional existing curve budgets are descriptive; no MI is pooled or reranked.
Only compact reports/provenance and numeric tables are copied, never adjacency,
raw score arrays, expression, reference edges, or labels.npy.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np


BUDGETS = tuple(range(1000, 100001, 1000))
DISPLAY_BUDGETS = (1000, 5000, 10000, 20000, 30000, 50000, 100000)
PRESPECIFIED = (1000, 5000, 10000, 50000, 100000)
METRICS = {"TP": "TP_tie_expected", "FP": "FP_tie_expected", "precision": "precision_tie_expected",
           "EPR": "EPR_tie_expected", "sensitivity": "sensitivity_tie_expected", "specificity": "specificity_tie_expected"}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def record(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def read_json(path):
    def invalid(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid)


def verify_record(value, expected_path=None):
    path = Path(value["path"]).resolve(strict=True)
    if expected_path is not None and path != Path(expected_path).resolve():
        raise ValueError("Provenance record points to the wrong artifact")
    if path.stat().st_size != value["bytes"] or digest(path) != value["sha256"]:
        raise ValueError("Artifact SHA256/size mismatch: " + str(path))
    return path


def _close(actual, expected, label, *, tolerance=1e-9):
    if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual):
        raise ValueError("Invalid numeric metric: " + label)
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=tolerance):
        raise ValueError("Inconsistent metric: " + label)


def _validate_point(row, size, positive, negative):
    k = row.get("k")
    if isinstance(k, bool) or not isinstance(k, int) or not 0 <= k <= size:
        raise ValueError("Invalid curve budget")
    tp, fp = row.get("TP_tie_expected"), row.get("FP_tie_expected")
    _close(tp, tp, "TP")
    _close(fp, fp, "FP")
    if not 0 <= tp <= min(k, positive) or not 0 <= fp <= min(k, negative):
        raise ValueError("TP/FP outside fixed class counts")
    _close(tp + fp, k, "TP+FP=k")
    _close(row["sensitivity_tie_expected"], tp / positive, "sensitivity")
    _close(row["specificity_tie_expected"], 1 - fp / negative, "specificity")
    _close(row["FPR_tie_expected"], fp / negative, "FPR")
    _close(row["random_TP_expectation_at_k"], k * positive / size, "random TP")
    low, high = row["TP_min"], row["TP_max"]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (low, high)):
        raise ValueError("Tie-range endpoints must be integers")
    if not 0 <= low <= tp <= high <= min(k, positive):
        raise ValueError("Invalid attainable TP tie range")
    if k:
        _close(row["precision_tie_expected"], tp / k, "precision")
        _close(row["EPR_tie_expected"], (tp / k) / (positive / size), "EPR")
    elif row.get("precision_tie_expected") is not None or row.get("EPR_tie_expected") is not None:
        raise ValueError("k=0 precision/EPR must be null")


def build_evidence(results, plan):
    """Return summary, one row per budget, and per-seed budget rows.

    Validates a complete 100-seed × 2-arm population; no files are written.
    """
    if plan.get("seeds") != list(range(1, 101)) or plan.get("arms") != ["before", "after"]:
        raise ValueError("Evidence requires all 100 original seeds in both arms")
    if plan["parameters"].get("primary_k") != 5000 or tuple(plan["parameters"].get("ks", [])) != PRESPECIFIED:
        raise ValueError("Original primary and prespecified evaluation budgets changed")
    universe = plan["universe"]
    size, positive, negative = (universe[key] for key in
                                ("candidate_pairs", "reference_positive_pairs", "reference_negative_pairs"))
    if not 0 < positive < size or positive + negative != size:
        raise ValueError("Invalid fixed-universe class totals")
    _close(universe["random_positive_fraction"], positive / size, "fixed prevalence")
    population, canonical_grid, canonical_roc = {}, None, None
    for result in results:
        identity = result.get("arm"), result.get("seed")
        if identity[0] not in ("before", "after") or identity[1] not in range(1, 101) or isinstance(identity[1], bool):
            raise ValueError("Unexpected arm/seed identity")
        if identity in population:
            raise ValueError("Duplicate arm/seed metrics")
        if result.get("status") != "complete":
            raise ValueError("Incomplete job metrics")
        for key in ("candidate_pairs", "reference_positive_pairs", "reference_negative_pairs", "random_positive_fraction"):
            if result.get(key) != universe[key]:
                raise ValueError("Scoring class totals/prevalence differ from plan")
        auc = result.get("AUROC_MI_ties")
        _close(auc, auc, "AUROC")
        if not 0 <= auc <= 1:
            raise ValueError("AUROC outside [0,1]")
        _close(result["AUROC_ROC_integral_check"], auc, "AUROC integration", tolerance=1e-12)
        curve = result["curve"]
        grid = tuple(row["k"] for row in curve)
        if not grid or grid[0] != 0 or grid[-1] != size or any(a >= b for a, b in zip(grid, grid[1:])):
            raise ValueError("Invalid/duplicate curve grid")
        if canonical_grid is None:
            canonical_grid = grid
        if grid != canonical_grid or not set(BUDGETS) <= set(grid):
            raise ValueError("Curve grids differ or lack exact 1k-to-100k points")
        for row in curve:
            _validate_point(row, size, positive, negative)
        if [row["k"] for row in result["top_k"]] != list(PRESPECIFIED):
            raise ValueError("Per-job prespecified budgets changed")
        indexed = {row["k"]: row for row in curve}
        for row in result["top_k"]:
            _validate_point(row, size, positive, negative)
            for key in METRICS.values():
                _close(row[key], indexed[row["k"]][key], "top-k versus curve " + key)
        roc = result.get("roc_curve")
        if roc is not None:
            fpr, tpr = roc["FPR"], roc["sensitivity"]
            if len(fpr) != len(tpr) or not fpr or fpr[0] != 0 or fpr[-1] != 1:
                raise ValueError("Invalid sampled ROC grid")
            if any(not math.isfinite(value) or not 0 <= value <= 1 for value in [*fpr, *tpr]):
                raise ValueError("Invalid ROC values")
            if any(a > b for a, b in zip(fpr, fpr[1:])) or any(a > b for a, b in zip(tpr, tpr[1:])):
                raise ValueError("ROC must be monotone")
            if canonical_roc is None:
                canonical_roc = tuple(fpr)
            elif tuple(fpr) != canonical_roc:
                raise ValueError("Sampled ROC grids differ")
        population[identity] = (result, indexed)
    if set(population) != {(arm, seed) for arm in ("before", "after") for seed in range(1, 101)}:
        raise ValueError("Missing before/after results for the complete 100-seed population")
    budget_rows, per_seed = [], []
    for k in BUDGETS:
        role = "prespecified_primary" if k == 5000 else "prespecified_budget" if k in PRESPECIFIED else "descriptive_existing_curve_point"
        row = {"k": k, "role": role, "matched_seeds": 100}
        for name, key in METRICS.items():
            before = np.array([population[("before", seed)][1][k][key] for seed in range(1, 101)])
            after = np.array([population[("after", seed)][1][k][key] for seed in range(1, 101)])
            delta = after - before
            row.update({f"before_{name}_median": float(np.median(before)),
                        f"after_{name}_median": float(np.median(after)),
                        f"paired_{name}_delta_median": float(np.median(delta)),
                        f"paired_{name}_after_higher": int(np.count_nonzero(delta > 0)),
                        f"paired_{name}_after_equal": int(np.count_nonzero(delta == 0)),
                        f"paired_{name}_after_lower": int(np.count_nonzero(delta < 0))})
        budget_rows.append(row)
        for seed in range(1, 101):
            for arm in ("before", "after"):
                point = population[(arm, seed)][1][k]
                per_seed.append({"arm": arm, "seed": seed, "k": k, "role": role,
                                 **{name: point[key] for name, key in METRICS.items()},
                                 "TP_min": point["TP_min"], "TP_max": point["TP_max"]})
    auc_before = np.array([population[("before", seed)][0]["AUROC_MI_ties"] for seed in range(1, 101)])
    auc_after = np.array([population[("after", seed)][0]["AUROC_MI_ties"] for seed in range(1, 101)])
    auc_delta = auc_after - auc_before
    summary = {"schema": 1, "status": "complete", "scope": "Full-100 raw-MI primary evidence; no new inference or score recalculation",
               "matched_seeds": 100, "metric_files": len(results), "primary_k": 5000,
               "selection_history": "The full-100 extension was requested after examining the exploratory 20-seed pilot. All pilot seeds are included; this is not an independent confirmatory cohort. The original primary k=5,000 and five prespecified budgets are unchanged.",
               "original_prespecified_budgets": list(PRESPECIFIED), "display_budgets": list(DISPLAY_BUDGETS),
               "descriptive_grid": "Exact saved curve points every 1,000 pairs from 1,000 through 100,000; no interpolation or retuning",
               "universe": universe, "display_rows": [row for row in budget_rows if row["k"] in DISPLAY_BUDGETS],
               "median_AUROC": {"before": float(np.median(auc_before)), "after": float(np.median(auc_after))},
               "paired_AUROC": {"delta_median": float(np.median(auc_delta)),
                                "after_higher": int(np.count_nonzero(auc_delta > 0)),
                                "after_equal": int(np.count_nonzero(auc_delta == 0)),
                                "after_lower": int(np.count_nonzero(auc_delta < 0))},
               "limitations": ["Computational resamples of the same cells are not independent biological replicates; no significance claim",
                               "Reference-positive perturbation responses are not proof of direct regulation",
                               "Full100 includes the original 20-pilot seeds; these are not independent replications",
                               "DPI/consensus end-to-end evidence remains secondary and is not overwritten"]}
    return summary, budget_rows, per_seed


def load_run(run_root, report_root=None):
    run_root = Path(run_root).resolve(strict=True)
    report_root = Path(report_root).resolve(strict=True) if report_root else run_root / "report_20261015"
    plan = read_json(run_root / "plan.json")
    status = read_json(run_root / "status.json")
    extension = read_json(run_root / "extension.json")
    provenance = read_json(report_root / "report_provenance.json")
    if status.get("status") != "complete" or status.get("completed") != 200 or status.get("total") != 200 or status.get("failures"):
        raise ValueError("Full-100 coordinator is not complete without failures")
    for value, expected in ((status["plan"], run_root / "plan.json"),
                            (status["extension"], run_root / "extension.json"),
                            (extension["new_plan"], run_root / "plan.json"),
                            (provenance["plan"], run_root / "plan.json"),
                            (provenance["extension"], run_root / "extension.json")):
        verify_record(value, expected)
    if Path(plan["out"]).resolve() != run_root:
        raise ValueError("Full plan output root differs from selected run root")
    verify_record(plan["universe_file"], run_root / "inputs/universe.json")
    records, identities, results = {}, set(), []
    for job in status["jobs"]:
        identity = job.get("arm"), job.get("seed")
        if job.get("status") != "complete" or identity in identities:
            raise ValueError("Incomplete or duplicate completed job record")
        identities.add(identity)
        metric_record = job["artifacts"]["metrics.json"]
        path = verify_record(metric_record)
        if path.name != "metrics.json" or path.parent.name != f"seed_{job['seed']:03d}" or path.parent.parent.name != job["arm"]:
            raise ValueError("Metric artifact path disagrees with job identity")
        if str(path) in records:
            raise ValueError("Duplicate metric artifact path")
        value = read_json(path)
        if (value.get("arm"), value.get("seed")) != identity:
            raise ValueError("Metric content identity disagrees with completed job")
        records[str(path)] = metric_record
        results.append(value)
    expected = {(arm, seed) for arm in ("before", "after") for seed in range(1, 101)}
    if identities != expected or len(results) != 200:
        raise ValueError("Completed records do not cover all 200 jobs")
    report_records = {}
    for value in provenance["score_results"]:
        path = str(Path(value["path"]).resolve())
        if path in report_records:
            raise ValueError("Duplicate report metric provenance record")
        report_records[path] = value
    if report_records != records:
        raise ValueError("Report provenance and completed metric artifacts differ")
    return plan, results, records, report_root


def _write_tsv(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def package(run_root, out, *, report_root=None, per_seed=True):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError("Evidence output must be fresh; existing evidence is never overwritten")
    run_root = Path(run_root).resolve(strict=True)
    plan, results, metric_records, report_root = load_run(run_root, report_root)
    summary, budgets, seed_rows = build_evidence(results, plan)
    extension = read_json(run_root / "extension.json")
    original_pilot = verify_record(extension["original_pilot_plan"])
    smoke_proof = verify_record(plan["smoke_proof"])
    copies = {"raw_mi_comparison.png": report_root / "raw_mi_comparison.png",
              "provenance/generated_summary.json": report_root / "summary.json", "paired_seed_metrics.tsv": report_root / "paired_seed_metrics.tsv",
              "provenance/generated_REPORT.md": report_root / "REPORT.md",
              "provenance/plan.json": run_root / "plan.json", "provenance/status.json": run_root / "status.json",
              "provenance/extension.json": run_root / "extension.json",
              "provenance/original_pilot_plan.json": original_pilot,
              "provenance/smoke_proof.json": smoke_proof,
              "provenance/universe.json": run_root / "inputs/universe.json",
              "provenance/report_provenance.json": report_root / "report_provenance.json"}
    audit = run_root / "independent_artifact_audit.json"
    if audit.is_file():
        copies["provenance/independent_artifact_audit.json"] = audit
    source_records = {name: record(path) for name, path in copies.items()}
    source_summary = read_json(report_root / "summary.json")
    if source_summary.get("status") != "complete" or source_summary.get("n_matched_seeds") != 100:
        raise ValueError("Existing full-100 report summary is incomplete")
    # All input validation and required-source existence checks finish before mkdir.
    out.mkdir(parents=True)
    for destination, source in copies.items():
        target = out / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if digest(target) != source_records[destination]["sha256"]:
            raise ValueError("Source copy changed during packaging")
    _write_tsv(out / "budget_summary.tsv", budgets)
    if per_seed:
        _write_tsv(out / "per_seed_budget_metrics.tsv", seed_rows)
    with (out / "analysis_summary.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")
    generated = ["budget_summary.tsv", "analysis_summary.json"] + (["per_seed_budget_metrics.tsv"] if per_seed else [])
    manifest = {"schema": 1, "status": "complete", "packager": record(__file__),
                "run_root": str(run_root), "source_copies": source_records,
                "source_metrics": sorted(metric_records.values(), key=lambda value: value["path"]),
                "copied_file_sha256": {name: digest(out / name) for name in copies},
                "generated_files": {name: record(out / name) for name in generated},
                "omitted_large_artifacts": ["raw.adj", "scores.npz", "labels.npy", "expression", "reference edge matrix"]}
    with (out / "package_manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report-root", type=Path)
    parser.add_argument("--no-per-seed", action="store_true")
    args = parser.parse_args()
    summary = package(args.run_root, args.out, report_root=args.report_root, per_seed=not args.no_per_seed)
    print(json.dumps({"status": summary["status"], "matched_seeds": summary["matched_seeds"],
                      "budget_count": len(BUDGETS), "out": str(args.out)}))


if __name__ == "__main__":
    main()
