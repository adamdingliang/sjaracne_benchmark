"""Synthetic/mocked capacity tests. No helper or native executable is launched."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("apmi_time_capacity", Path(__file__).with_name("time_capacity.py"))
CAPACITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPACITY)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


class TestCapacityTiming(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runs = self.root / "runs"
        self.out = self.runs / "capacity"
        self.generator = self.root / "mock_generator"
        self.generator.write_bytes(b"synthetic never executable")
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(CAPACITY, "runs_root", return_value=self.runs).start()
        mock.patch.object(CAPACITY, "EXPECTED_GENERATOR", CAPACITY.record(self.generator)["sha256"]).start()
        self.calls = []
        self.lock = threading.Lock()
        self.fail_worker = None
        self.raise_worker = None
        self.tamper_worker = None
        self.process = mock.patch.object(CAPACITY.subprocess, "run", side_effect=self.fake_helper).start()

    def fake_helper(self, argv, **kwargs):
        """Materialize only small synthetic timing evidence, not an actual process."""
        helper_out = Path(argv[argv.index("--out") + 1])
        number = int(helper_out.parent.name.split("_")[1])
        request_path = helper_out.parent.parent / "capacity_request.json"
        self.assertTrue(request_path.is_file(), "request must precede every process launch")
        request = CAPACITY.read_object(request_path)
        self.assertEqual(CAPACITY.record(request_path)["sha256"], request_path.with_suffix(".sha256").read_text().strip())
        self.assertEqual(argv, request["worker_requests"][number - 1]["argv"])
        for key, value in CAPACITY.ENV_CONTROLS.items():
            self.assertEqual(kwargs["env"][key], value)
        self.assertFalse(kwargs["check"])
        self.assertNotIn("--fit-draws", argv)
        self.assertNotIn("calibrate_apmi_null.py", " ".join(argv))
        with self.lock:
            self.calls.append(number)
        if number == self.raise_worker:
            raise OSError("synthetic process launch error")
        if number == self.fail_worker:
            kwargs["stderr"].write(b"synthetic helper failure")
            return SimpleNamespace(returncode=7)
        m = int(argv[argv.index("--m") + 1])
        draws = int(argv[argv.index("--draws") + 1])
        data = helper_out / ("m%05d" % m)
        data.mkdir(parents=True)
        (data / "timing.f64").write_bytes(b"\x00" * (8 * draws))
        (data / "timing.f64.meta").write_text("m=%s\ndraws=%s\nseed=%s\n" % (m, draws, request["helper_seed"]))
        (data / "stdout.log").write_bytes(b"")
        (data / "stderr.log").write_bytes(b"")
        (data / "time.tsv").write_text("1.25\t1.20\t0.01\t4096\n")
        job = {"m": m, "draws": draws, "seed": request["helper_seed"], "native_exit_code": 0,
               "native_wall_seconds": 1.25, "user_seconds": 1.2, "system_seconds": 0.01,
               "peak_rss_kib": 4096, "total_wall_seconds": 1.3,
               "artifacts": {p.name: CAPACITY.record(p) for p in data.iterdir()}}
        write_json(data / "job.json", job)
        result = {"status": "complete", "draws": draws, "m": [m], "npar": 40,
                  "generator": request["generator"], "script": request["helper"], "jobs": [job]}
        if number == self.tamper_worker:
            result["draws"] += 1
        write_json(helper_out / "timing_results.json", result)
        return SimpleNamespace(returncode=0)

    def test_default_eight_worker_request_frozen_before_launch_and_all_results_retained(self):
        result = CAPACITY.run_capacity(self.generator, self.out)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(sorted(self.calls), list(range(1, 9)))
        self.assertEqual(self.process.call_count, 8)
        self.assertEqual(result["worker_returncodes"], {str(i): 0 for i in range(1, 9)})
        self.assertEqual(result["successful_workers"], 8)
        self.assertGreater(result["batch_wall_seconds"], 0)
        self.assertEqual(result["native_wall_seconds_min"], 1.25)
        self.assertEqual(result["native_wall_seconds_median"], 1.25)
        self.assertEqual(result["native_wall_seconds_max"], 1.25)
        self.assertAlmostEqual(result["aggregate_draws_per_batch_wall_second"], 800_000 / result["batch_wall_seconds"])
        request = CAPACITY.read_object(self.out / "capacity_request.json")
        self.assertEqual((request["workers"], request["draws"], request["m"]), (8, 100_000, 10_000))
        self.assertEqual(request["total_requested_timing_draws"], 800_000)
        self.assertEqual(request["expected_generator_sha256"], CAPACITY.record(self.generator)["sha256"])
        self.assertEqual(request["helper"]["path"], str(CAPACITY.helper_path().resolve()))
        self.assertIn("not independent scientific streams", request["seed_warning"])
        self.assertIn("no models", result["purpose"])
        self.assertEqual(len(list(self.out.glob("worker_*/result.json"))), 8)
        self.assertEqual(len(list(self.out.glob("worker_*/helper/m10000/timing.f64"))), 8)
        self.assertEqual(list(self.out.rglob("*.model")), [])
        self.assertTrue(result["request_unchanged"])

    def test_nonzero_worker_exit_is_retained_without_retry_or_suppressed_peers(self):
        self.fail_worker = 2
        result = CAPACITY.run_capacity(self.generator, self.out, workers=3, draws=5, m=5000)
        self.assertEqual(sorted(self.calls), [1, 2, 3])
        self.assertEqual(self.process.call_count, 3)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["worker_returncodes"], {"1": 0, "2": 7, "3": 0})
        self.assertEqual(result["successful_workers"], 2)
        self.assertIsNone(result["aggregate_draws_per_batch_wall_second"])
        self.assertIn("return code 7", result["results"][1]["error"])
        self.assertTrue((self.out / "worker_002" / "stderr.log").read_bytes())

    def test_process_launch_error_retains_none_returncode_and_other_workers(self):
        self.raise_worker = 1
        result = CAPACITY.run_capacity(self.generator, self.out, workers=2, draws=3, m=2000)
        self.assertEqual(result["worker_returncodes"], {"1": None, "2": 0})
        self.assertEqual(result["status"], "failed")
        self.assertIn("launch error", result["results"][0]["error"])

    def test_success_exit_with_invalid_helper_evidence_is_failed(self):
        self.tamper_worker = 1
        result = CAPACITY.run_capacity(self.generator, self.out, workers=2, draws=3)
        self.assertEqual(result["worker_returncodes"], {"1": 0, "2": 0})
        self.assertEqual(result["status"], "failed")
        self.assertIn("frozen request", result["results"][0]["error"])

    def test_limits_prevent_science_sized_draws_or_excess_concurrency(self):
        invalid = ({"workers": 0}, {"workers": 13}, {"draws": 0}, {"draws": 200_001},
                   {"draws": 10_000_000}, {"m": 1}, {"m": 10_001}, {"workers": True})
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CAPACITY.run_capacity(self.generator, self.out, **kwargs)
        self.process.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_wrong_generator_pin_is_rejected_before_creating_output(self):
        with mock.patch.object(CAPACITY, "EXPECTED_GENERATOR", "0" * 64):
            with self.assertRaisesRegex(ValueError, "generator binary SHA256"):
                CAPACITY.run_capacity(self.generator, self.out)
        self.process.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_output_must_be_fresh_ignored_runs_child(self):
        for invalid_out in (self.runs, self.root / "outside"):
            with self.subTest(out=invalid_out), self.assertRaisesRegex(ValueError, "fresh child"):
                CAPACITY.run_capacity(self.generator, invalid_out)
        CAPACITY.run_capacity(self.generator, self.out, workers=1, draws=3)
        digest = CAPACITY.record(self.out / "capacity_results.json")["sha256"]
        with self.assertRaisesRegex(ValueError, "fresh child"):
            CAPACITY.run_capacity(self.generator, self.out)
        self.assertEqual(CAPACITY.record(self.out / "capacity_results.json")["sha256"], digest)
        self.assertEqual(self.process.call_count, 1)

    def test_source_pin_drift_fails_workers_without_launching(self):
        with mock.patch.object(CAPACITY, "verify_pins", side_effect=ValueError("helper changed")):
            result = CAPACITY.run_capacity(self.generator, self.out, workers=2, draws=3)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["worker_returncodes"], {"1": None, "2": None})
        self.process.assert_not_called()

    def test_worker_directory_error_does_not_erase_other_worker_returncodes(self):
        real_worker = CAPACITY.worker
        def broken_worker(request, specification, environment, start_event):
            if specification["worker"] == 1:
                raise OSError("synthetic directory error")
            return real_worker(request, specification, environment, start_event)
        with mock.patch.object(CAPACITY, "worker", side_effect=broken_worker):
            result = CAPACITY.run_capacity(self.generator, self.out, workers=2, draws=3)
        self.assertEqual(result["worker_returncodes"], {"1": None, "2": 0})
        self.assertEqual(result["status"], "failed")
        self.assertIn("orchestration failed", result["results"][0]["error"])

    def test_postprocess_hash_failure_keeps_known_process_returncode(self):
        real_record = CAPACITY.record
        def fail_final_worker_hash(path):
            path = Path(path)
            if path.name == "stdout.log" and path.parent.name == "worker_001":
                raise OSError("synthetic post-process hash failure")
            return real_record(path)
        with mock.patch.object(CAPACITY, "record", side_effect=fail_final_worker_hash):
            result = CAPACITY.run_capacity(self.generator, self.out, workers=2, draws=3)
        self.assertEqual(result["worker_returncodes"], {"1": 0, "2": 0})
        self.assertEqual(result["status"], "failed")
        self.assertIn("Evidence hashing failed", result["results"][0]["error"])
        self.assertIsNotNone(result["results"][0]["job"])

    def test_worker_result_write_failure_keeps_known_process_returncode_in_parent(self):
        real_write = CAPACITY.write_new
        def fail_worker_result(path, value):
            path = Path(path)
            if path.name == "result.json" and path.parent.name == "worker_001":
                raise OSError("synthetic result write failure")
            return real_write(path, value)
        with mock.patch.object(CAPACITY, "write_new", side_effect=fail_worker_result):
            result = CAPACITY.run_capacity(self.generator, self.out, workers=2, draws=3)
        self.assertEqual(result["worker_returncodes"], {"1": 0, "2": 0})
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["results"][0]["worker_result_persisted"])
        persisted = CAPACITY.read_object(self.out / "capacity_results.json")
        self.assertEqual(persisted["worker_returncodes"], {"1": 0, "2": 0})
        self.assertIn("persistence failed", persisted["results"][0]["error"])

    def test_thread_controls_forward_to_wsl_without_mutating_parent_environment(self):
        with mock.patch.dict(os.environ, {"WSLENV": "PATH/l:OMP_NUM_THREADS/w:UNCHANGED/u", "OMP_NUM_THREADS": "9"}):
            environment = CAPACITY.child_environment(windows=True)
            self.assertEqual(os.environ["OMP_NUM_THREADS"], "9")
            self.assertEqual(environment["OMP_NUM_THREADS"], "1")
            self.assertIn("PATH/l", environment["WSLENV"].split(":"))
            self.assertIn("UNCHANGED/u", environment["WSLENV"].split(":"))
            self.assertNotIn("OMP_NUM_THREADS/w", environment["WSLENV"].split(":"))
            for key in CAPACITY.ENV_CONTROLS:
                self.assertIn(key + "/u", environment["WSLENV"].split(":"))


if __name__ == "__main__":
    unittest.main()
