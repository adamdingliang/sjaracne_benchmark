#!/usr/bin/env python3
"""Exploratory smoothing of existing AP-MI nulls; never generate new draws."""
from __future__ import annotations

import os
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_name] = "1"

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import time

import numpy as np
import scipy
from scipy.stats import beta

import extract
import models

KNOT_P = [0.05, 0.01, 0.001, 0.0005, 0.0001, 1e-5, 1e-6, 1e-7]
PROBE_P = [0.02, 0.005, 0.002, 0.00075, 0.0002, 5e-5, 5e-6, 5e-7]
ALL_P = sorted(KNOT_P + PROBE_P, reverse=True)
PRIMARY_P = [0.001, 0.0005]
GRID = [30, 50, 80, 90, 100, 150, 200, 250, 300, 400, 500, 516,
        600, 644, 700, 725, 800, 900, 1000]
SMOOTHERS = ["loglinear", "logquadratic", "pchip"]
CONFIDENCE = 0.999
ROOT = Path(__file__).resolve().parents[3]


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def write_csv(path, rows):
    if not rows:
        raise ValueError("cannot write an empty table")
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def cp_interval(count, draws, confidence=CONFIDENCE):
    if not 0 <= count <= draws or draws <= 0 or not 0 < confidence < 1:
        raise ValueError("invalid binomial interval arguments")
    alpha = 1 - confidence
    return (0.0 if count == 0 else float(beta.ppf(alpha / 2, count, draws-count+1)),
            1.0 if count == draws else float(beta.ppf(1-alpha/2, count+1, draws-count)))


def classify_interval(low, high, p):
    if low >= 0.9*p and high <= 1.1*p:
        return "pointwise_interval_inside_10pct_band"
    if high < 0.9*p or low > 1.1*p:
        return "pointwise_interval_disjoint_from_10pct_band"
    return "unresolved_pointwise"


def valid_cutoff(value, m):
    if not math.isfinite(value) or not 0 <= value <= math.log(m):
        raise ValueError("cutoff outside finite MI support")
    return float(value)


def parameters(item):
    fit = item["primary_fit"]
    return {"u": float(fit["threshold"]), "scale": float(fit["scale"]),
            "shape": float(fit["shape"]), "tail_probability": float(fit["tail_probability"])}


def quantiles(item):
    return {float(row["nominal_p"]): float(row["cutoff"]) for row in item["quantiles"]}


def prediction_specs(items):
    """Predictions are fit-only; every smooth candidate omits the entire test m."""
    sizes = np.asarray([item["m"] for item in items])
    if sizes.tolist() != GRID:
        raise ValueError("expected all nineteen sizes in frozen sorted order")
    table = np.asarray([[quantiles(item)[p] for p in KNOT_P] for item in items])
    pars = {key: np.asarray([parameters(item)[key] for item in items])
            for key in parameters(items[0])}
    result = []
    for index, item in enumerate(items):
        m = item["m"]
        train = sizes != m
        train_m = sizes[train]
        fold = "endpoint_extrapolation" if m in (min(GRID), max(GRID)) else "interior_interpolation"
        empirical = quantiles(item)
        for family in ("quantile", "gpd"):
            for method in SMOOTHERS:
                error = None
                try:
                    if method == "pchip" and not min(train_m) <= m <= max(train_m):
                        raise ValueError("outside_training_m_range_no_extrapolation")
                    if family == "quantile":
                        knots = models.predict_quantiles(train_m, table[train], m, method)
                        predictions = models.interpolate_probability(KNOT_P, knots, ALL_P)
                    else:
                        predicted_pars = models.predict_gpd_parameters(
                            train_m, {key: values[train] for key, values in pars.items()}, m, method)
                except (ValueError, FloatingPointError, OverflowError) as exc:
                    error = str(exc)
                for pi, p in enumerate(ALL_P):
                    cutoff, reason = None, error
                    if reason is None:
                        try:
                            cutoff = valid_cutoff(float(predictions[pi]) if family == "quantile" else
                                models.gpd_cutoff(**predicted_pars, p=p, m=m), m)
                        except (ValueError, FloatingPointError, OverflowError) as exc:
                            reason = str(exc)
                    result.append({"m": m, "fold_kind": fold, "method": family+"_"+method,
                        "family": family, "smoother": method, "nominal_p": p,
                        "p_role": "knot" if p in KNOT_P else "probe",
                        "cutoff": cutoff, "empirical_cutoff": empirical[p],
                        "status": "valid" if reason is None else "unavailable",
                        "invalid_reason": reason, "train_m": train_m.tolist(),
                        "predicted_parameters": predicted_pars if family == "gpd" and error is None else None})
        for family in ("empirical_exact_m", "gpd_exact_m"):
            for p in ALL_P:
                reason, cutoff = None, None
                try:
                    cutoff = valid_cutoff(empirical[p] if family == "empirical_exact_m" else
                                         models.gpd_cutoff(**parameters(item), p=p, m=m), m)
                except (ValueError, FloatingPointError, OverflowError) as exc:
                    reason = str(exc)
                result.append({"m": m, "fold_kind": fold, "method": family,
                    "family": family, "smoother": None, "nominal_p": p,
                    "p_role": "knot" if p in KNOT_P else "probe", "cutoff": cutoff,
                    "empirical_cutoff": empirical[p], "status": "valid" if reason is None else "unavailable",
                    "invalid_reason": reason, "train_m": [m],
                    "predicted_parameters": parameters(item) if family == "gpd_exact_m" else None})
    return result


