#!/usr/bin/env python3
"""Prospectively gated two-surface analysis; never generates new null draws."""
from __future__ import annotations

import os
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_key] = "1"

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
import math
from pathlib import Path
import platform
import sys
import time

import numpy as np
import scipy

try:
    from . import fit_data, fit_models, fit_report, generate
except ImportError:
    import fit_data, fit_models, fit_report, generate

HERE = Path(__file__).resolve().parent
GRID = fit_models._GRID
METHODS = fit_models.METHODS
GENERATION_HASH = "003c3feb92d425fea56ef40edab4f747b3201a6e9176b7971a228c9bba5538b3"
LEGACY = (1.062, -48.7, -0.634)


def locked_write(path, value):
    path = Path(path)
    generate.write_new(path, value)
    with path.with_suffix(".sha256").open("x", encoding="ascii") as handle:
        handle.write(generate.sha256(path) + "\n")
    return generate.record(path)


def read_locked(path):
    path = Path(path)
    if path.with_suffix(".sha256").read_text(encoding="ascii").strip() != generate.sha256(path):
        raise ValueError("immutable record hash mismatch: " + str(path))
    return generate.read_json(path)


def groups():
    return {group: [m for m in generate.GRID if fit_data.m_group(m) == group]
            for group in ("training", "development", "final_interpolation_test")}


def legacy_predictions(m, probabilities):
    alpha, beta, gamma = LEGACY
    result = []
    for p in probabilities:
        cutoff = (alpha - math.log(p)) / (-beta - gamma * m)
        valid = math.isfinite(cutoff) and 0 < cutoff <= math.log(m)
        result.append({"m": m, "p": p, "available": valid,
                       "cutoff": cutoff if valid else None,
                       "cutoff_hex": cutoff.hex() if valid else None,
                       "source": "legacy_affine", "reason": None if valid else "invalid_legacy_cutoff"})
    return result


def shape_check(model):
    rows = [row for m in generate.GRID
            for row in fit_models.predict_surface(model, m, GRID.ALL_P)]
    failures = [row for row in rows if not row["available"]]
    moderate = [row for row in failures if row["p"] >= 0.0001]
    return {"eligible": not moderate, "queries": len(rows),
            "moderate_failures": moderate, "rare_failures": [r for r in failures if r["p"] < 0.0001]}


def restart_evidence(path):
    """Audit the failed pre-selection attempt without opening scientific arrays."""
    root = Path(path).resolve(strict=True)
    fit_data._reject_links(root)
    boundary = (generate.repo_root() / "runs").resolve(strict=True)
    if root == boundary or not root.is_relative_to(boundary):
        raise ValueError("restart evidence must be an existing ignored analysis run")
    old = read_locked(root / "request.json")
    if (old.get("format") != "apmi-two-surface-analysis-request-v1"
            or old.get("plan_sha256") != GENERATION_HASH
            or old.get("groups") != groups()):
        raise ValueError("restart evidence belongs to a different analysis protocol")
    failure = generate.read_json(root / "failure.json")
    if failure.get("error") != "ValueError('MI draws must be nonnegative')":
        raise ValueError("this correction applies only to the recorded roundoff-guard failure")
    sealed_artifacts = ("selection.json", "primary.json", "access_selected.json", "access_final.json",
                        "refit_models.json", "final_scores.csv", "summary.json", "validation_index.json",
                        "test_fit_index.json", "cache/validation", "cache/test_fit")
    if any((root / name).exists() for name in sealed_artifacts):
        raise ValueError("prior selection or final access prevents this pre-selection restart")
    training = read_locked(root / "training_index.json")
    development = read_locked(root / "development_index.json")
    read_locked(root / "initial_models.json")
    for phase, index in (("training", training), ("development", development)):
        if sorted(row["m"] for row in index["records"]) != groups()[phase]:
            raise ValueError("failed-run extraction coverage changed")
        for row in index["records"]:
            fit_data._check_record(row["cache"])
    evidence = {name: generate.record(root / name) for name in
                ("request.json", "failure.json", "initial_models.json", "training_index.json", "development_index.json")}
    return {"failed_run": str(root), "evidence": evidence,
            "earlier_statistical_access": "160 training and20 development fitting streams; initial surfaces and partial internal scoring",
            "selection_recorded": False, "final_statistical_access": False,
            "authorization": "Explicit user-approved numerical-zero correction and restart; no new draws"}


