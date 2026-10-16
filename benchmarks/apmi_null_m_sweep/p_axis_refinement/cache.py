"""Verify and reuse frozen sorted streams without generation or re-sorting.

The public entry point is deliberately fixed to the existing 10M+10M study.
No function in this module writes a file or modifies an input array.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import math
from pathlib import Path, PurePosixPath
import re
import time

import numpy as np


_EXTRACT_PATH = Path(__file__).resolve().parents[1] / "smooth_feasibility" / "extract.py"
_SPEC = importlib.util.spec_from_file_location("apmi_p_refinement_frozen_extract", _EXTRACT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load frozen sorted-stream helpers")
EXTRACT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(EXTRACT)
SUMMARY = EXTRACT.SUMMARY
RUNS_ROOT = EXTRACT.RUNS_ROOT
SCHEMA = "sjaracne-apmi-p-axis-cache-verification-v1"
DRAW_COUNT = 10_000_000


def _safe_existing(path, runs_root):
    """Reject traversal/symlinks before resolving any existing input."""
    requested = Path(path)
    if not requested.is_absolute() or ".." in requested.parts:
        raise ValueError("input path must be absolute without traversal")
    for candidate in (requested, *requested.parents):
        if candidate.is_symlink():
            raise ValueError("symlink in input path")
    resolved = requested.resolve(strict=True)
    root = Path(runs_root).resolve(strict=True)
    if resolved == root or root not in resolved.parents:
        raise ValueError("input must remain inside repository ignored runs/")
    return resolved


def _hash_checked(path, expected):
    if not isinstance(expected, str) or re.fullmatch("[0-9a-f]{64}", expected) is None:
        raise ValueError("invalid recorded SHA256")
    actual = SUMMARY.sha256(path)
    if actual != expected:
        raise ValueError("SHA256 mismatch: " + str(path))
    return actual


def _positive_integer(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(name + " must be a positive integer")
    return int(value)


def _verified_sorted(path, record, m, expected_draws, chunk_size=1_000_000):
    """Memory-map and scan bounded chunks, retaining no extra large array."""
    expected_draws = _positive_integer(expected_draws, "expected_draws")
    chunk_size = _positive_integer(chunk_size, "chunk_size")
    if (record.get("draws") != expected_draws or record.get("dtype") != "<f8" or
            record.get("sort") != "ascending independent copy" or
            record.get("bytes") != path.stat().st_size):
        raise ValueError("sorted-cache metadata mismatch")
    _hash_checked(path, record.get("sha256"))
    values = np.load(path, mmap_mode="r", allow_pickle=False)
    try:
        if (values.ndim != 1 or values.shape != (expected_draws,) or
                values.dtype.str != "<f8" or values.flags.writeable):
            raise ValueError("sorted cache must be read-only, one-dimensional little-endian float64")
        # Standard .npy payload must exactly occupy the declared file: no trailing bytes.
        if values.offset + expected_draws * 8 != path.stat().st_size:
            raise ValueError("sorted-cache byte length mismatch")
        tolerance = 64 * np.finfo(np.float64).eps
        previous = -math.inf
        for start in range(0, expected_draws, chunk_size):
            chunk = values[start:start + chunk_size]
            if (not np.all(np.isfinite(chunk)) or np.any(chunk < -tolerance) or
                    np.any(chunk > math.log(m) + tolerance)):
                raise ValueError("sorted-cache values outside finite AP-MI support")
            if chunk[0] < previous or np.any(chunk[1:] < chunk[:-1]):
                raise ValueError("sorted cache is not ascending")
            previous = float(chunk[-1])
        if record.get("minimum") != float(values[0]) or record.get("maximum") != float(values[-1]):
            raise ValueError("sorted-cache extrema mismatch")
        return values
    except Exception:
        values._mmap.close()
        raise


def _verify_cache_one(source_extraction, probabilities, *, expected_draws, runs_root):
    """Private small-fixture hook; production callers use verify_cache_one."""
    started = time.perf_counter()
    expected_draws = _positive_integer(expected_draws, "expected_draws")
    probabilities = EXTRACT.probabilities_checked(probabilities)
    source_extraction = deepcopy(source_extraction)
    m = _positive_integer(source_extraction.get("m"), "m")
    stage = SUMMARY.stage_for_m(m)
    if (source_extraction.get("format") != EXTRACT.SCHEMA or
            source_extraction.get("stage") != stage or source_extraction.get("npar") != 40 or
            source_extraction.get("original_gpd_status") not in {"accepted", "rejected"} or
            source_extraction.get("exceedance_rule") != "APMI >= cutoff"):
        raise ValueError("source extraction does not match the frozen study")
    source = source_extraction["source"]
    for path, key in ((_EXTRACT_PATH, "extractor_sha256"),
                      (EXTRACT._HELPER_PATH, "verification_helper_sha256")):
        if key in source:
            _hash_checked(path, source[key])
    run = _safe_existing(source["run"], runs_root)
    relative = PurePosixPath(source["attempt"])
    expected_attempt = "jobs/m%05d/attempt_0001" % m
    if relative.as_posix() != expected_attempt:
        raise ValueError("expected exactly the original attempt_0001 for m")
    attempt = _safe_existing(run / Path(*relative.parts), runs_root)
    if sorted(attempt.parent.glob("attempt_*")) != [attempt]:
        raise ValueError("expected exactly one original attempt, not a retry")
    verified = {}
    for name, key in (("plan.json", "plan_sha256"),
                      (source["attempt"] + "/result.json", "result_sha256"),
                      (source["attempt"] + "/calibration/calibration_report.json", "report_sha256")):
        path = _safe_existing(run / name, runs_root)
        verified[name] = _hash_checked(path, source[key])
    plan = SUMMARY.read_json(run / "plan.json")
    expected_config = dict(SUMMARY.EXPECTED_CONFIG,
                           fit_draws=expected_draws, validation_draws=expected_draws)
    if (plan.get("format") != SUMMARY.PLAN_SCHEMA or plan.get("stages") != SUMMARY.STAGES or
            plan.get("m") != SUMMARY.GRID or plan.get("config") != expected_config or
            plan.get("stability_quantiles") != [0.9925, 0.995, 0.9975]):
        raise ValueError("source plan does not match the frozen design")
    if any(source.get(key) != plan.get(key) for key in ("generator_sha256", "calibrator_sha256")):
        raise ValueError("source generator/calibrator identity mismatch")
    record = SUMMARY.read_json(attempt / "result.json")
    report = SUMMARY.read_json(attempt / "calibration" / "calibration_report.json")
    results = report.get("results", [])
    if (record.get("m") != m or record.get("status") != source_extraction["original_gpd_status"] or
            len(results) != 1 or results[0].get("m") != m):
        raise ValueError("original result/status/m mismatch")
    original = results[0]
    if source_extraction.get("primary_fit") is not None and source_extraction["primary_fit"] != original.get("primary_fit"):
        raise ValueError("source primary_fit differs from original report")
    arrays = {}
    try:
        for role in ("fit", "validation"):
            provenance = source_extraction["raw_provenance"][role]
            raw = _safe_existing(attempt / "calibration" / "raw" /
                                 ("m%05d_npar040_%s.f64" % (m, role)), runs_root)
            raw_relative = raw.relative_to(attempt).as_posix()
            digest = _hash_checked(raw, provenance["sha256"])
            if (digest != original["model"][role + "_values_sha256"] or
                    digest != source["artifact_sha256"].get(raw_relative) or
                    digest != record["artifacts_sha256"].get(raw_relative) or
                    raw.stat().st_size != expected_draws * 8 or
                    provenance.get("draws") != expected_draws or provenance.get("bytes") != expected_draws * 8):
                raise ValueError("raw-stream hash/length/provenance mismatch")
            metadata = {}
            for suffix in (".meta", ".provenance.json"):
                sidecar = _safe_existing(str(raw) + suffix, runs_root)
                digest_sidecar = _hash_checked(sidecar, source["artifact_sha256"].get(raw_relative + suffix))
                if digest_sidecar != record["artifacts_sha256"].get(raw_relative + suffix):
                    raise ValueError("raw sidecar differs from original result")
                verified[sidecar.relative_to(run).as_posix()] = digest_sidecar
            for line in Path(str(raw) + ".meta").read_text(encoding="utf-8").splitlines():
                if line.strip():
                    key, value = line.split("=", 1)
                    if key in metadata:
                        raise ValueError("duplicate raw metadata key")
                    metadata[key] = value
            seed = expected_config[role + "_seed"] + m + (1_000_000_000 if role == "validation" else 0)
            expected_metadata = {"format": "sjaracne-apmi-null-binary-v1", "kernel_schema": "sjaracne-apmi-v1",
                "estimator": "sjaracne-adaptive-partitioning", "rng": "mt19937-rejection-fisher-yates-v1",
                "m": str(m), "draws": str(expected_draws), "npar_limit": "40", "seed": str(seed),
                "dtype": "float64", "byte_order": "little", "record_bytes": "8"}
            raw_generator = SUMMARY.read_json(Path(str(raw) + ".provenance.json"))
            if (metadata != provenance.get("metadata") or provenance.get("seed") != seed or
                    any(metadata.get(k) != v for k, v in expected_metadata.items()) or
                    raw_generator.get("format") != "sjaracne-apmi-null-raw-provenance-v1" or
                    raw_generator.get("generator_sha256") != plan["generator_sha256"]):
                raise ValueError("raw metadata/generator provenance mismatch")
            verified[raw.relative_to(run).as_posix()] = digest
            cache_record = source_extraction["sorted_cache"][role]
            cache_path = _safe_existing(cache_record["path"], runs_root)
            if cache_path.name != role + "_sorted.npy" or cache_path.parent.name != "m%05d" % m:
                raise ValueError("sorted cache path does not identify its m and role")
            arrays[role] = _verified_sorted(cache_path, cache_record, m, expected_draws)
        if (source_extraction["raw_provenance"]["fit"]["sha256"] ==
                source_extraction["raw_provenance"]["validation"]["sha256"]):
            raise ValueError("fit and validation raw streams must differ")
        quantiles = []
        for p in probabilities:
            cutoff = EXTRACT.higher_quantile_sorted(arrays["fit"], p)
            counts = EXTRACT.count_sorted(arrays["fit"], cutoff)
            quantiles.append({"nominal_p": p, "cutoff": cutoff, "fit_ge": counts["ge"],
                              "fit_gt": counts["gt"], "fit_ties": counts["ties"],
                              "fit_draws": expected_draws, "method": "fit-only empirical higher quantile"})
        return {"format": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
                "m": m, "stage": stage, "npar": 40, "probabilities": probabilities,
                "quantiles": quantiles, "primary_fit": source_extraction.get("primary_fit"),
                "original_gpd_status": source_extraction["original_gpd_status"],
                "raw_provenance": source_extraction["raw_provenance"], "source": source,
                "original_source_input_hashes": verified,
                "sorted_cache": source_extraction["sorted_cache"], "exceedance_rule": "APMI >= cutoff",
                "tie_policy": "exact counts; no randomization",
                "scope": "exploratory reuse; no new draws, sorting, or runtime models",
                "elapsed_seconds": time.perf_counter() - started}
    finally:
        for values in arrays.values():
            values._mmap.close()


def verify_cache_one(source_extraction, probabilities):
    """Return fit-only dense quantiles after verifying both existing 10M caches.

    Original raw streams and all referenced hashes are checked read-only. The
    validation cache is verified but its quantiles/counts never become fit data.
    """
    return _verify_cache_one(source_extraction, probabilities,
                             expected_draws=DRAW_COUNT, runs_root=RUNS_ROOT)