def score_predictions(predictions, items):
    grouped = {item["m"]: item for item in items}
    rows = []
    for m in GRID:
        item = grouped[m]
        arrays = {stream: np.load(item["sorted_cache"][stream]["path"], mmap_mode="r")
                  for stream in ("fit", "validation")}
        for prediction in [row for row in predictions if row["m"] == m]:
            p = prediction["nominal_p"]
            for stream, values in arrays.items():
                row = {key: value for key, value in prediction.items()
                       if key not in ("train_m", "predicted_parameters")}
                row.update(train_m=json.dumps(prediction["train_m"]), stream=stream,
                    draws=int(values.size), expected_count=float(values.size*p), ge=None, gt=None,
                    ties=None, observed_p=None, actual_nominal=None, relative_null_rate_error=None,
                    relative_cutoff_error=None, cp_lower=None, cp_upper=None,
                    cp_confidence=None, pointwise_classification=None,
                    interval_role="unavailable_prediction" if row["status"] != "valid" else
                    ("not_applicable_in_sample_baseline" if stream == "fit" and not prediction["smoother"] else
                     "descriptive_fixed_prediction_pointwise"))
                if row["status"] == "valid":
                    counts = extract.count_sorted(values, row["cutoff"])
                    row.update(counts)
                    rate = counts["ge"] / len(values)
                    row.update(observed_p=rate, actual_nominal=rate/p,
                        relative_null_rate_error=rate/p-1,
                        relative_cutoff_error=row["cutoff"]/row["empirical_cutoff"]-1)
                    if row["interval_role"] == "descriptive_fixed_prediction_pointwise":
                        low, high = cp_interval(counts["ge"], len(values))
                        row.update(cp_lower=low, cp_upper=high, cp_confidence=CONFIDENCE,
                            pointwise_classification=classify_interval(low, high, p))
                rows.append(row)
    return rows


def summarize(rows):
    summaries = []
    methods = list(dict.fromkeys(row["method"] for row in rows))
    groups = {"primary_interior": lambda row: row["fold_kind"] == "interior_interpolation" and row["nominal_p"] in PRIMARY_P,
              "body_interior": lambda row: row["fold_kind"] == "interior_interpolation" and row["nominal_p"] >= 0.0005,
              "probe_interior_moderate": lambda row: row["fold_kind"] == "interior_interpolation" and row["p_role"] == "probe" and row["nominal_p"] >= 0.0005,
              "primary_endpoints": lambda row: row["fold_kind"] == "endpoint_extrapolation" and row["nominal_p"] in PRIMARY_P}
    for group, select in groups.items():
        for method in methods:
            subset = [row for row in rows if row["stream"] == "validation" and row["method"] == method and select(row)]
            valid = [row for row in subset if row["status"] == "valid"]
            errors = np.asarray([abs(row["relative_null_rate_error"]) for row in valid])
            summaries.append({"group": group, "method": method, "total_checks": len(subset),
                "valid_checks": len(valid), "unavailable_checks": len(subset)-len(valid),
                "observed_within_10pct": sum(abs(row["relative_null_rate_error"]) <= 0.1+1e-14 for row in valid),
                "interval_inside_10pct": sum(row["pointwise_classification"] == "pointwise_interval_inside_10pct_band" for row in valid),
                "interval_disjoint_10pct": sum(row["pointwise_classification"] == "pointwise_interval_disjoint_from_10pct_band" for row in valid),
                "median_abs_rate_error": float(np.median(errors)) if len(errors) else None,
                "p90_abs_rate_error": float(np.quantile(errors, .9)) if len(errors) else None,
                "max_abs_rate_error": float(np.max(errors)) if len(errors) else None})
    return summaries