def make_request(args):
    plan, digest = generate.load_plan(args.plan)
    if digest != GENERATION_HASH:
        raise ValueError("this analysis requires the frozen October16 generation plan")
    out = args.out.absolute()
    boundary = (generate.repo_root() / "runs").resolve(strict=True)
    fit_data._reject_links(out)
    if out.exists() or not out.resolve().is_relative_to(boundary) or out.resolve() == boundary:
        raise ValueError("analysis output must be a fresh ignored runs/ child")
    history = restart_evidence(args.restart_from)
    sources = ["fit_pipeline.py", "test_fit_pipeline.py", "fit_models.py", "test_fit_models.py",
               "fit_data.py", "test_fit_data.py", "fit_report.py", "test_fit_report.py",
               "AMENDMENT_2026-10-17.md", "ANALYSIS_SPEC_2026-10-16.md", "CORRECTION_2026-10-17.md"]
    pins = {name: generate.record(HERE / name) for name in sources}
    pins["probability_grid"] = generate.record(HERE.parent / "p_axis_refinement" / "grid.py")
    pins["generation_controller"] = generate.record(HERE / "generate.py")
    pins.update({"restart_" + name: record for name, record in history["evidence"].items()})
    pins["legacy_config"] = generate.record(Path(plan["engine_root"]) / "SJARACNe/config/config_threshold.txt")
    config_text = Path(pins["legacy_config"]["path"]).read_text().splitlines()
    values = [line for line in config_text if line.strip() and not line.startswith(">")]
    if tuple(map(float, values[0].split())) != LEGACY:
        raise ValueError("legacy comparator coefficients changed")
    out.mkdir(parents=True, exist_ok=False)
    request = {"format": "apmi-two-surface-analysis-request-v1", "created_utc": generate.utc_now(),
               "generation_plan": generate.record(args.plan), "plan_sha256": digest,
               "output_dir": str(out), "pins": pins, "max_workers": 12,
               "groups": groups(), "p_knots": list(GRID.DENSE_P), "query_p": list(GRID.ALL_P),
               "report_p": list(GRID.COARSE_P), "selection_p": list(fit_models.SELECTION_P),
               "candidate_order": list(METHODS), "selection_tie_absolute": 1e-12,
               "initial_draws": {"construction": 8_000_000, "internal_diagnostic": 2_000_000},
               "refit_draws": 10_000_000, "validation_draws": 10_000_000,
               "versions": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__,
                            "platform": platform.platform()},
               "code_commit": generate.git_output(generate.repo_root(), "rev-parse", "HEAD"),
               "restart_history": history,
               "no_final_statistical_access_before_this_record": True,
               "numerical_zero_policy": {"lower_inclusive": -fit_data.SUPPORT_TOLERANCE,
                                         "upper_exclusive": 0, "replacement": "+0.0",
                                         "preserve_original_raw_bytes": True},
               "amendment": "Focused empirical quadratic/PCHIP selection; full104-candidate analysis deferred.",
               "no_fallback": True}
    request_record = locked_write(out / "request.json", request)
    gate = {"format": fit_data.GATE_SCHEMA, "stage": "analysis_frozen", "plan_sha256": digest,
            "analysis_plan_sha256": request_record["sha256"], "pins": {**pins, "request": request_record}}
    locked_write(out / "access_initial.json", gate)
    print(json.dumps({"request": str(out / "request.json"), "sha256": request_record["sha256"]}), flush=True)


def check_request(path):
    request = read_locked(path)
    if request.get("format") != "apmi-two-surface-analysis-request-v1":
        raise ValueError("unknown analysis request")
    for record in request["pins"].values():
        fit_data._check_record(record)
    fit_data._check_record(request["generation_plan"])
    if (request["groups"] != groups() or request["candidate_order"] != list(METHODS)
            or request["query_p"] != list(GRID.ALL_P) or request["p_knots"] != list(GRID.DENSE_P)):
        raise ValueError("frozen grid/candidates changed")
    if request["versions"]["numpy"] != np.__version__ or request["versions"]["scipy"] != scipy.__version__:
        raise ValueError("numerical library versions changed")
    return request


