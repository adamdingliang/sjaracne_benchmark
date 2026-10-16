#!/usr/bin/env python3
"""Refine the p axis using existing sorted AP-MI nulls; never generate draws."""
from __future__ import annotations

import os
for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                  "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_variable] = "1"

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import time

import numpy as np
import scipy

import cache
import grid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = HERE.parent / "smooth_feasibility"
sys.path.append(str(OLD))
import analyze as previous
import models

sha256, write_json, write_csv = previous.sha256, previous.write_json, previous.write_csv
METHODS = tuple(kind+"_"+method for kind in ("coarse", "dense") for method in grid.SMOOTHERS) + (
    "exact_m_coarse_p_only", "exact_m_dense_p_only", "empirical_exact_m")


def read_source(source):
    source = Path(source).resolve(strict=True)
    if not source.is_relative_to(ROOT / "runs"):
        raise ValueError("source must be an existing repository runs/ child")
    request = json.loads((source / "request.json").read_text(encoding="utf-8"))
    completed = json.loads((source / "completion.json").read_text(encoding="utf-8"))
    archive = OLD / "results_2026-10-15"
    for name in ("request.json", "completion.json", "extraction.json", "evaluation.csv"):
        if sha256(source / name) != sha256(archive / name):
            raise ValueError("source differs from frozen first-analysis evidence: "+name)
    if (request["format"] != "apmi-smooth-feasibility-v1" or request["new_null_draws"] != 0 or
            completed["request_sha256"] != sha256(source / "request.json") or
            completed["m_count"] != 19 or completed["evaluation_rows"] != 4864):
        raise ValueError("unexpected original feasibility design")
    for name, digest in completed["outputs_sha256"].items():
        if Path(name).name != name or sha256(source / name) != digest:
            raise ValueError("source output hash mismatch")
    for name in ("analyze.py", "models.py", "extract.py"):
        if sha256(OLD / name) != request["code_sha256"][name]:
            raise ValueError("frozen numerical helper changed: "+name)
    items = json.loads((source / "extraction.json").read_text(encoding="utf-8"))
    if [item["m"] for item in items] != list(grid.GRIDM):
        raise ValueError("expected original nineteen-size extraction")
    verifier = HERE.parent / "expanded_10m" / "summarize.py"
    if any(item["source"]["verification_helper_sha256"] != sha256(verifier) for item in items):
        raise ValueError("original verification helper changed")
    return items


def quantile_map(item):
    return {row["nominal_p"]: row["cutoff"] for row in item["quantiles"]}


def diagnose_knots(p_knots, cutoffs):
    order = np.argsort(p_knots)
    p, values = np.asarray(p_knots)[order], np.asarray(cutoffs)[order]
    crossings = [{"smaller_p": float(p[i]), "larger_p": float(p[i+1]),
                  "smaller_p_cutoff": float(values[i]), "larger_p_cutoff": float(values[i+1])}
                 for i in range(len(p)-1)
                 if math.isfinite(values[i]) and math.isfinite(values[i+1]) and values[i+1] > values[i]]
    return {"p_knots": list(p_knots),
            "predicted_cutoff_knots": [float(x) if math.isfinite(x) else None for x in cutoffs],
            "crossings": crossings}


