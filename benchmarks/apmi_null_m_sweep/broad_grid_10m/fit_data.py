"""Phase-scoped, integrity-checked access to the frozen broad-grid raw draws.

No statistics are computed at import time. Generation artifacts are never
modified. This module writes only fresh analysis caches beneath ignored runs/.
The analysis controller owns worker concurrency and creates the phase locks.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import sys

import numpy as np

try:
    from . import generate
except ImportError:
    import generate


SCHEMA = "sjaracne-broad-grid-fit-cache-v1"
GATE_SCHEMA = "sjaracne-broad-grid-analysis-access-v1"
N_DRAWS = 10_000_000
N_CONSTRUCTION = 8_000_000


def m_group(m):
    if isinstance(m, bool) or not isinstance(m, int) or m not in generate.GRID:
        raise ValueError("m must be one of the frozen 200 grid sizes")
    return ("final_interpolation_test" if m % 500 == 350 else
            "development" if m % 500 == 450 else "training")


def _reject_links(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("symlink/junction paths are not allowed: " + str(parent))


def _new_output(out, generation_root):
    out = Path(out).absolute()
    _reject_links(out)
    boundary = (generate.repo_root() / "runs").resolve(strict=True)
    resolved = out.resolve()
    generation_root = Path(generation_root).resolve(strict=True)
    if (out.exists() or resolved == boundary or not resolved.is_relative_to(boundary)
            or resolved == generation_root or resolved.is_relative_to(generation_root)):
        raise ValueError("cache must be a fresh child of ignored runs/, outside generation output")
    out.mkdir(parents=True, exist_ok=False)
    return out


def _find_task(plan, m, stream):
    m_group(m)
    if stream not in {"fit", "validation"}:
        raise ValueError("stream must be fit or validation")
    matches = [task for task in plan["tasks"] if task["m"] == m and task["stream"] == stream]
    if len(matches) != 1 or matches[0]["draws"] != N_DRAWS:
        raise ValueError("missing, duplicate or unexpected draw count for frozen task")
    return matches[0]


def _identity(plan_path, m, stream):
    _reject_links(plan_path)
    plan, digest = generate.load_plan(plan_path)
    task = _find_task(plan, m, stream)
    directory = Path(plan["output_dir"]) / "streams" / task["id"]
    _reject_links(directory)
    result = generate.verify_complete(plan, digest, task, directory)
    identity = {
        "plan_sha256": digest,
        "task": dict(task),
        "raw": dict(result["artifacts"]["null.f64"]),
        "metadata": dict(result["artifacts"]["null.f64.meta"]),
        "checkpoint": generate.record(directory / "complete.json"),
        "generator_sha256": plan["pins"]["generator"]["sha256"],
        "engine_commit": plan["engine_commit"],
    }
    return plan, identity


def verify_stream(plan_path, m, stream):
    """Return integrity/provenance only; no quantiles or tail counts."""
    return _identity(plan_path, m, stream)[1]


def _check_record(record):
    if not isinstance(record, dict) or set(record) != {"path", "bytes", "sha256"}:
        raise ValueError("phase-lock artifacts require path, bytes and SHA256")
    _reject_links(record["path"])
    if generate.record(record["path"]) != record:
        raise ValueError("phase-lock pinned artifact changed")


def _authorize(gate_manifest, stage, plan_hash):
    """Read a hash-locked access declaration and recheck all its pinned files.

    A gate is an immutable JSON file with a sibling .sha256 digest. Controller
    gates use this module's GATE_SCHEMA, stage, plan_sha256 and nonempty pins.
    The frozen gate additionally pins primary_model and selection_lock and
    declares primary_eligible=true and no_fallback=true. Boolean declarations
    supplement rather than replace the model/selection file hashes.
    """
    gate_manifest = Path(gate_manifest)
    _reject_links(gate_manifest)
    sidecar = gate_manifest.with_suffix(".sha256")
    if sidecar.read_text(encoding="ascii").strip() != generate.sha256(gate_manifest):
        raise ValueError("phase-lock SHA256 mismatch")
    gate = generate.read_json(gate_manifest)
    if (gate.get("format") != GATE_SCHEMA or gate.get("stage") != stage
            or gate.get("plan_sha256") != plan_hash):
        raise ValueError("phase-lock identity or stage mismatch")
    pins = gate.get("pins")
    if not isinstance(pins, dict) or not pins:
        raise ValueError("phase-lock must pin analysis code and protocol")
    for pin in pins.values():
        _check_record(pin)
    selection = None
    if stage in {"selected", "frozen"}:
        _check_record(gate.get("selection_lock"))
        selection = generate.read_json(gate["selection_lock"]["path"])
        if (selection.get("format") != "apmi-two-surface-selection-v1"
                or selection.get("stage") != "selected"
                or selection.get("plan_sha256") != plan_hash
                or selection.get("selected_model") not in {"quadratic", "pchip"}
                or selection.get("eligible") is not True
                or selection.get("no_fallback") is not True
                or not isinstance(selection.get("analysis_plan_sha256"), str)
                or len(selection["analysis_plan_sha256"]) != 64):
            raise ValueError("invalid selected-candidate lock")
        if ("analysis_plan_sha256" in gate
                and gate["analysis_plan_sha256"] != selection["analysis_plan_sha256"]):
            raise ValueError("selection belongs to another prospective analysis plan")
    if stage == "frozen":
        if gate.get("primary_eligible") is not True or gate.get("no_fallback") is not True:
            raise ValueError("final opening requires one eligible primary and no fallback")
        _check_record(gate.get("primary_model"))
        primary = generate.read_json(gate["primary_model"]["path"])
        expected_m = [m for m in generate.GRID if m_group(m) != "final_interpolation_test"]
        if (primary.get("format") != "apmi-two-surface-frozen-primary-v1"
                or primary.get("generation_plan_sha256") != plan_hash
                or primary.get("selected_model") != selection["selected_model"]
                or primary.get("selection_sha256") != gate["selection_lock"]["sha256"]
                or primary.get("training_m") != expected_m
                or not isinstance(primary.get("surface"), dict)
                or not isinstance(primary["surface"].get("fit_models"), dict)
                or not primary["surface"]["fit_models"]):
            raise ValueError("invalid frozen primary, selection consistency or 180-size refit")
        if "selected_model" in gate and gate["selected_model"] != selection["selected_model"]:
            raise ValueError("frozen access wrapper model disagrees with selection")
    return gate


def _preflight(plan_path, m, stream, group, stage, gate_manifest):
    """Authorize roles before integrity loading, and hence before raw access."""
    actual_group = m_group(m)
    if actual_group not in group:
        raise ValueError("requested m group is sealed for this extraction")
    # Reading the frozen plan is not statistical access. Do not call the
    # stream verifier until group, phase, code pins and role have been checked.
    _reject_links(plan_path)
    plan, digest = generate.load_plan(plan_path)
    _find_task(plan, m, stream)
    gate = _authorize(gate_manifest, stage, digest)
    verified_plan, identity = _identity(plan_path, m, stream)
    if verified_plan != plan:
        raise ValueError("generation plan changed during authorization")
    return plan, identity, generate.record(gate_manifest), gate


def _read_verified(identity, expected=None):
    expected = N_DRAWS if expected is None else expected
    raw_path = Path(identity["raw"]["path"])
    _reject_links(raw_path)
    values = np.fromfile(raw_path, dtype="<f8")
    if values.ndim != 1 or values.size != expected or values.nbytes != identity["raw"]["bytes"]:
        raise ValueError("raw draw count changed after verification")
    # Hash exactly the bytes used statistically, closing the verification/read
    # race without mutating the source file or creating another raw file.
    digest = hashlib.sha256(memoryview(values).cast("B")).hexdigest()
    if digest != identity["raw"]["sha256"]:
        raise ValueError("statistical bytes differ from completed generation checkpoint")
    values.flags.writeable = False
    return values


def _p_knots(pknots):
    values = np.asarray(pknots, dtype=np.float64)
    if (values.ndim != 1 or not len(values) or not np.all(np.isfinite(values))
            or np.any(values <= 0) or np.any(values >= 1)
            or len(set(map(float, values))) != len(values)):
        raise ValueError("unique finite probabilities strictly between zero and one required")
    return values


def _quantiles(values, pknots):
    p = _p_knots(pknots)
    cutoffs = np.quantile(values, 1.0 - p, method="higher")
    return [{"p": float(probability), "cutoff": float(cutoff), "cutoff_hex": float(cutoff).hex()}
            for probability, cutoff in zip(p, cutoffs)]


def _save_npy(path, values):
    with Path(path).open("xb") as handle:
        np.save(handle, values, allow_pickle=False)
    return generate.record(path)


def sorted_summary(values):
    """Check one cache once; repeated tail counts can then use searchsorted."""
    values = np.asarray(values)
    if (values.ndim != 1 or not len(values) or values.dtype != np.dtype("float64")
            or not np.all(np.isfinite(values)) or np.any(values[1:] < values[:-1])):
        raise ValueError("nonempty finite ascending binary64 array required")
    return {"draws": int(values.size), "zero_count": int(np.count_nonzero(values == 0)),
            "unique_count": int(1 + np.count_nonzero(values[1:] != values[:-1])),
            "minimum": float(values[0]), "maximum": float(values[-1])}


def count_sorted(values, threshold):
    """Exact engine >=, strict >, ties and neighboring-binary64 diagnostics.

    The input is a sorted, already verified cache. This deliberately does not
    round cutoffs, clip them, randomize ties or choose a favorable neighbor.
    """
    if isinstance(threshold, bool):
        raise ValueError("finite binary64 threshold required")
    threshold = float(threshold)
    if not math.isfinite(threshold):
        raise ValueError("finite binary64 threshold required")
    values = np.asarray(values)
    if values.ndim != 1 or values.dtype != np.dtype("float64"):
        raise ValueError("binary64 one-dimensional sorted cache required")
    left = int(np.searchsorted(values, threshold, side="left"))
    right = int(np.searchsorted(values, threshold, side="right"))
    lower = float(np.nextafter(threshold, -np.inf))
    upper = float(np.nextafter(threshold, np.inf))
    n = int(values.size)
    return {"draws": n, "ge": n - left, "gt": n - right, "ties": right - left,
            "minus_ulp_ge": n - int(np.searchsorted(values, lower, side="left")),
            "plus_ulp_ge": n - int(np.searchsorted(values, upper, side="left")),
            "threshold": threshold, "threshold_hex": threshold.hex()}


def _write_cache(out, identity, gate_record, purpose, arrays, quantiles=None):
    result = {"format": SCHEMA, "purpose": purpose, "source": identity,
              "phase_lock": gate_record, "arrays": {}, "quantiles": quantiles or []}
    for name, (values, sorted_flag) in arrays.items():
        artifact = _save_npy(out / (name + ".npy"), values)
        item = {"artifact": artifact, "draws": int(values.size), "sorted": sorted_flag,
                "dtype": "float64"}
        if sorted_flag:
            item["summary"] = sorted_summary(values)
        result["arrays"][name] = item
    generate.write_new(out / "cache.json", result)
    return result


def extract_training(plan_path, m, out, pknots, gate_manifest):
    """First-8M quantiles plus independently sorted last-2M scoring cache."""
    plan, identity, gate, _ = _preflight(plan_path, m, "fit", {"training"},
                                         "analysis_frozen", gate_manifest)
    pknots = _p_knots(pknots)
    out = _new_output(out, plan["output_dir"])
    values = _read_verified(identity)
    construction, internal = values[:N_CONSTRUCTION], np.sort(values[N_CONSTRUCTION:])
    return _write_cache(out, identity, gate, "initial_training_first8M_last2M",
                        {"internal": (internal, True)},
                        _quantiles(construction, pknots))


def extract_development(plan_path, m, out, gate_manifest):
    """Development fitting stream is score-only until candidate selection."""
    plan, identity, gate, _ = _preflight(plan_path, m, "fit", {"development"},
                                         "analysis_frozen", gate_manifest)
    out = _new_output(out, plan["output_dir"])
    values = np.sort(_read_verified(identity))
    return _write_cache(out, identity, gate, "development_score_only", {"score": (values, True)})


def extract_refit(plan_path, m, out, pknots, gate_manifest):
    """One selected procedure may refit only the 180 non-test fitting streams."""
    plan, identity, gate, _ = _preflight(plan_path, m, "fit", {"training", "development"},
                                         "selected", gate_manifest)
    pknots = _p_knots(pknots)
    out = _new_output(out, plan["output_dir"])
    values = _read_verified(identity)
    return _write_cache(out, identity, gate, "selected_procedure_full10M_refit",
                        {}, _quantiles(values, pknots))


def extract_final_validation(plan_path, m, out, gate_manifest):
    """Final validation opens only after one eligible model is hash-frozen."""
    plan, identity, gate, _ = _preflight(plan_path, m, "validation",
                                         {"training", "development", "final_interpolation_test"},
                                         "frozen", gate_manifest)
    out = _new_output(out, plan["output_dir"])
    values = np.sort(_read_verified(identity))
    return _write_cache(out, identity, gate, "final_validation_score_only", {"score": (values, True)})


def extract_final_test_fit(plan_path, m, out, pknots, gate_manifest):
    """Exact-m final-test baselines are diagnostic only, after the same gate."""
    plan, identity, gate, _ = _preflight(plan_path, m, "fit", {"final_interpolation_test"},
                                         "frozen", gate_manifest)
    pknots = _p_knots(pknots)
    out = _new_output(out, plan["output_dir"])
    values = _read_verified(identity)
    return _write_cache(out, identity, gate, "final_test_fit_diagnostic_only", {},
                        _quantiles(values, pknots))


def load_array(cache, name, mmap_mode="r"):
    """Verify a materialized cache and return a read-only array."""
    if isinstance(cache, (str, Path)):
        cache = generate.read_json(cache)
    if cache.get("format") != SCHEMA:
        raise ValueError("unexpected fit cache schema")
    item = cache["arrays"][name]
    artifact = item["artifact"]
    _check_record(artifact)
    if mmap_mode != "r":
        raise ValueError("caches may only be opened read-only")
    values = np.load(artifact["path"], allow_pickle=False, mmap_mode="r")
    if values.ndim != 1 or values.dtype != np.dtype("float64") or len(values) != item["draws"]:
        raise ValueError("cache dtype, shape or draw count mismatch")
    m = cache["source"]["task"]["m"]
    tolerance = 64 * sys.float_info.epsilon
    if np.any(~np.isfinite(values)) or np.any(values < -tolerance) or np.any(values > math.log(m) + tolerance):
        raise ValueError("cache outside AP-MI support")
    if item["sorted"] and sorted_summary(values) != item["summary"]:
        raise ValueError("sorted cache summary changed")
    values.flags.writeable = False
    return values
