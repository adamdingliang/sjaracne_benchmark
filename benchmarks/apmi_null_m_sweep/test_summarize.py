"""Synthetic-only tests. No production generator, calibration, or raw data used."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np


SPEC = importlib.util.spec_from_file_location("apmi_sweep_summarize", Path(__file__).with_name("summarize.py"))
SUMMARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUMMARY)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def hash_attempt(attempt):
    return {p.relative_to(attempt).as_posix(): SUMMARY.sha256(p)
            for p in sorted(attempt.rglob("*")) if p.is_file() and p.name != "result.json"}


def fixture(run, status="accepted", m=80):
    """Synthetic fit quantiles and independent 100/50 held-out exceedance counts."""
    config = copy.deepcopy(SUMMARY.EXPECTED_CONFIG)
    config.update(fit_draws=100_000, validation_draws=100_000, min_tail_count=100)
    plan = {"config": config, "generator_sha256": "synthetic-generator", "calibrator_sha256": "synthetic-calibrator"}
    attempt = run / "jobs" / ("m%05d" % m) / "attempt_0001"
    raw = attempt / "calibration" / "raw"
    raw.mkdir(parents=True)
    values = np.zeros(config["validation_draws"], dtype="<f8")
    values[-100:-50], values[-50:] = 0.02, 0.03
    fitting = np.zeros(config["fit_draws"], dtype="<f8")
    fitting[-500:] = np.linspace(0.001, 0.02, 500)
    hashes = {}
    for role in ("fit", "validation"):
        path = raw / ("m%05d_npar040_%s.f64" % (m, role))
        stream_values = fitting if role == "fit" else values
        stream_values.tofile(path)
        seed = config[role + "_seed"] + m + (1_000_000_000 if role == "validation" else 0)
        metadata = {"format": "sjaracne-apmi-null-binary-v1", "kernel_schema": "sjaracne-apmi-v1",
                    "estimator": "sjaracne-adaptive-partitioning", "rng": "mt19937-rejection-fisher-yates-v1",
                    "m": m, "draws": len(values), "npar_limit": 40, "seed": seed,
                    "dtype": "float64", "byte_order": "little", "record_bytes": 8}
        Path(str(path) + ".meta").write_text("\n".join("%s=%s" % pair for pair in metadata.items()) + "\n", encoding="utf-8")
        write_json(Path(str(path) + ".provenance.json"), {"format": "sjaracne-apmi-null-raw-provenance-v1", "generator_sha256": plan["generator_sha256"]})
        hashes[role] = SUMMARY.sha256(path)
    threshold = float(np.quantile(fitting, 0.995, method="higher"))
    count = int(np.count_nonzero(fitting > threshold))
    primary = {"threshold_quantile": 0.995, "threshold": threshold, "tail_count": count,
               "tail_probability": (count + 1) / (len(fitting) + 1), "shape": 0.0, "scale": 0.01, "endpoint": None}
    primary["cutoff_at_stability_probability"] = SUMMARY.cutoff(primary, 5e-4)
    sensitivity = []
    for q in (0.9925, 0.995, 0.9975):
        u = float(np.quantile(fitting, q, method="higher"))
        count = int(np.count_nonzero(fitting > u))
        pu = (count + 1) / (len(fitting) + 1)
        scale = (primary["cutoff_at_stability_probability"] - u) / math.log(pu / 5e-4)
        sensitivity.append({**primary, "threshold_quantile": q, "threshold": u,
                            "tail_count": count, "tail_probability": pu, "scale": scale})
    validation = [SUMMARY.heldout(values, SUMMARY.cutoff(primary, p), p, 0.999) for p in SUMMARY.PROBABILITIES]
    accepted = status == "accepted"
    if status == "rejected":
        # Scientific stability failure, while both held-out acceptance checks pass.
        sensitivity[0]["scale"] = 0.02
        stability_range = float(np.ptp([SUMMARY.cutoff(f, 5e-4) for f in sensitivity]) /
                                np.median([SUMMARY.cutoff(f, 5e-4) for f in sensitivity]))
    else:
        stability_range = float(np.ptp([SUMMARY.cutoff(f, 5e-4) for f in sensitivity]) /
                                np.median([SUMMARY.cutoff(f, 5e-4) for f in sensitivity]))
    model = {"m": m, "npar_limit": 40, "fit_draws": len(values), "validation_draws": len(values),
             "fit_seed": config["fit_seed"] + m, "validation_seed": config["validation_seed"] + 1_000_000_000 + m,
             "generator_sha256": plan["generator_sha256"], "calibrator_sha256": plan["calibrator_sha256"],
             "default_p": 5e-4, "supported_p_min": 5e-4, "supported_p_max": 1e-3,
             "kernel_schema": "sjaracne-apmi-v1", "tail_shape": 0.0, "tail_scale": 0.01,
             "tail_threshold": primary["threshold"], "tail_probability": primary["tail_probability"],
             "default_p_cutoff": SUMMARY.cutoff(primary, 5e-4),
             "fit_values_sha256": hashes["fit"], "validation_values_sha256": hashes["validation"],
             "calibration_status": status}
    result = {"m": m, "accepted": accepted, "model": model, "primary_fit": primary,
              "stability_fits": sensitivity, "skipped_stability_quantiles": [],
              "stability_probability": 5e-4, "relative_stability_range": stability_range,
              "stability_pass": accepted, "validation_pass": True,
              "validation_family_confidence": 0.99, "validation_family_comparisons": 10,
              "validation_point_confidence": 0.999, "validation": validation}
    if status != "failed":
        write_json(attempt / "calibration" / "calibration_report.json", {"results": [result], "tail_design": "stale p=1e-7"})
        (attempt / "calibration" / "calibration_summary.csv").write_text("m,cutoff_p1e-7\n80,0.023\n", encoding="utf-8")
    if accepted:
        (attempt / "calibration" / "apmi_null_m00080_npar040.model").write_text("\n".join("%s=%s" % item for item in model.items()) + "\n", encoding="utf-8")
    (attempt / "stderr.log").write_text("synthetic failure" if status == "failed" else "", encoding="utf-8")
    record = {"m": m, "status": status, "accepted": accepted, "returncode": 1 if status == "failed" else 0,
              "elapsed_seconds": 0.01, "error": "synthetic failure" if status == "failed" else None,
              "artifacts_sha256": hash_attempt(attempt)}
    write_json(attempt / "result.json", record)
    return plan, attempt, result


class TestSummaryMath(unittest.TestCase):
    def test_recorded_gpd_cutoff_exponential_and_bounded(self):
        fit = {"threshold": 0.1, "tail_probability": 0.005, "shape": 0, "scale": 0.02, "endpoint": None}
        self.assertAlmostEqual(SUMMARY.cutoff(fit, 5e-4), 0.1 + 0.02 * math.log(10))
        fit.update(shape=-0.5, endpoint=0.14)
        self.assertLess(SUMMARY.cutoff(fit, 5e-4), 0.14)
        with self.assertRaises(ValueError):
            SUMMARY.cutoff(fit, 0.1)

    def test_tied_empirical_quantile_uses_fit_only_and_greater_equal(self):
        fit = np.array([0.0] * 99 + [1.0])
        threshold = SUMMARY.higher_quantile(fit, 0.01)
        self.assertEqual(threshold, 1.0)
        heldout = SUMMARY.heldout(np.array([0.0, 1.0, 1.0, 2.0]), threshold, 0.01, 0.999)
        self.assertEqual(heldout["exceedances"], 3)
        self.assertEqual(heldout["draws"], 4)
        self.assertAlmostEqual(heldout["ratio_observed_to_nominal"], 75)


class TestSyntheticJobs(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run = Path(self.temporary.name) / "run"
        self.run.mkdir()

    def test_accepted_both_probabilities_and_actual_labels(self):
        plan, attempt, _ = fixture(self.run)
        report_hash = SUMMARY.sha256(attempt / "calibration" / "calibration_report.json")
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "accepted", row.get("error"))
        self.assertEqual([d["exceedances"] for d in row["gpd"]], [100, 50])
        self.assertAlmostEqual(row["gpd"][1]["stability_relative_range"], 0)
        self.assertTrue(all(d["diagnostic_only"] for d in row["empirical_diagnostic"]))
        out = Path(self.temporary.name) / "package"
        out.mkdir()
        SUMMARY.copy_compact_evidence(self.run, out, [row])
        SUMMARY.write_tables(out, [row])
        self.assertEqual(report_hash, SUMMARY.sha256(attempt / "calibration" / "calibration_report.json"))
        self.assertIn("cutoff_p_5e_4", (out / "summary.csv").read_text())
        self.assertIn("cutoff_p_1e_3", (out / "summary.csv").read_text())
        self.assertNotIn("cutoff_p1e-7", (out / "summary.csv").read_text())
        self.assertEqual(len(list(out.rglob("*.model"))), 1)
        self.assertEqual(list(out.rglob("*.f64")), [])
        self.assertEqual(list(out.rglob("*.bin")), [])
        copied = out / "evidence" / attempt.relative_to(self.run) / "calibration" / "calibration_report.json"
        self.assertEqual(SUMMARY.sha256(copied), report_hash)

    def test_scientific_rejection_remains_rejected_and_keeps_diagnostics(self):
        plan, _, _ = fixture(self.run, "rejected")
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "rejected", row.get("error"))
        self.assertFalse(row["accepted"])
        self.assertEqual(len(row["gpd"]), 2)
        self.assertEqual(len(row["empirical_diagnostic"]), 2)

    def test_model_fit_failure_retains_empirical_diagnostic_but_no_gpd(self):
        plan, _, _ = fixture(self.run, "failed")
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["gpd"], [])
        self.assertEqual(len(row["empirical_diagnostic"]), 2)

    def test_tampered_raw_fails_closed(self):
        plan, attempt, _ = fixture(self.run)
        path = next((attempt / "calibration" / "raw").glob("*_fit.f64"))
        with path.open("r+b") as handle:
            handle.write(b"tampered")
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        self.assertFalse(row["accepted"])
        self.assertIn("artifact hashes", row["error"])

    def test_identical_streams_cannot_be_called_held_out(self):
        plan, attempt, result = fixture(self.run)
        raw = attempt / "calibration" / "raw"
        fit = next(raw.glob("*_fit.f64"))
        validation = next(raw.glob("*_validation.f64"))
        validation.write_bytes(fit.read_bytes())
        result["model"]["validation_values_sha256"] = SUMMARY.sha256(validation)
        model_path = next((attempt / "calibration").glob("*.model"))
        model_path.write_text("\n".join("%s=%s" % item for item in result["model"].items()) + "\n", encoding="utf-8")
        write_json(attempt / "calibration" / "calibration_report.json", {"results": [result]})
        record = SUMMARY.read_json(attempt / "result.json")
        record["artifacts_sha256"] = hash_attempt(attempt)
        write_json(attempt / "result.json", record)
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        self.assertIn("streams are not distinct", row["error"])

    def test_degenerate_failed_fit_retains_tie_diagnostic_with_warning(self):
        plan, attempt, _ = fixture(self.run, "failed")
        for path in (attempt / "calibration" / "raw").glob("*.f64"):
            np.zeros(100_000, dtype="<f8").tofile(path)
        record = SUMMARY.read_json(attempt / "result.json")
        record["artifacts_sha256"] = hash_attempt(attempt)
        write_json(attempt / "result.json", record)
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(len(row["empirical_diagnostic"]), 2)
        self.assertEqual(row["empirical_diagnostic"][0]["observed_p"], 1)
        self.assertIn("degenerate", row["warnings"][0])

    def test_report_counts_disagreeing_with_raw_fail_closed(self):
        plan, attempt, result = fixture(self.run)
        result["validation"][0]["exceedances"] += 1
        write_json(attempt / "calibration" / "calibration_report.json", {"results": [result]})
        record = SUMMARY.read_json(attempt / "result.json")
        record["artifacts_sha256"] = hash_attempt(attempt)
        write_json(attempt / "result.json", record)
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        self.assertIn("validation does not match", row["error"])

    def test_rejected_attempt_cannot_package_runtime_model(self):
        plan, attempt, _ = fixture(self.run, "rejected")
        (attempt / "calibration" / "unexpected.model").write_text("not accepted")
        record = SUMMARY.read_json(attempt / "result.json")
        record["artifacts_sha256"] = hash_attempt(attempt)
        write_json(attempt / "result.json", record)
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        out = Path(self.temporary.name) / "package"
        out.mkdir()
        SUMMARY.copy_compact_evidence(self.run, out, [row])
        self.assertEqual(list(out.rglob("*.model")), [])

    def test_latest_incomplete_attempt_does_not_reuse_prior_acceptance(self):
        plan, attempt, _ = fixture(self.run)
        (attempt.parent / "attempt_0002").mkdir()
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "incomplete")
        self.assertEqual(row["attempt_count"], 2)
        self.assertFalse(row["accepted"])
        self.assertEqual(row["attempt_history"][0]["status"], "accepted")
        out = Path(self.temporary.name) / "package"
        out.mkdir()
        SUMMARY.copy_compact_evidence(self.run, out, [row])
        self.assertTrue((out / "evidence" / attempt.relative_to(self.run) / "result.json").is_file())
        self.assertEqual(list(out.rglob("*.model")), [])

    def test_duplicate_stability_quantile_fails_closed(self):
        plan, attempt, result = fixture(self.run)
        result["stability_fits"][0]["threshold_quantile"] = 0.995
        write_json(attempt / "calibration" / "calibration_report.json", {"results": [result]})
        record = SUMMARY.read_json(attempt / "result.json")
        record["artifacts_sha256"] = hash_attempt(attempt)
        write_json(attempt / "result.json", record)
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        self.assertIn("duplicate stability", row["error"])

    def test_stability_fit_must_include_actual_primary_candidate(self):
        plan, attempt, result = fixture(self.run)
        for candidate in result["stability_fits"]:
            candidate["scale"] *= 2
        write_json(attempt / "calibration" / "calibration_report.json", {"results": [result]})
        record = SUMMARY.read_json(attempt / "result.json")
        record["artifacts_sha256"] = hash_attempt(attempt)
        write_json(attempt / "result.json", record)
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        self.assertIn("primary fit disagrees", row["error"])

    def test_recorded_tail_count_must_match_fitting_draws(self):
        plan, attempt, result = fixture(self.run)
        result["primary_fit"]["tail_count"] += 1
        result["stability_fits"][1]["tail_count"] += 1
        write_json(attempt / "calibration" / "calibration_report.json", {"results": [result]})
        record = SUMMARY.read_json(attempt / "result.json")
        record["artifacts_sha256"] = hash_attempt(attempt)
        write_json(attempt / "result.json", record)
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        self.assertIn("does not match fitting draws", row["error"])

    def test_malformed_json_container_is_failed_row_not_global_crash(self):
        plan, attempt, _ = fixture(self.run)
        write_json(attempt / "result.json", [])
        row = SUMMARY.summarize_job(self.run, plan, 80)
        self.assertEqual(row["status"], "failed")
        self.assertIn("expected JSON object", row["error"])

    def test_synthetic_plot_contains_both_requested_outputs(self):
        try:
            import matplotlib
        except ImportError:
            self.skipTest("matplotlib not installed")
        plan, _, _ = fixture(self.run)
        row = SUMMARY.summarize_job(self.run, plan, 80)
        out = Path(self.temporary.name) / "plots"
        out.mkdir()
        self.assertIsNone(SUMMARY.plot(out, [row]))
        self.assertGreater((out / "cutoffs_and_heldout.png").stat().st_size, 1000)
        self.assertGreater((out / "cutoffs_and_heldout.svg").stat().st_size, 1000)

    def test_missing_all_eleven_sizes_and_exclusive_output(self):
        plan = {"format": "sjaracne-staged-apmi-calibration-v1", "m": SUMMARY.GRID,
                "config": SUMMARY.EXPECTED_CONFIG, "stability_quantiles": [0.9925, 0.995, 0.9975]}
        write_json(self.run / "plan.json", plan)
        (self.run / "plan.sha256").write_text(SUMMARY.sha256(self.run / "plan.json"))
        out = Path(self.temporary.name) / "package"
        result = SUMMARY.summarize_run(self.run, out, make_plots=False)
        self.assertEqual(len(result["results"]), 11)
        self.assertEqual(result["counts"]["not_started"], 11)
        self.assertIn("0.0005", result["tail_design"])
        self.assertNotIn("1e-7", result["tail_design"])
        self.assertTrue((out / "package_sha256.json").is_file())
        with self.assertRaises(ValueError):
            SUMMARY.summarize_run(self.run, out, make_plots=False)
        with self.assertRaises(ValueError):
            SUMMARY.summarize_run(self.run, self.run / "nested", make_plots=False)

    def test_plan_hash_mismatch_is_rejected(self):
        write_json(self.run / "plan.json", {})
        (self.run / "plan.sha256").write_text("wrong hash")
        with self.assertRaises(ValueError):
            SUMMARY.load_plan(self.run)


if __name__ == "__main__":
    unittest.main()
