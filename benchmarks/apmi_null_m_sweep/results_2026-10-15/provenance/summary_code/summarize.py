#!/usr/bin/env python3
"""Package a frozen exact-m sweep without changing or refitting its evidence.

Run only after the authorized science stage: python summarize.py --run RUN --out NEW
The output directory must not exist. Raw streams stay local and are never copied.
Empirical thresholds use fitting draws only; their held-out checks are diagnostic,
never a way to replace a rejected GPD, select a threshold, or alter acceptance.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import sys

import numpy as np
from scipy.stats import beta


SCHEMA = "sjaracne-exact-m-moderate-tail-summary-v1"
GRID = [30, 50, 80, 90, 100, 150, 300, 1000, 644, 516, 725]
PROBABILITIES = (1e-3, 5e-4)
EXPECTED_CONFIG = {
    "npar": 40, "fit_draws": 5_000_000, "validation_draws": 5_000_000,
    "fit_seed": 20261015, "validation_seed": 20261016,
    "tail_quantile": 0.995, "min_tail_count": 20_000,
    "p_min": 5e-4, "p_max": 1e-3, "default_p": 5e-4,
    "validation_p": [1e-3, 5e-4], "stability_relative_tolerance": 0.10,
    "min_stability_fits": 3, "validation_family_confidence": 0.99,
    "validation_family_comparisons": 10,
}
LIMITS = (
    "Synthetic independent uniform rank-permutation nulls only; Npar=40 and unique ordinal ranks. "
    "Exact m only: no interpolation or nearest-neighbor lookup. Acceptance does not establish "
    "biological accuracy, biological FDR, or an optimal network setting. Confidence is the "
    "predeclared 99% family setting per model with ten comparisons (99.9% per point), not "
    "simultaneous 99% coverage across all m. Empirical thresholds are fit-stream diagnostics "
    "evaluated on held-out draws, not replacement runtime models or a model-selection rule."
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: " + str(path))
    return value


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def same_number(left, right):
    return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-14)


def cutoff(fit, probability):
    """Evaluate recorded GPD parameters; perform no fitting or optimization."""
    u, pu = float(fit["threshold"]), float(fit["tail_probability"])
    shape, scale = float(fit["shape"]), float(fit["scale"])
    if not all(math.isfinite(x) for x in (u, pu, shape, scale)):
        raise ValueError("non-finite recorded GPD parameter")
    if not 0 < probability <= pu <= 1 or scale <= 0:
        raise ValueError("probability outside recorded GPD tail, or invalid scale")
    value = (u + scale * math.log(pu / probability) if abs(shape) < 1e-10 else
             u + scale / shape * ((probability / pu) ** (-shape) - 1))
    if fit.get("endpoint") is not None:
        value = min(value, float(fit["endpoint"]))
    if not math.isfinite(value):
        raise ValueError("non-finite GPD cutoff")
    return value


def interval(count, draws, confidence):
    alpha = 1 - confidence
    return (0.0 if count == 0 else float(beta.ppf(alpha / 2, count, draws - count + 1)),
            1.0 if count == draws else float(beta.ppf(1 - alpha / 2, count + 1, draws - count)))


def heldout(values, threshold, probability, confidence):
    count, draws = int(np.count_nonzero(values >= threshold)), int(values.size)
    low, high = interval(count, draws, confidence)
    return {"nominal_p": probability, "cutoff": threshold, "exceedances": count,
            "draws": draws, "observed_p": count / draws,
            "ratio_observed_to_nominal": count / draws / probability,
            "interval_lower": low, "interval_upper": high,
            "interval_confidence": confidence, "nominal_in_interval": low <= probability <= high,
            "exceedance_rule": "APMI >= cutoff"}


def higher_quantile(values, probability):
    try:
        return float(np.quantile(values, 1 - probability, method="higher"))
    except TypeError:
        return float(np.quantile(values, 1 - probability, interpolation="higher"))


def load_plan(run):
    path = run / "plan.json"
    if sha256(path) != (run / "plan.sha256").read_text(encoding="ascii").strip():
        raise ValueError("frozen plan hash mismatch")
    plan = read_json(path)
    if (plan.get("format") != "sjaracne-staged-apmi-calibration-v1" or
            plan.get("m") != GRID or plan.get("config") != EXPECTED_CONFIG or
            plan.get("stability_quantiles") != [0.9925, 0.995, 0.9975]):
        raise ValueError("not the predeclared moderate-probability eleven-m sweep")
    return plan


def verify_attempt(attempt, record):
    actual = {}
    for path in sorted(attempt.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink in attempt evidence")
        if path.is_file() and path.name != "result.json":
            actual[path.relative_to(attempt).as_posix()] = sha256(path)
    declared = record.get("artifacts_sha256")
    if not isinstance(declared, dict) or actual != declared:
        raise ValueError("attempt artifact hashes do not match result.json")
    for name in declared:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name:
            raise ValueError("unsafe artifact path in result.json")
    return actual


def raw_values(attempt, plan, m, stream, expected_hash=None):
    config = plan["config"]
    path = attempt / "calibration" / "raw" / ("m%05d_npar%03d_%s.f64" % (m, config["npar"], stream))
    metadata = {}
    for line in Path(str(path) + ".meta").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, value = line.split("=", 1)
        if key in metadata:
            raise ValueError("duplicate raw metadata key")
        metadata[key] = value
    seed = config[stream + "_seed"] + m + (1_000_000_000 if stream == "validation" else 0)
    expected = {"format": "sjaracne-apmi-null-binary-v1", "kernel_schema": "sjaracne-apmi-v1",
                "m": str(m), "npar_limit": str(config["npar"]), "draws": str(config[stream + "_draws"]),
                "seed": str(seed), "dtype": "float64", "byte_order": "little", "record_bytes": "8",
                "estimator": "sjaracne-adaptive-partitioning", "rng": "mt19937-rejection-fisher-yates-v1"}
    if any(metadata.get(k) != v for k, v in expected.items()):
        raise ValueError("raw metadata does not match frozen design for " + stream)
    provenance = read_json(Path(str(path) + ".provenance.json"))
    if (provenance.get("format") != "sjaracne-apmi-null-raw-provenance-v1" or
            provenance.get("generator_sha256") != plan["generator_sha256"]):
        raise ValueError("raw generator provenance mismatch")
    digest = sha256(path)
    if expected_hash is not None and digest != expected_hash:
        raise ValueError("raw hash does not match calibration report")
    if path.stat().st_size != config[stream + "_draws"] * 8:
        raise ValueError("raw byte length mismatch")
    values = np.fromfile(path, dtype="<f8")
    tolerance = 64 * np.finfo(np.float64).eps
    if not np.all(np.isfinite(values)) or np.any(values < -tolerance) or np.any(values > math.log(m) + tolerance):
        raise ValueError("raw values outside finite AP-MI support")
    return values, {"sha256": digest, "draws": int(values.size), "seed": seed,
                    "bytes": path.stat().st_size, "metadata": metadata}


def inspect_report(attempt, plan, m, record):
    report = read_json(attempt / "calibration" / "calibration_report.json")
    results = report.get("results", [])
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict) or results[0].get("m") != m:
        raise ValueError("engine report must contain exactly this m")
    result, config = results[0], plan["config"]
    model = result["model"]
    if not isinstance(model, dict) or not isinstance(result.get("primary_fit"), dict):
        raise ValueError("invalid model/primary-fit JSON container")
    for key in ("stability_fits", "validation"):
        if not isinstance(result.get(key), list) or any(not isinstance(item, dict) for item in result[key]):
            raise ValueError("invalid " + key + " JSON container")
    expected = {"m": m, "npar_limit": config["npar"], "fit_draws": config["fit_draws"],
                "validation_draws": config["validation_draws"], "fit_seed": config["fit_seed"] + m,
                "validation_seed": config["validation_seed"] + 1_000_000_000 + m,
                "generator_sha256": plan["generator_sha256"], "calibrator_sha256": plan["calibrator_sha256"],
                "default_p": config["default_p"], "supported_p_min": config["p_min"],
                "supported_p_max": config["p_max"], "kernel_schema": "sjaracne-apmi-v1"}
    if any(model.get(k) != v for k, v in expected.items()):
        raise ValueError("engine model metadata does not match frozen design")
    confidence = 1 - (1 - config["validation_family_confidence"]) / config["validation_family_comparisons"]
    if (result.get("validation_family_comparisons") != config["validation_family_comparisons"] or
            not same_number(result["validation_family_confidence"], config["validation_family_confidence"]) or
            not same_number(result["validation_point_confidence"], confidence) or
            not same_number(result["stability_probability"], config["default_p"])):
        raise ValueError("engine confidence/stability design mismatch")
    primary = result["primary_fit"]
    if (primary["tail_count"] < config["min_tail_count"] or
            not same_number(primary["threshold_quantile"], config["tail_quantile"])):
        raise ValueError("primary tail fails frozen threshold/count requirement")
    quantiles = [f["threshold_quantile"] for f in result["stability_fits"]]
    if len(set(quantiles)) != len(quantiles) or not set(quantiles).issubset({0.9925, 0.995, 0.9975}):
        raise ValueError("unplanned or duplicate stability threshold")
    primary_sensitivity = [f for f in result["stability_fits"] if f["threshold_quantile"] == config["tail_quantile"]]
    if len(primary_sensitivity) != 1:
        raise ValueError("primary threshold is absent from stability fits")
    for key in ("threshold", "tail_count", "tail_probability", "shape", "scale"):
        if not same_number(primary[key], primary_sensitivity[0][key]):
            raise ValueError("primary fit disagrees with its stability fit")
    if primary.get("endpoint") != primary_sensitivity[0].get("endpoint"):
        raise ValueError("primary endpoint disagrees with its stability fit")
    for model_key, fit_key in (("tail_shape", "shape"), ("tail_scale", "scale"),
                               ("tail_threshold", "threshold"), ("tail_probability", "tail_probability")):
        if not same_number(model[model_key], primary[fit_key]):
            raise ValueError("model and primary fit disagree")
    if not same_number(model["default_p_cutoff"], cutoff(primary, config["default_p"])):
        raise ValueError("model cutoff does not match actual default probability")
    if result["accepted"] is not (record["status"] == "accepted"):
        raise ValueError("runner status and scientific acceptance disagree")
    if record.get("returncode") != 0:
        raise ValueError("completed scientific result has nonzero process exit")
    models = list((attempt / "calibration").glob("*.model"))
    if len(models) != int(result["accepted"]):
        raise ValueError("accepted model count mismatch; rejected models must not be emitted")
    if (bool(result["accepted"]) != (bool(result["stability_pass"]) and bool(result["validation_pass"])) or
            model.get("calibration_status") != ("accepted" if result["accepted"] else "rejected")):
        raise ValueError("inconsistent scientific acceptance gates")
    if models:
        text_model = dict(line.split("=", 1) for line in models[0].read_text(encoding="utf-8").splitlines() if line and not line.startswith("#"))
        for key, value in model.items():
            if key not in text_model:
                raise ValueError("accepted model artifact is missing " + key)
            if value is None:
                equal = text_model[key] == "none"
            elif isinstance(value, (float, int)):
                equal = same_number(text_model[key], value)
            else:
                equal = text_model[key] == str(value)
            if not equal:
                raise ValueError("accepted model artifact disagrees with report: " + key)
    return result, confidence


def summarize_job(run, plan, m):
    row = {"m": m, "stage": "anchors" if m in GRID[:8] else "dream", "status": "not_started",
           "accepted": False, "gpd": [], "empirical_diagnostic": [], "warnings": []}
    attempts = sorted((run / "jobs" / ("m%05d" % m)).glob("attempt_*"))
    row["attempt_count"] = len(attempts)
    row["attempt_history"] = []
    for historical in attempts[:-1]:
        entry = {"attempt": historical.relative_to(run).as_posix(), "selected": False,
                 "role": "retained history only; not used for current scientific acceptance"}
        try:
            prior = read_json(historical / "result.json")
            entry.update(status=prior.get("status"), error=prior.get("error"),
                         result_sha256=sha256(historical / "result.json"))
        except (OSError, ValueError, TypeError) as error:
            entry.update(status="incomplete-or-unreadable", error=str(error))
        row["attempt_history"].append(entry)
    if not attempts:
        return row
    attempt = attempts[-1]
    row["attempt"] = attempt.relative_to(run).as_posix()
    if not (attempt / "result.json").is_file():
        row.update(status="incomplete", failure_kind="running-or-interrupted-attempt")
        return row
    try:
        record = read_json(attempt / "result.json")
        row["runner_status"] = record.get("status")
        row["job"] = record
        if record.get("m") != m or record.get("status") not in {"accepted", "rejected", "failed"}:
            raise ValueError("invalid runner result identity/status")
        verify_attempt(attempt, record)
        row.update(status=record["status"], accepted=record["status"] == "accepted")
        if record["status"] == "failed":
            row["failure_kind"] = record.get("failure_kind", "computational-or-model-fit-failure")
            row["error"] = record.get("error")
            if list((attempt / "calibration").glob("*.model")):
                raise ValueError("failed attempt emitted a runtime model")
            result = None
            confidence = 1 - (1 - plan["config"]["validation_family_confidence"]) / plan["config"]["validation_family_comparisons"]
        else:
            result, confidence = inspect_report(attempt, plan, m, record)
            row["primary_fit"] = result["primary_fit"]
            row["stability_pass"] = result["stability_pass"]
            row["validation_pass"] = result["validation_pass"]
            row["recorded_stability_relative_range_at_5e_4"] = result["relative_stability_range"]
            row["fit_summary"] = result.get("fit_summary")
        try:
            fit, fit_provenance = raw_values(attempt, plan, m, "fit", None if result is None else result["model"]["fit_values_sha256"])
            validation, validation_provenance = raw_values(attempt, plan, m, "validation", None if result is None else result["model"]["validation_values_sha256"])
        except (OSError, ValueError, KeyError) as error:
            if result is not None:
                raise
            row["warnings"].append("Empirical diagnostic unavailable: " + str(error))
            return row
        row["raw_provenance"] = {"fit": fit_provenance, "validation": validation_provenance}
        if fit_provenance["seed"] == validation_provenance["seed"]:
            raise ValueError("fit and validation streams are not distinct")
        if fit_provenance["sha256"] == validation_provenance["sha256"]:
            if np.all(fit == fit[0]):
                row["warnings"].append("Fit and validation have identical degenerate values despite distinct recorded seeds; empirical diagnostics retain ties and do not establish usable tail calibration.")
            else:
                raise ValueError("fit and validation streams are not distinct")
        if result is not None:
            for recorded_fit in [result["primary_fit"]] + result["stability_fits"]:
                threshold = higher_quantile(fit, 1 - recorded_fit["threshold_quantile"])
                count = int(np.count_nonzero(fit > threshold))
                pu = (count + 1) / (fit.size + 1)
                if (not same_number(recorded_fit["threshold"], threshold) or
                        recorded_fit["tail_count"] != count or
                        not same_number(recorded_fit["tail_probability"], pu)):
                    raise ValueError("recorded fit threshold/count/probability does not match fitting draws")
        for p in PROBABILITIES:
            empirical = heldout(validation, higher_quantile(fit, p), p, confidence)
            empirical.update(method="empirical-fit-higher-quantile", diagnostic_only=True,
                             fit_quantile=1-p, fit_quantile_rule="higher")
            row["empirical_diagnostic"].append(empirical)
            if result is None:
                continue
            diagnostic = heldout(validation, cutoff(result["primary_fit"], p), p, confidence)
            original = [v for v in result["validation"] if same_number(v["nominal_p"], p)]
            if (len(original) != 1 or original[0]["exceedances"] != diagnostic["exceedances"] or
                    original[0]["draws"] != diagnostic["draws"] or
                    not same_number(original[0]["cutoff"], diagnostic["cutoff"]) or
                    original[0]["nominal_in_interval"] != diagnostic["nominal_in_interval"]):
                raise ValueError("recorded held-out validation does not match raw draws")
            sensitivity = [{"threshold_quantile": f["threshold_quantile"], "cutoff": cutoff(f, p),
                            "tail_count": f["tail_count"]} for f in result["stability_fits"]]
            values = np.asarray([item["cutoff"] for item in sensitivity])
            relative = float(np.ptp(values) / np.median(values)) if values.size >= 2 and np.median(values) != 0 else None
            diagnostic.update(method="GPD", stability_fits=sensitivity,
                              stability_relative_range=relative,
                              stability_evaluation="acceptance gate" if p == plan["config"]["default_p"] else "diagnostic only")
            if p == plan["config"]["default_p"]:
                if ((relative is None) != (result["relative_stability_range"] is None) or
                        (relative is not None and not same_number(relative, result["relative_stability_range"]))):
                    raise ValueError("recorded stability range mismatch")
                valid_sensitivity = [f for f in result["stability_fits"] if
                                     f["tail_count"] >= max(100, plan["config"]["min_tail_count"] // 10)]
                gate = (len(valid_sensitivity) >= plan["config"]["min_stability_fits"] and
                        relative is not None and math.isfinite(relative) and
                        relative <= plan["config"]["stability_relative_tolerance"])
                if bool(result["stability_pass"]) != gate:
                    raise ValueError("recorded stability gate disagrees with derived range/counts")
            row["gpd"].append(diagnostic)
        if result is not None and bool(result["validation_pass"]) != all(d["nominal_in_interval"] for d in row["gpd"]):
            raise ValueError("recorded validation gate disagrees with independent counts")
        return row
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        row.update(status="failed", accepted=False, failure_kind="summary-provenance-validation-failure", error=str(error))
        row["gpd"], row["empirical_diagnostic"] = [], []
        row.pop("primary_fit", None)
        return row


def copy_compact_evidence(run, out, rows):
    """Whitelist compact evidence; raw binary payloads and rejected models never leave run/."""
    for name in ("plan.json", "plan.sha256", "environment.json"):
        if (run / name).is_file():
            shutil.copy2(run / name, out / name)
    code = out / "provenance" / "summary_code"
    code.mkdir(parents=True, exist_ok=True)
    for name in ("summarize.py", "test_summarize.py"):
        source = Path(__file__).with_name(name)
        if source.is_file():
            shutil.copy2(source, code / name)
    for path in sorted((run / "invocations").glob("*/*.json")):
        target = out / "provenance" / path.relative_to(run)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for row in rows:
        if "attempt" not in row:
            continue
        selected = run / row["attempt"]
        for attempt in sorted(selected.parent.glob("attempt_*")):
            for path in sorted(attempt.rglob("*")):
                if not path.is_file() or path.is_symlink() or path.suffix not in {".json", ".csv", ".log", ".txt", ".meta", ".model"}:
                    continue
                if path.suffix == ".model" and (not row["accepted"] or attempt != selected):
                    continue
                relative = path.relative_to(run)
                target = out / "evidence" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)


def write_tables(out, rows):
    summary_fields = ["m", "stage", "status", "accepted", "shape", "scale", "u", "p_u",
                      "cutoff_p_1e_3", "cutoff_p_5e_4", "stability_range_p_1e_3", "stability_range_p_5e_4",
                      "stability_pass", "validation_pass", "failure_kind", "error"]
    long_fields = ["m", "status", "method", "diagnostic_only", "nominal_p", "cutoff", "exceedances", "draws",
                   "observed_p", "ratio_observed_to_nominal", "interval_lower", "interval_upper",
                   "interval_confidence", "nominal_in_interval", "stability_relative_range"]
    with (out / "summary.csv").open("x", newline="", encoding="utf-8") as summary, (out / "heldout.csv").open("x", newline="", encoding="utf-8") as heldout_file:
        writer, long_writer = csv.DictWriter(summary, summary_fields), csv.DictWriter(heldout_file, long_fields, extrasaction="ignore")
        writer.writeheader()
        long_writer.writeheader()
        for row in rows:
            flat = {k: row[k] for k in summary_fields if k in row}
            primary = row.get("primary_fit", {})
            flat.update({name: primary.get(key) for name, key in (("shape", "shape"), ("scale", "scale"), ("u", "threshold"), ("p_u", "tail_probability"))})
            for diagnostic in row["gpd"]:
                suffix = "1e_3" if diagnostic["nominal_p"] == 1e-3 else "5e_4"
                flat["cutoff_p_" + suffix] = diagnostic["cutoff"]
                flat["stability_range_p_" + suffix] = diagnostic["stability_relative_range"]
            writer.writerow(flat)
            for diagnostic in row["gpd"] + row["empirical_diagnostic"]:
                long_writer.writerow({"m": row["m"], "status": row["status"], "diagnostic_only": diagnostic.get("diagnostic_only", False), **diagnostic})


def plot(out, rows):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "Plots unavailable: matplotlib is not installed."
    figure, axes = plt.subplots(2, 2, figsize=(12, 7), sharex="col")
    for column, p in enumerate(PROBABILITIES):
        for key, status, label, style in (("gpd", "accepted", "GPD accepted", "o"),
                                          ("gpd", "rejected", "GPD rejected (not runtime model)", "x"),
                                          ("empirical_diagnostic", None, "Empirical fit quantile (diagnostic)", "s")):
            points = sorted((r["m"], d) for r in rows for d in r[key]
                            if d["nominal_p"] == p and (status is None or r["status"] == status))
            if not points:
                continue
            x, diagnostics = zip(*points)
            axes[0, column].plot(x, [d["cutoff"] for d in diagnostics], style, label=label, markersize=4)
            ratios = [d["ratio_observed_to_nominal"] for d in diagnostics]
            errors = [[d["observed_p"] / p - d["interval_lower"] / p for d in diagnostics],
                      [d["interval_upper"] / p - d["observed_p"] / p for d in diagnostics]]
            axes[1, column].errorbar(x, ratios, yerr=errors, fmt=style, capsize=3, markersize=4, label=label)
        axes[0, column].set_title("Nominal p = %g" % p)
        axes[0, column].set_ylabel("AP-MI cutoff")
        axes[1, column].set_ylabel("Held-out actual / nominal")
        axes[1, column].set_xlabel("Exact observation count m (log scale)")
        axes[1, column].axhline(1, color="black", linewidth=0.7)
        for axis in axes[:, column]:
            axis.set_xscale("log")
            axis.grid(alpha=0.2)
            if axis.lines:
                axis.legend(fontsize=7)
    figure.suptitle("Synthetic exact-m null diagnostics; point intervals 99.9%; rejected GPDs are not runtime models", fontsize=10)
    figure.tight_layout()
    figure.savefig(out / "cutoffs_and_heldout.png", dpi=160)
    figure.savefig(out / "cutoffs_and_heldout.svg")
    plt.close(figure)
    return None


def summarize_run(run, out, make_plots=True):
    run, out = Path(run).resolve(strict=True), Path(out).resolve()
    if out.exists():
        raise ValueError("output must be a fresh nonexistent directory")
    if run == out or run in out.parents or out in run.parents:
        raise ValueError("output and raw run directories must not contain each other")
    plan = load_plan(run)
    rows = [summarize_job(run, plan, m) for m in GRID]
    summary = {"format": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
               "source_run": str(run), "plan_sha256": sha256(run / "plan.json"),
               "summarizer_sha256": sha256(__file__), "config": plan["config"],
               "probabilities": list(PROBABILITIES), "limitations": LIMITS,
               "tail_design": "Recorded q=0.995 GPD fits; default/minimum p=0.0005, supported through p=0.001; independent 5M fitting and 5M validation draws per exact m.",
               "legacy_label_correction": "Original engine CSV cutoff_p1e-7 and report p=1e-7 prose are stale labels. Original evidence remains unchanged; corrected cutoffs here are explicitly p=0.0005 and p=0.001.",
               "counts": {s: sum(r["status"] == s for r in rows) for s in ("accepted", "rejected", "failed", "incomplete", "not_started")},
               "results": rows, "warnings": []}
    out.mkdir(parents=True, exist_ok=False)
    copy_compact_evidence(run, out, rows)
    write_tables(out, rows)
    if make_plots:
        warning = plot(out, rows)
        if warning:
            summary["warnings"].append(warning)
    write_json(out / "summary.json", summary)
    lines = ["# Exact-m moderate-tail calibration", "", summary["tail_design"], "", LIMITS, "",
             summary["legacy_label_correction"], "", "| m | Stage | Status |", "|---:|:---|:---|"]
    lines.extend("| %s | %s | %s |" % (r["m"], r["stage"], r["status"]) for r in rows)
    lines += ["", "See summary.json for verified provenance and diagnostics, summary.csv for GPD parameters/cutoffs, and heldout.csv for independent exceedance counts and intervals. Original compact reports/logs are in evidence/. Raw streams are excluded.", ""]
    (out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    files = {p.relative_to(out).as_posix(): sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}
    write_json(out / "package_sha256.json", files)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skip-plots", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = summarize_run(args.run, args.out, not args.skip_plots)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("AP-MI sweep summary failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result["counts"], sort_keys=True))
    return 1 if result["counts"]["failed"] or result["counts"]["incomplete"] or result["counts"]["not_started"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
