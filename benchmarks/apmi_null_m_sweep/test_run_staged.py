"""Synthetic runner checks: no generator, WSL, or calibration is launched."""
import importlib.util
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("run_staged", Path(__file__).with_name("run_staged.py"))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class StagedRunnerTests(unittest.TestCase):
    def test_frozen_protocol(self):
        self.assertEqual(len(runner.ALL_M), 11)
        self.assertEqual(runner.STAGES["dream"], [644, 516, 725])
        self.assertEqual(runner.CONFIG["fit_draws"], 5_000_000)
        self.assertEqual(runner.CONFIG["validation_draws"], 5_000_000)
        self.assertEqual(runner.CONFIG["p_min"], 5e-4)
        self.assertEqual(runner.CONFIG["default_p"], 5e-4)
        self.assertEqual(runner.CONFIG["validation_family_comparisons"], 10)
        self.assertEqual(runner.CONFIG["min_tail_count"], 20_000)
        self.assertEqual(runner.CONFIG["min_stability_fits"], 3)

    def test_wsl_path(self):
        self.assertEqual(runner.native_path(r"D:\GitHub\space dir\x", "Ubuntu"), "/mnt/d/GitHub/space dir/x")
        with self.assertRaises(ValueError):
            runner.native_path(r"\\server\share\x", "Ubuntu")

    def test_command_fits_only_checked_raw_locally(self):
        plan = {"execution": {"distro": "Ubuntu", "python": "/opt/env/bin/python", "time_program": "/usr/bin/time"},
                "calibrator": r"D:\engine\calibrate.py", "generator": r"D:\build\null", "config": runner.CONFIG}
        command = runner.calibration_command(plan, 644, Path(r"D:\runs\m644"))
        self.assertEqual(command[0], "/opt/env/bin/python")
        self.assertNotIn("wsl.exe", command)
        self.assertIn("--allow-rejected-calibration", command)
        self.assertIn("--reuse-raw", command)
        self.assertEqual(command[command.index("--m") + 1], "644")
        self.assertEqual(command[command.index("--p-min") + 1], "0.0005")

    def test_generation_command_uses_wsl_and_disjoint_seed(self):
        plan = {"execution": {"distro": "Ubuntu", "time_program": "/usr/bin/time"},
                "generator": r"D:\build\null", "config": runner.CONFIG}
        command = runner.generation_command(plan, 644, Path(r"D:\runs\m644"), "validation")
        self.assertEqual(command[:4], ["wsl.exe", "--distribution", "Ubuntu", "--exec"])
        self.assertEqual(command[command.index("--seed") + 1], str(20261016 + 1_000_000_000 + 644))
        self.assertIn("NUMEXPR_NUM_THREADS=1", command)

    def test_new_json_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            runner.json_write_new(path, {"a": 1})
            with self.assertRaises(FileExistsError):
                runner.json_write_new(path, {"a": 2})
            self.assertEqual(runner.read_json(path), {"a": 1})

    def test_tampered_completed_attempt_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            (attempt / "raw.f64").write_bytes(b"test")
            runner.json_write_new(attempt / "result.json", {"status": "rejected", "artifacts_sha256": runner.artifact_hashes(attempt)})
            self.assertEqual(runner.verify_result(attempt)["status"], "rejected")
            (attempt / "raw.f64").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "artifacts changed"):
                runner.verify_result(attempt)

    def report_fixture(self, attempt, accepted):
        calibration = attempt / "calibration"
        calibration.mkdir()
        config = runner.CONFIG
        model = {"m": 30, "npar_limit": 40, "fit_draws": 5_000_000,
                 "validation_draws": 5_000_000, "fit_seed": 20261045,
                 "validation_seed": 1020261046, "generator_sha256": "generator",
                 "calibrator_sha256": "calibrator", "default_p": 5e-4,
                 "supported_p_min": 5e-4, "validation_family_confidence": .99,
                 "calibration_status": "accepted" if accepted else "rejected", "default_p_cutoff": .1}
        result = {"m": 30, "model": model, "accepted": accepted,
                  "validation_family_comparisons": 10, "stability_pass": accepted,
                  "validation_pass": True, "relative_stability_range": .01,
                  "primary_fit": {"threshold_quantile": .995, "tail_count": 24999},
                  "stability_fits": [{"threshold_quantile": q} for q in (.9925, .995, .9975)],
                  "validation": [{"nominal_p": p} for p in (.001, .0005)]}
        raw = calibration / "raw"
        raw.mkdir()
        for role in ("fit", "validation"):
            path = raw / ("m00030_npar040_%s.f64" % role)
            path.write_bytes(struct.pack("<d", .1))
            model[role + "_values_sha256"] = runner.sha256(path)
        runner.json_write_new(calibration / "calibration_report.json", {"results": [result]})
        if accepted:
            (calibration / "exact.model").write_text("accepted")
        return {"config": config, "generator_sha256": "generator", "calibrator_sha256": "calibrator"}

    def raw_fixture(self, attempt):
        generator = attempt / "generator"
        generator.write_bytes(b"not executable; synthetic only")
        config = dict(runner.CONFIG, fit_draws=2)
        plan = {"config": config, "generator": str(generator), "generator_sha256": runner.sha256(generator)}
        path = runner.stream_path(plan, 30, attempt, "fit")
        path.parent.mkdir(parents=True)
        path.write_bytes(struct.pack("<dd", .1, .2))
        metadata = {"format": "sjaracne-apmi-null-binary-v1", "kernel_schema": "sjaracne-apmi-v1",
                    "estimator": "sjaracne-adaptive-partitioning", "rng": "mt19937-rejection-fisher-yates-v1",
                    "m": "30", "draws": "2", "npar_limit": "40", "seed": "20261045",
                    "dtype": "float64", "byte_order": "little", "record_bytes": "8"}
        Path(str(path) + ".meta").write_text("\n".join(k + "=" + v for k, v in metadata.items()))
        runner.json_write_new(Path(str(path) + ".provenance.json"), {"format": "sjaracne-apmi-null-raw-provenance-v1", "generator_sha256": plan["generator_sha256"]})
        return plan, path

    def test_raw_preflight_checks_provenance_support_and_length(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, path = self.raw_fixture(Path(directory))
            self.assertEqual(runner.check_raw(plan, 30, Path(directory), "fit")["sha256"], runner.sha256(path))
            path.write_bytes(struct.pack("<dd", .1, float("nan")))
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                runner.check_raw(plan, 30, Path(directory), "fit")
            path.write_bytes(struct.pack("<d", .1))
            with self.assertRaisesRegex(ValueError, "length"):
                runner.check_raw(plan, 30, Path(directory), "fit")
        with tempfile.TemporaryDirectory() as directory:
            plan, path = self.raw_fixture(Path(directory))
            Path(str(path) + ".provenance.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "provenance"):
                runner.check_raw(plan, 30, Path(directory), "fit")

    def test_scientific_rejection_retains_diagnostic_not_model(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            plan = self.report_fixture(attempt, False)
            result = runner.inspect_calibration(plan, 30, attempt, 0)
            self.assertEqual(result["status"], "rejected")
            self.assertIsNone(result["model_path"])
            self.assertEqual(result["cutoff_at_default_p_5e_4"], .1)

    def test_accepted_and_failed_process_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            plan = self.report_fixture(attempt, True)
            self.assertEqual(runner.inspect_calibration(plan, 30, attempt, 0)["status"], "accepted")
            with self.assertRaisesRegex(ValueError, "failed process left a model"):
                runner.inspect_calibration(plan, 30, attempt, 1)
        with tempfile.TemporaryDirectory() as directory:
            result = runner.inspect_calibration({}, 30, Path(directory), 1)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failure_kind"], "computational-or-model-fit-failure")

    def test_report_seed_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            plan = self.report_fixture(attempt, True)
            path = attempt / "calibration" / "calibration_report.json"
            report = runner.read_json(path)
            report["results"][0]["model"]["fit_seed"] += 1
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "fit_seed"):
                runner.inspect_calibration(plan, 30, attempt, 0)

    def test_gnu_time_rss(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "time.txt"
            path.write_text("Maximum resident set size (kbytes): 123456\n")
            self.assertEqual(runner.parse_time(path)["maximum_resident_set_kbytes"], 123456)

    def test_output_lock_disallows_concurrent_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with runner.output_lock(out):
                with self.assertRaises(ValueError):
                    with runner.output_lock(out):
                        self.fail("concurrent output lock accepted")
            with runner.output_lock(out):
                pass

    def test_mock_pipeline_generates_two_streams_then_fits_once(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "jobs").mkdir()
            (out / "invocation").mkdir()
            generator = out / "generator"
            generator.write_bytes(b"synthetic")
            plan = {"output_dir": str(out), "engine_root": str(out), "config": runner.CONFIG,
                    "execution": {"distro": None, "python": sys.executable, "time_program": "/usr/bin/time"}}
            for name in ("generator", "calibrator", "runner", "runner_tests"):
                plan[name] = str(generator)
                plan[name + "_sha256"] = runner.sha256(generator)
            process = unittest.mock.Mock()
            process.poll.return_value = 0
            process.wait.return_value = 0
            with patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as generate, \
                 patch.object(runner.subprocess, "Popen", return_value=process) as fit, \
                 patch.object(runner, "check_raw", return_value={"sha256": "synthetic"}), \
                 patch.object(runner, "peak_working_set", return_value=None), \
                 patch.object(runner, "inspect_calibration", return_value={"status": "rejected", "accepted": False}):
                record = runner.run_one(plan, 30, out / "invocation")
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(fit.call_count, 1)
            self.assertIn("--reuse-raw", fit.call_args.args[0])
            self.assertEqual(record["status"], "rejected")
            attempt = Path(record["attempt"])
            self.assertEqual(runner.verify_result(attempt)["status"], "rejected")
            for role in ("fit", "validation"):
                self.assertTrue(Path(str(runner.stream_path(plan, 30, attempt, role)) + ".provenance.json").is_file())

    def test_mock_native_failure_isolated_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "jobs").mkdir()
            generator = out / "generator"
            generator.write_bytes(b"synthetic")
            plan = {"output_dir": str(out), "engine_root": str(out), "config": runner.CONFIG,
                    "execution": {"distro": None, "python": sys.executable, "time_program": "/usr/bin/time"}}
            for name in ("generator", "calibrator", "runner", "runner_tests"):
                plan[name] = str(generator)
                plan[name + "_sha256"] = runner.sha256(generator)
            with patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 9)), \
                 patch.object(runner.subprocess, "Popen") as fit:
                record = runner.run_one(plan, 30, out / "invocation")
            fit.assert_not_called()
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["returncode"], 9)
            self.assertIn("native fit generator failed", record["error"])
            self.assertEqual(runner.verify_result(Path(record["attempt"]))["status"], "failed")


if __name__ == "__main__":
    unittest.main()