def make_plot(out, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    methods = [family+"_"+method for family in ("quantile", "gpd") for method in SMOOTHERS]
    interior = GRID[1:-1]
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), gridspec_kw={"width_ratios": [1, 1.4, 1.4]}, layout="constrained")
    for method in ["empirical_exact_m"] + methods:
        subset = sorted([row for row in rows if row["stream"] == "validation" and row["method"] == method
                         and row["nominal_p"] == .001 and row["status"] == "valid"], key=lambda row: row["m"])
        axes[0].plot([row["m"] for row in subset], [row["cutoff"] for row in subset],
                     marker=".", label=method, linewidth=1)
    axes[0].set(xscale="log", yscale="log", xlabel="m", ylabel="MI cutoff", title="p=0.001; leave-size-out candidates")
    axes[0].legend(fontsize=7)
    for ax, p in zip(axes[1:], PRIMARY_P):
        matrix = np.full((len(interior), len(methods)), np.nan)
        for i, m in enumerate(interior):
            for j, method in enumerate(methods):
                row = next(row for row in rows if row["stream"] == "validation" and row["method"] == method and row["m"] == m and row["nominal_p"] == p)
                if row["status"] == "valid":
                    matrix[i, j] = 100*row["relative_null_rate_error"]
        im = ax.imshow(matrix, aspect="auto", cmap="RdBu_r", vmin=-30, vmax=30)
        ax.set(xticks=range(len(methods)), xticklabels=[method.replace("_", "\n", 1) for method in methods],
               yticks=range(len(interior)), yticklabels=interior, title=f"Validation null-rate error (%), p={p:g}", ylabel="Omitted m")
        for i in range(len(interior)):
            for j in range(len(methods)):
                if math.isfinite(matrix[i, j]):
                    ax.text(j, i, f"{matrix[i,j]:.0f}", ha="center", va="center", fontsize=7,
                            color="white" if abs(matrix[i,j]) >= 20 else "black")
        fig.colorbar(im, ax=ax, shrink=.7, label="Error; colors saturate at +/-30%")
    fig.suptitle("Exploratory reuse of previously inspected nulls; no fresh confirmation", fontsize=12)
    fig.savefig(out / "feasibility.png", dpi=160)
    fig.savefig(out / "feasibility.svg")
    plt.close(fig)


def run(args):
    started = time.perf_counter()
    out, source = args.out.resolve(), args.source_run.resolve()
    if not 1 <= args.workers <= 12:
        raise ValueError("workers must be between 1 and 12")
    allowed = (ROOT / "runs").resolve()
    if not out.is_relative_to(allowed) or out == allowed or out.exists():
        raise ValueError("output must be a fresh child of this repository's ignored runs/")
    if out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError("source/output overlap")
    plan = extract.SUMMARY.load_plan(source)
    if sorted(plan["m"]) != GRID:
        raise ValueError("wrong source grid")
    out.mkdir(parents=True)
    code_paths = sorted(Path(__file__).parent.glob("*.py")) + [Path(__file__).with_name("PLAN.md")]
    request = {"format": "apmi-smooth-feasibility-v1", "started_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv, "source_run": str(source), "out": str(out), "workers": args.workers,
        "new_null_draws": 0, "m": GRID, "knot_p": KNOT_P, "probe_p": PROBE_P,
        "source_plan_sha256": sha256(source / "plan.json"),
        "code_sha256": {path.name: sha256(path) for path in code_paths},
        "environment": {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
                        "scipy": scipy.__version__, "numerical_threads": 1}}
    write_json(out / "request.json", request)
    code_out = out / "code"
    code_out.mkdir()
    for path in code_paths:
        shutil.copy2(path, code_out / path.name)
    items, failures = [], []
    extraction_start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(extract.process_one_m, source, m, ALL_P, out / f"m{m:05d}"): m for m in GRID}
        for future in as_completed(futures):
            m = futures[future]
            try:
                items.append(future.result())
                print(f"Verified and extracted m={m} ({len(items)}/{len(GRID)})", flush=True)
            except Exception as exc:
                failures.append({"m": m, "error": type(exc).__name__+": "+str(exc)})
                print(f"FAILED m={m}: {exc}", flush=True)
    extraction_seconds = time.perf_counter()-extraction_start
    if failures:
        write_json(out / "failure.json", {"failures": failures, "completed_m": sorted(item["m"] for item in items),
                   "elapsed_seconds": time.perf_counter()-started})
        raise ValueError("extraction failures retained; no candidate fitting performed")
    items.sort(key=lambda item: item["m"])
    write_json(out / "extraction.json", items)
    prediction_start = time.perf_counter()
    predictions = prediction_specs(items)
    write_json(out / "predictions.json", predictions)
    rows = score_predictions(predictions, items)
    write_csv(out / "evaluation.csv", rows)
    summaries = summarize(rows)
    write_csv(out / "summary.csv", summaries)
    make_plot(out, rows)
    write_json(out / "completion.json", {"format": request["format"], "finished_utc": datetime.now(timezone.utc).isoformat(),
        "request_sha256": sha256(out / "request.json"), "new_null_draws": 0,
        "m_count": len(items), "prediction_count": len(predictions), "evaluation_rows": len(rows),
        "extraction_seconds": extraction_seconds, "analysis_seconds": time.perf_counter()-prediction_start,
        "elapsed_seconds": time.perf_counter()-started, "summaries": summaries,
        "outputs_sha256": {name: sha256(out/name) for name in
                           ("extraction.json", "predictions.json", "evaluation.csv", "summary.csv", "feasibility.png", "feasibility.svg")}})
    print(f"Completed without new simulations: {out}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