def worker(task):
    phase, plan, m, out, gate = task
    if phase == "training":
        fit_data.extract_training(plan, m, out, GRID.DENSE_P, gate)
    elif phase == "development":
        fit_data.extract_development(plan, m, out, gate)
    elif phase == "refit":
        fit_data.extract_refit(plan, m, out, GRID.ALL_P, gate)
    elif phase == "validation":
        fit_data.extract_final_validation(plan, m, out, gate)
    elif phase == "test_fit":
        fit_data.extract_final_test_fit(plan, m, out, GRID.ALL_P, gate)
    else:
        raise ValueError("unknown extraction phase")
    return str(Path(out) / "cache.json")


def extract_phase(request, phase, ms, gate):
    root = Path(request["output_dir"])
    stage = root / "cache" / phase
    stage.mkdir(parents=True, exist_ok=False)
    tasks = [(phase, request["generation_plan"]["path"], m, str(stage / f"m{m:05d}"), str(gate)) for m in ms]
    records, start = [], time.monotonic()
    with ProcessPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(worker, task): task[2] for task in tasks}
        for future in as_completed(futures):
            cache = future.result()
            records.append({"m": futures[future], "cache": generate.record(cache)})
            state = {"phase": phase, "complete": len(records), "total": len(tasks),
                     "elapsed_seconds": time.monotonic() - start, "updated_utc": generate.utc_now()}
            generate.atomic_status(root / "status.json", state)
            print(json.dumps(state), flush=True)
    records.sort(key=lambda r: r["m"])
    locked_write(root / (phase + "_index.json"), {"phase": phase, "records": records})
    return records


def caches(records):
    return {r["m"]: generate.read_json(r["cache"]["path"]) for r in records}


def matrix(cache_map):
    ms = sorted(cache_map)
    rows = []
    for m in ms:
        quantiles = {r["p"]: r["cutoff"] for r in cache_map[m]["quantiles"]}
        rows.append([quantiles[p] for p in GRID.DENSE_P])
    return ms, np.asarray(rows, dtype=np.float64)


def score_cache(cache_map, models, phase, primary_method=None, legacy=False, empirical=None):
    rows = []
    for m, cache in sorted(cache_map.items()):
        name = "internal" if phase == "internal" else "score"
        values = fit_data.load_array(cache, name)
        expected = 2_000_000 if phase == "internal" else 10_000_000
        if len(values) != expected:
            raise ValueError("unexpected scoring draw count")
        for method, model in models.items():
            predictions = fit_models.predict_surface(model, m, GRID.ALL_P)
            rows.extend(fit_report.score_predictions(values, predictions, method, phase,
                                                    primary=(phase == "final_validation" and method == primary_method)))
        if legacy:
            rows.extend(fit_report.score_predictions(values, legacy_predictions(m, GRID.ALL_P),
                                                    "legacy_affine", phase))
        if empirical is not None:
            predictions = empirical[m]
            rows.extend(fit_report.score_predictions(values, predictions, "exact_m_empirical", phase))
    for row in rows:
        row["m_group"] = fit_data.m_group(int(row["m"]))
        audit = cache_map[int(row["m"])]["source"].get("normalization", {})
        row["source_stream_corrected_negative_count"] = audit.get("negative_count")
        row["source_stream_raw_minimum"] = audit.get("raw_minimum")
    return rows