def prediction_specs(items):
    sizes = np.asarray([item["m"] for item in items])
    if sizes.tolist() != list(grid.GRIDM):
        raise ValueError("expected all nineteen sizes in order")
    maps = [quantile_map(item) for item in items]
    tables = {kind: np.asarray([[mapping[p] for p in p_knots] for mapping in maps])
              for kind, p_knots in (("coarse",grid.COARSE_P),("dense",grid.DENSE_P))}
    result, diagnostics = [], []
    for index, item in enumerate(items):
        m = item["m"]
        fold = "endpoint_extrapolation" if m in (min(sizes), max(sizes)) else "interior_interpolation"
        train = sizes != m
        for method in METHODS:
            baseline = method.startswith("exact_m") or method == "empirical_exact_m"
            kind = "dense" if "dense" in method else "coarse" if "coarse" in method else "exact"
            smoother = None if baseline else method.split("_",1)[1]
            p_knots = grid.DENSE_P if kind == "dense" else grid.COARSE_P
            reason, values = None, None
            diag = {"m":m, "method":method, "fold_kind":fold, "baseline_uses_own_m":baseline,
                    "train_m":[m] if baseline else sizes[train].tolist(), "crossings":[]}
            try:
                if method == "empirical_exact_m":
                    values = np.asarray([maps[index][p] for p in grid.ALL_P])
                else:
                    if smoother == "pchip" and not min(sizes[train]) <= m <= max(sizes[train]):
                        raise ValueError("outside_training_m_range_no_extrapolation")
                    knots = (tables[kind][index] if baseline else
                             models.predict_quantiles(sizes[train], tables[kind][train], m, smoother))
                    diag.update(diagnose_knots(p_knots, knots))
                    values = models.interpolate_probability(p_knots, knots, grid.ALL_P)
            except (ValueError, FloatingPointError, OverflowError) as exc:
                reason = str(exc)
            diag["invalid_reason"] = reason
            diagnostics.append(diag)
            for pi, p in enumerate(grid.ALL_P):
                cutoff, point_reason = None, reason
                if point_reason is None:
                    try:
                        cutoff = previous.valid_cutoff(float(values[pi]),m)
                    except (ValueError, FloatingPointError, OverflowError) as exc:
                        point_reason = str(exc)
                roles = grid.probability_roles(p)
                result.append({"m":m, "fold_kind":fold, "method":method,
                    "family":"exact_m_baseline" if baseline else "quantile", "smoother":smoother,
                    "grid_kind":kind, "nominal_p":p, "p_role":"new_probe" if roles["new_probe"] else "regression_or_knot",
                    **{key:value for key,value in roles.items() if key != "p"},
                    "cutoff":cutoff,"empirical_cutoff":maps[index][p],
                    "status":"valid" if point_reason is None else "unavailable",
                    "invalid_reason":point_reason, "train_m":diag["train_m"], "predicted_parameters":None})
    return result, diagnostics


def summarize(rows):
    selectors = {
        "main_new_probes": lambda r:r["new_probe"] and r["moderate"],
        "all_new_probes_to_1e_minus4": lambda r:r["new_probe"],
        "operating_probabilities": lambda r:r["primary"],
        "old_moderate_regression": lambda r:r["old_query"] and r["moderate"],
        "all_moderate_queries": lambda r:r["moderate"],
        "lower_new_probes": lambda r:r["new_probe"] and r["lower_diagnostic"],
    }
    groups = [(name, "interior_interpolation", select) for name, select in selectors.items()]
    groups += [("endpoint_operating", "endpoint_extrapolation", lambda r:r["primary"])]
    summaries = []
    for name, fold, select in groups:
        for method in METHODS:
            subset = [r for r in rows if r["stream"] == "validation" and r["method"] == method and r["fold_kind"] == fold and select(r)]
            valid = [r for r in subset if r["status"] == "valid"]
            errors = [abs(r["relative_null_rate_error"]) for r in valid]
            within = sum(error <= .1+1e-14 for error in errors)
            summaries.append({"group":name,"method":method,"total_checks":len(subset),"valid_checks":len(valid),
                "unavailable_checks":len(subset)-len(valid),"observed_within_10pct":within,
                "within_fraction_full_denominator":within/len(subset) if subset else None,
                "interval_inside_10pct":sum(r["pointwise_classification"] == "pointwise_interval_inside_10pct_band" for r in valid),
                "interval_disjoint_10pct":sum(r["pointwise_classification"] == "pointwise_interval_disjoint_from_10pct_band" for r in valid),
                "median_abs_rate_error":float(np.median(errors)) if errors else None,
                "p90_abs_rate_error":float(np.quantile(errors,.9)) if errors else None,
                "max_abs_rate_error":max(errors) if errors else None})
    return summaries


