#!/usr/bin/env python3
"""Read-only extraction of the existing 19-size 10M null streams.

No generator or GPD optimizer is called. The only large outputs are independently
sorted copies under a fresh, ignored ``runs/`` child. Original frozen evidence is
verified using the expanded sweep's own helpers and is never modified.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import math
from pathlib import Path

import numpy as np


_HERE = Path(__file__).resolve().parent
_HELPER_PATH = _HERE.parent / "expanded_10m" / "summarize.py"
_SPEC = importlib.util.spec_from_file_location("apmi_smooth_verified_summary", _HELPER_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load frozen-sweep verification helpers")
SUMMARY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(SUMMARY)
RUNS_ROOT = _HERE.parents[2] / "runs"
SCHEMA = "sjaracne-apmi-smooth-feasibility-extraction-v1"


def _vector(values):
    """Check shape only; public lookup utilities require already sorted values."""
    array = np.asarray(values)
    if array.ndim != 1 or not array.size or array.dtype.kind != "f":
        raise ValueError("expected a nonempty one-dimensional sorted floating array")
    return array


def probabilities_checked(probabilities):
    values = list(probabilities)
    if not values or any(isinstance(p, (bool, np.bool_)) for p in values):
        raise ValueError("probabilities must be nonempty and strictly between zero and one")
    converted = [float(p) for p in values]
    if any(not math.isfinite(p) or not 0 < p < 1 for p in converted):
        raise ValueError("probabilities must be finite and strictly between zero and one")
    if len(set(converted)) != len(converted):
        raise ValueError("duplicate probability")
    return converted


def higher_quantile_sorted(sorted_values, probability):
    """Fit-only ``np.quantile(values, 1-p, method='higher')`` without sorting again."""
    values = _vector(sorted_values)
    p = probabilities_checked([probability])[0]
    index = int(math.ceil((values.size - 1) * (1 - p)))
    cutoff = float(values[index])
    if not math.isfinite(cutoff):
        raise ValueError("non-finite quantile")
    return cutoff


def count_sorted(sorted_values, cutoff):
    """Exact >=, >, and tied counts; input must already be sorted ascending.

    This deliberately performs binary searches, not O(N) rescans or randomized
    tie breaking. The engine's threshold comparator is >=.
    """
    values = _vector(sorted_values)
    cutoff = float(cutoff)
    if not math.isfinite(cutoff):
        raise ValueError("cutoff must be finite")
    left = int(np.searchsorted(values, cutoff, side="left"))
    right = int(np.searchsorted(values, cutoff, side="right"))
    return {"ge": int(values.size) - left, "gt": int(values.size) - right,
            "ties": right - left}


def validate_output(run, out_dir):
    """Resolve exact targets; cache writes must stay within ignored runs/."""
    run = Path(run).resolve(strict=True)
    requested = Path(out_dir).absolute()
    # Resolve only after rejecting existing symlink components, even when their
    # current targets happen to be inside the allowed tree.
    for candidate in (requested, *requested.parents):
        if candidate.is_symlink():
            raise ValueError("symlink in output path")
    out = requested.resolve()
    root = RUNS_ROOT.resolve()
    if out == root or root not in out.parents:
        raise ValueError("sorted caches must be in a fresh child of repository runs/")
    if out.exists():
        raise ValueError("output must be a fresh nonexistent directory")
    if out == run or run in out.parents or out in run.parents:
        raise ValueError("output and original run must not contain each other")
    return run, out


def _check_recorded_thresholds(fit_sorted, result):
    for recorded in [result["primary_fit"], *result["stability_fits"]]:
        threshold = higher_quantile_sorted(fit_sorted, 1 - recorded["threshold_quantile"])
        count = count_sorted(fit_sorted, threshold)["gt"]
        pu = (count + 1) / (fit_sorted.size + 1)
        if (not SUMMARY.same_number(recorded["threshold"], threshold) or
                recorded["tail_count"] != count or
                not SUMMARY.same_number(recorded["tail_probability"], pu)):
            raise ValueError("recorded threshold/count/probability disagrees with fitting draws")


def _check_recorded_validation(validation_sorted, result):
    for p in SUMMARY.PROBABILITIES:
        threshold = SUMMARY.cutoff(result["primary_fit"], p)
        matches = [item for item in result["validation"] if SUMMARY.same_number(item["nominal_p"], p)]
        if (len(matches) != 1 or
                matches[0]["exceedances"] != count_sorted(validation_sorted, threshold)["ge"] or
                matches[0]["draws"] != validation_sorted.size or
                not SUMMARY.same_number(matches[0]["cutoff"], threshold)):
            raise ValueError("recorded validation disagrees with raw validation draws")


def process_one_m(run, m, probabilities, out_dir):
    """Verify one original attempt and return JSON-safe extraction/cache records.

    Both raw streams are verified for byte hash, metadata, draw count, finite
    values and AP-MI support before any cache is written. Each is independently
    sorted once with ``np.sort`` (a copy). Rejected original GPD models remain
    rejected; their parameters are retained only as exploratory fitting inputs.
    """
    run, out = validate_output(run, out_dir)
    probabilities = probabilities_checked(probabilities)
    if isinstance(m, (bool, np.bool_)) or int(m) != m:
        raise ValueError("m must be an integer in the frozen grid")
    m = int(m)
    plan = SUMMARY.load_plan(run)
    stage = SUMMARY.stage_for_m(m)
    parent = run / "jobs" / ("m%05d" % m)
    attempts = sorted(parent.glob("attempt_*"))
    attempt = parent / "attempt_0001"
    if attempts != [attempt] or not attempt.is_dir():
        raise ValueError("expected exactly original attempt_0001, not a retry or missing attempt")
    record = SUMMARY.read_json(attempt / "result.json")
    if record.get("m") != m or record.get("status") not in {"accepted", "rejected"}:
        raise ValueError("original attempt must be a completed scientific result for this m")
    artifact_hashes = SUMMARY.verify_attempt(attempt, record)
    result, original_confidence = SUMMARY.inspect_report(attempt, plan, m, record)
    raw_provenance, sorted_streams = {}, {}
    for stream in ("fit", "validation"):
        raw, provenance = SUMMARY.raw_values(
            attempt, plan, m, stream, result["model"][stream + "_values_sha256"])
        raw.setflags(write=False)
        sorted_streams[stream] = np.sort(raw)
        raw_provenance[stream] = provenance
        del raw
    if raw_provenance["fit"]["seed"] == raw_provenance["validation"]["seed"]:
        raise ValueError("fit and validation seeds must differ")
    if raw_provenance["fit"]["sha256"] == raw_provenance["validation"]["sha256"]:
        raise ValueError("fit and validation raw streams must differ")
    _check_recorded_thresholds(sorted_streams["fit"], result)
    _check_recorded_validation(sorted_streams["validation"], result)
    quantiles = []
    for p in probabilities:
        threshold = higher_quantile_sorted(sorted_streams["fit"], p)
        counts = count_sorted(sorted_streams["fit"], threshold)
        quantiles.append({"nominal_p": p, "cutoff": threshold,
                          "fit_ge": counts["ge"], "fit_gt": counts["gt"],
                          "fit_ties": counts["ties"], "fit_draws": int(sorted_streams["fit"].size),
                          "method": "fit-only empirical higher quantile"})
    source = {"run": str(run), "attempt": attempt.relative_to(run).as_posix(),
              "plan_sha256": SUMMARY.sha256(run / "plan.json"),
              "result_sha256": SUMMARY.sha256(attempt / "result.json"),
              "report_sha256": SUMMARY.sha256(attempt / "calibration" / "calibration_report.json"),
              "artifact_sha256": artifact_hashes,
              "verification_helper_sha256": SUMMARY.sha256(_HELPER_PATH),
              "extractor_sha256": SUMMARY.sha256(__file__),
              "generator_sha256": plan["generator_sha256"],
              "calibrator_sha256": plan["calibrator_sha256"]}
    out.mkdir(parents=True, exist_ok=False)
    caches = {}
    for stream, values in sorted_streams.items():
        path = out / (stream + "_sorted.npy")
        with path.open("xb") as handle:
            np.save(handle, values, allow_pickle=False)
        caches[stream] = {"path": str(path), "sha256": SUMMARY.sha256(path),
                          "draws": int(values.size), "bytes": path.stat().st_size,
                          "dtype": values.dtype.str, "minimum": float(values[0]),
                          "maximum": float(values[-1]), "sort": "ascending independent copy"}
    extracted = {"format": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
                 "m": m, "stage": stage, "npar": plan["config"]["npar"],
                 "probabilities": probabilities, "quantiles": quantiles,
                 "primary_fit": result["primary_fit"],
                 "original_gpd_status": record["status"],
                 "original_validation_point_confidence": original_confidence,
                 "raw_provenance": raw_provenance, "source": source,
                 "sorted_cache": caches, "exceedance_rule": "APMI >= cutoff",
                 "tie_policy": "exact counts; no randomization",
                 "scope": "exploratory reuse; no new draws, refits, or runtime models"}
    SUMMARY.write_json(out / "extraction.json", extracted)
    return extracted