def write_csv(path, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def choose(development_rows, checks):
    candidates = []
    for method in METHODS:
        cells = [dict(row, n=row.get("n"), count=row.get("count")) for row in development_rows
                 if row["method"] == method and row["p"] in fit_models.SELECTION_P]
        score = fit_models.selection_loss(cells)
        if not checks[method]["eligible"]:
            score.update(eligible=False, loss=None)
            score["failures"].append("moderate_shape_failure_on_200_size_grid")
        candidates.append({"method": method, **score})
    return {"candidates": candidates, **fit_models.select_surface(candidates)}


def primary_artifact(request, winner, ms, model, selection_record):
    return {"format": "apmi-two-surface-frozen-primary-v1", "selected_model": winner,
            "generation_plan_sha256": request["plan_sha256"], "training_m": ms,
            "surface": {"fit_models": model}, "selection_sha256": selection_record["sha256"],
            "supported_domain": {"m_min": 50, "m_max": 10000, "p_min": .0005, "p_max": .05},
            "created_utc": generate.utc_now(), "no_fallback": True}


def run(args):
    request = check_request(args.request)
    root = Path(request["output_dir"])
    # Exclusive whole-analysis ownership; no repeated fitting/final peeking.
    with (root / "started.json").open("x", encoding="utf-8") as handle:
        json.dump({"utc": generate.utc_now(), "pid": os.getpid()}, handle)
    try:
        initial_gate = root / "access_initial.json"
        training = caches(extract_phase(request, "training", request["groups"]["training"], initial_gate))
        development = caches(extract_phase(request, "development", request["groups"]["development"], initial_gate))
        ms, quantiles = matrix(training)
        models = {method: fit_models.fit_surface(ms, quantiles, method) for method in METHODS}
        checks = {method: shape_check(model) for method, model in models.items()}
        locked_write(root / "initial_models.json", {"models": models, "shape_checks": checks})
        internal_rows = score_cache(training, models, "internal")
        dev_rows = score_cache(development, models, "development")
        write_csv(root / "internal_scores.csv", internal_rows)
        write_csv(root / "development_scores.csv", dev_rows)
        choice = choose(dev_rows, checks)
        winner = choice["selected_method"]
        selection = {"format": "apmi-two-surface-selection-v1", "stage": "selected",
                     "plan_sha256": request["plan_sha256"],
                     "analysis_plan_sha256": generate.sha256(args.request),
                     "selected_model": winner, "eligible": winner is not None,
                     "no_fallback": True, "created_utc": generate.utc_now(), **choice}
        selected_record = locked_write(root / "selection.json", selection)
        print(json.dumps({"selection": choice}), flush=True)
        if winner is None:
            raise ValueError("neither method is eligible: final streams remain sealed")
        initial = read_locked(initial_gate)
        selected_gate = {**initial, "stage": "selected", "selection_lock": selected_record}
        locked_write(root / "access_selected.json", selected_gate)
        non_test = sorted(ms + request["groups"]["development"])
        refit = caches(extract_phase(request, "refit", non_test, root / "access_selected.json"))
        ms, quantiles = matrix(refit)
        final_models = {method: fit_models.fit_surface(ms, quantiles, method) for method in METHODS}
        final_checks = {method: shape_check(model) for method, model in final_models.items()}
        locked_write(root / "refit_models.json", {"models": final_models, "shape_checks": final_checks})
        if not final_checks[winner]["eligible"]:
            raise ValueError("selected primary refit failed moderate shape/support: no fallback; final remains sealed")
        primary = primary_artifact(request, winner, ms, final_models[winner], selected_record)
        primary_record = locked_write(root / "primary.json", primary)
        frozen_gate = {**selected_gate, "stage": "frozen", "primary_model": primary_record,
                       "primary_eligible": True, "no_fallback": True,
                       "pins": {**selected_gate["pins"], "refit_models": generate.record(root / "refit_models.json")}}
        locked_write(root / "access_final.json", frozen_gate)
        print(json.dumps({"primary_frozen": primary_record, "selected_method": winner}), flush=True)
        # Final access is strictly below the frozen gate. No fit/selection calls follow.
        validation = caches(extract_phase(request, "validation", generate.GRID, root / "access_final.json"))
        test_fit = caches(extract_phase(request, "test_fit", request["groups"]["final_interpolation_test"], root / "access_final.json"))
        empirical = {}
        for m, cache in {**refit, **test_fit}.items():
            predictions = [dict(row, m=m, available=0 < row["cutoff"] <= math.log(m),
                                reason=None, source="exact_m_empirical") for row in cache["quantiles"]]
            empirical[m] = predictions
        final_rows = score_cache(validation, final_models, "final_validation", winner, legacy=True, empirical=empirical)
        write_csv(root / "final_scores.csv", final_rows)
        summary = fit_report.summarize(final_rows)
        locked_write(root / "summary.json", {"selection": selection, "primary": primary,
                                            "final_summary": summary, "completed_utc": generate.utc_now()})
        generate.atomic_status(root / "status.json", {"phase": "complete", "primary": winner,
                                                      "updated_utc": generate.utc_now()})
        print(json.dumps({"complete": str(root), "primary": winner}), flush=True)
    except BaseException as error:
        generate.write_new(root / "failure.json", {"utc": generate.utc_now(), "error": repr(error),
                                                   "no_automatic_retry": True})
        generate.atomic_status(root / "status.json", {"phase": "failed", "error": repr(error),
                                                      "updated_utc": generate.utc_now()})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--plan", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    freeze.add_argument("--restart-from", type=Path, required=True)
    launch = sub.add_parser("run")
    launch.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    make_request(args) if args.command == "freeze" else run(args)


if __name__ == "__main__":
    main()