def check_regression(rows, source):
    import csv
    with (Path(source)/"evaluation.csv").open(encoding="utf-8",newline="") as handle:
        old = {(int(r["m"]),float(r["nominal_p"]),r["stream"],r["method"]):r for r in csv.DictReader(handle)}
    compared, differences = 0, []
    for row in rows:
        if not row["method"].startswith("coarse_") or not row["old_query"]:
            continue
        key = (row["m"],row["nominal_p"],row["stream"],row["method"].replace("coarse_","quantile_",1))
        prior = old[key]
        compared += 1
        equal = row["status"] == prior["status"]
        if row["status"] == "valid" and equal:
            equal = math.isclose(row["cutoff"],float(prior["cutoff"]),rel_tol=1e-12,abs_tol=1e-14)
            equal = equal and all(row[name] == int(prior[name]) for name in ("ge","gt","ties","draws"))
        if not equal:
            differences.append({"key":list(key),"current":row,"previous":prior})
    return {"compared_rows":compared,"expected_rows":19*16*3*2,"differences":differences,
            "passed":compared == 19*16*3*2 and not differences}


def per_probability(rows):
    result = []
    for p in grid.ALL_P:
        for method in METHODS:
            subset = [r for r in rows if r["nominal_p"] == p and r["method"] == method and
                      r["stream"] == "validation" and r["fold_kind"] == "interior_interpolation"]
            valid = [r for r in subset if r["status"] == "valid"]
            errors = [abs(r["relative_null_rate_error"]) for r in valid]
            result.append({"p":p,"method":method,**{key:value for key,value in grid.probability_roles(p).items() if key != "p"},
                "total":len(subset),"valid":len(valid),"within_10pct":sum(e <= .1+1e-14 for e in errors),
                "median_abs_error":float(np.median(errors)) if errors else None,
                "max_abs_error":max(errors) if errors else None})
    return result


def make_plot(out, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ps = [p for p in grid.NEW_PROBE_P if p >= .0005]
    sizes = grid.GRIDM[1:-1]
    methods = ("coarse_logquadratic","dense_logquadratic","exact_m_dense_p_only")
    lookup = {(r["method"],r["m"],r["nominal_p"]):r for r in rows if r["stream"] == "validation"}
    fig, axes = plt.subplots(1,3,figsize=(18,6),layout="constrained",sharey=True)
    for ax, method in zip(axes,methods):
        values = np.full((len(sizes),len(ps)),np.nan)
        for i,m in enumerate(sizes):
            for j,p in enumerate(ps):
                row = lookup[(method,m,p)]
                if row["status"] == "valid":
                    values[i,j] = 100*row["relative_null_rate_error"]
        cmap = plt.get_cmap("RdBu_r").copy()
        cmap.set_bad("#b0b0b0")
        im = ax.imshow(values,cmap=cmap,vmin=-30,vmax=30,aspect="auto")
        ax.set(xticks=range(len(ps)),xticklabels=[f"{p:.2g}" for p in ps],
               yticks=range(len(sizes)),yticklabels=sizes,xlabel="New off-knot probability probes (p)",
               title=method.replace("_"," "))
        ax.tick_params(axis="x",rotation=70,labelsize=8)
    axes[0].set_ylabel("Omitted sample size m (exact-m baseline at right uses own m)")
    fig.colorbar(im,ax=axes,shrink=.8,label="Validation relative null-rate error (%), color limit +/-30")
    fig.suptitle("Denser-p exploratory refinement; gray = unavailable; previously inspected data",fontsize=12)
    fig.savefig(out/"refinement.png",dpi=160)
    fig.savefig(out/"refinement.svg")
    plt.close(fig)


def run(args):
    start = time.perf_counter()
    source,out = args.source.resolve(strict=True),args.out.resolve()
    if not 1 <= args.workers <= 12:
        raise ValueError("workers must be 1..12")
    if out.exists() or out == ROOT/"runs" or not out.is_relative_to(ROOT/"runs"):
        raise ValueError("output must be a fresh repository runs/ child")
    if out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError("source/output overlap")
    items = read_source(source)
    out.mkdir(parents=True)
    code_paths = [HERE/name for name in ("run.py","grid.py","cache.py","test_grid.py","test_cache.py","test_run.py","PLAN.md")]
    code_paths += [OLD/name for name in ("analyze.py","models.py","extract.py")]
    code_paths += [HERE.parent/"expanded_10m"/"summarize.py"]
    request = {"format":"apmi-p-axis-refinement-v1","started_utc":datetime.now(timezone.utc).isoformat(),
        "command":sys.argv,"source":str(source),"out":str(out),"workers":args.workers,
        "new_null_draws":0,"new_large_copies":0,"grid":grid.grid_manifest(),
        "source_sha256":{name:sha256(source/name) for name in ("request.json","completion.json","extraction.json","evaluation.csv")},
        "code_sha256":{path.relative_to(ROOT).as_posix():sha256(path) for path in code_paths},
        "environment":{"python":sys.version,"platform":platform.platform(),"numpy":np.__version__,"scipy":scipy.__version__,"threads_per_worker":1}}
    write_json(out/"request.json",request)
    for path in code_paths:
        target = out/"execution_code"/path.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
    extracted,failures = [],[]
    extraction_start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(cache.verify_cache_one,item,grid.ALL_P):item["m"] for item in items}
        for future in as_completed(futures):
            m = futures[future]
            try:
                extracted.append(future.result())
                print(f"Verified existing cache; extracted p quantiles m={m} ({len(extracted)}/19)",flush=True)
            except Exception as exc:
                failures.append({"m":m,"error":type(exc).__name__+": "+str(exc)})
                print(f"FAILED m={m}: {exc}",flush=True)
    extraction_seconds = time.perf_counter()-extraction_start
    if failures:
        write_json(out/"failure.json",{"failures":failures,"verified_m":sorted(item["m"] for item in extracted)})
        raise ValueError("input verification failures retained; no fitting performed")
    extracted.sort(key=lambda item:item["m"])
    write_json(out/"extraction.json",extracted)
    analysis_start = time.perf_counter()
    predictions,diagnostics = prediction_specs(extracted)
    write_json(out/"predictions.json",predictions)
    write_json(out/"knot_diagnostics.json",diagnostics)
    rows = previous.score_predictions(predictions,extracted)
    write_csv(out/"evaluation.csv",rows)
    regression = check_regression(rows,source)
    write_json(out/"old_result_reproduction.json",regression)
    if not regression["passed"]:
        raise ValueError("earlier coarse results failed reproduction; artifacts retained")
    summaries = summarize(rows)
    write_csv(out/"summary.csv",summaries)
    write_csv(out/"per_probability.csv",per_probability(rows))
    make_plot(out,rows)
    names = ("extraction.json","predictions.json","knot_diagnostics.json","evaluation.csv",
             "old_result_reproduction.json","summary.csv","per_probability.csv","refinement.png","refinement.svg")
    write_json(out/"completion.json",{"format":request["format"],"finished_utc":datetime.now(timezone.utc).isoformat(),
        "request_sha256":sha256(out/"request.json"),"new_null_draws":0,"new_large_copies":0,
        "m_count":len(extracted),"query_probability_count":len(grid.ALL_P),"evaluation_rows":len(rows),
        "prediction_count":len(predictions),"extraction_seconds":extraction_seconds,
        "analysis_seconds":time.perf_counter()-analysis_start,"elapsed_seconds":time.perf_counter()-start,
        "summaries":summaries,"outputs_sha256":{name:sha256(out/name) for name in names}})
    print(f"Completed refinement with no new draws: {out}",flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--workers",type=int,default=12)
    run(parser.parse_args())
