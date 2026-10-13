"""Synthetic background-driver tests; never start native inference or R."""

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_full_baseline as module


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.results = self.root / "results"
        self.results.mkdir()
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.prepared = self.results / "prepared"
        self.prepared.mkdir()
        for name, content in (("expression.exp", "probe\tdescription\tNT1\nA\tA\t1\n"),
                              ("hubs.txt", "A\n"),
                              ("reference_positive_edges.tsv", "source\ttarget\nA\tB\n")):
            (self.prepared / name).write_text(content, encoding="utf-8")
        self.prep = self.prepared / "prepare_manifest.json"
        self.write(self.prep, {"status": "complete", "outputs": {
            name: module.run_legacy.record_file(self.prepared / name)
            for name in ("expression.exp", "hubs.txt", "reference_positive_edges.tsv")}})
        self.audit = self.results / "independent_audit.json"
        self.write(self.audit, {"status": "pass", "prepare_manifest_sha256": module.sha256(self.prep)})
        native = self.assets / "sources" / "SJARACNe-v0.2.1"
        self.component = native / "build_record.json"
        self.component.parent.mkdir(parents=True)
        self.component.write_text("synthetic pinned component manifest", encoding="utf-8")
        self.smoke_dir = self.results / "legacy_smoke"
        self.smoke_dir.mkdir()
        self.adj = self.smoke_dir / "bootstrap_001.adj"
        self.adj.write_text("A\tB\t0.2\n", encoding="utf-8")
        self.log = self.smoke_dir / "native.log"
        self.log.write_text("synthetic native success\n", encoding="utf-8")
        self.smoke_path = self.smoke_dir / "run_manifest.json"
        self.smoke = {"status": "bootstraps_complete", "frozen": {
            "source_commit": module.run_legacy.SOURCE_COMMIT,
            "parameters": {"bootstrap_count": 1, "seeds": [1], "bootstrap_p": 1e-7,
                           "consensus_p": [0.01, 0.001], "npar": 40, "dpi_tolerance": 0,
                           "sampling": "legacy -r 1", "algorithm": "adaptive_partitioning",
                           "explicit_mi_override": None},
            "inputs": {key: module.run_legacy.record_file(self.prepared / name) for key, name in (
                ("expression", "expression.exp"), ("hubs", "hubs.txt"),
                ("prepare_manifest", "prepare_manifest.json"))},
            "component_manifest": module.run_legacy.record_file(self.component),
            "components": {"synthetic_component": module.run_legacy.record_file(self.component)}},
            "bootstraps": {"1": {"seed": 1, "status": "complete", "started": 10, "finished": 20,
                                    "artifacts": {"adjacency": module.run_legacy.record_file(self.adj),
                                                  "log": module.run_legacy.record_file(self.log)}}},
            "consensus": {}}
        self.write(self.smoke_path, self.smoke)
        self.calls = []
        self.events = []

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def checkpoint(self):
        return json.loads((self.results / "driver" / "status.json").read_text(encoding="utf-8"))

    def finish_comparison(self):
        comparison = self.results / "comparison"
        comparison.mkdir()
        (comparison / "REPORT.md").write_text("Synthetic verified comparison\n", encoding="utf-8")
        self.write(comparison / "summary.json", {"status": "complete", "exact_reproduction_established": False})
        self.write(comparison / "status.json", {"status": "complete", "outputs": {
            name: module.run_legacy.record_file(comparison / name) for name in ("REPORT.md", "summary.json")}})

    def fake_popen(self, command, *, stdout, stderr):
        self.assertEqual(stderr, module.subprocess.STDOUT)
        self.assertFalse(stdout.closed)
        number = len(self.calls)
        self.calls.append(command)
        self.events.append("start" + str(number))
        owner = self

        class Process:
            pid = 31000 + number

            def wait(self):
                status = owner.checkpoint()
                owner.assertEqual(status["child_pid"], self.pid)
                owner.assertEqual(status["command"], command)
                owner.assertTrue(Path(status["log"]).is_file())
                owner.events.append("wait" + str(number))
                stdout.write("Synthetic child success\n")
                if number == 1:
                    owner.finish_comparison()
                return 0

        return Process()

    def execute(self, popen=None, wait=None, workers=8):
        argv = [str(Path(module.__file__)), "--result-root", str(self.results),
                "--assets-root", str(self.assets), "--workers", str(workers)]
        with patch.object(module.sys, "argv", argv), \
                patch.object(module.subprocess, "Popen", popen or self.fake_popen), \
                contextlib.redirect_stdout(io.StringIO()):
            if wait is None:
                return module.main()
            with patch.object(module, "wait_for_smoke", wait):
                return module.main()

    def test_smoke_accepts_only_verified_one_seed_job(self):
        with patch.object(module.time, "sleep") as sleep:
            result = module.wait_for_smoke(self.smoke_path, self.prepared)
        self.assertEqual(result, self.smoke)
        sleep.assert_not_called()

    def test_smoke_pending_waits_then_verifies(self):
        pending = copy.deepcopy(self.smoke)
        pending["status"] = "incomplete"
        pending["bootstraps"] = {}
        self.write(self.smoke_path, pending)

        def finish(interval):
            self.assertEqual(interval, 7)
            self.write(self.smoke_path, self.smoke)

        with patch.object(module.time, "sleep", finish):
            self.assertEqual(module.wait_for_smoke(self.smoke_path, self.prepared, interval=7), self.smoke)

    def test_smoke_wrong_bootstrap_count_rejected_without_wait(self):
        self.smoke["frozen"]["parameters"]["bootstrap_count"] = 100
        self.write(self.smoke_path, self.smoke)
        with patch.object(module.time, "sleep") as sleep, self.assertRaises(ValueError):
            module.wait_for_smoke(self.smoke_path, self.prepared)
        sleep.assert_not_called()

    def test_smoke_wrong_seed_or_protocol_rejected(self):
        for key, value in (("seeds", [2]), ("bootstrap_p", .001), ("npar", 41),
                           ("dpi_tolerance", .1), ("sampling", "without replacement"),
                           ("algorithm", "gaussian_kernel"),
                           ("explicit_mi_override", .1)):
            with self.subTest(key=key):
                changed = copy.deepcopy(self.smoke)
                changed["frozen"]["parameters"][key] = value
                self.write(self.smoke_path, changed)
                with patch.object(module.time, "sleep") as sleep, self.assertRaises(ValueError):
                    module.wait_for_smoke(self.smoke_path, self.prepared)
                sleep.assert_not_called()

    def test_smoke_wrong_source_rejected(self):
        self.smoke["frozen"]["source_commit"] = "wrong"
        self.write(self.smoke_path, self.smoke)
        with self.assertRaisesRegex(ValueError, "legacy baseline protocol"):
            module.wait_for_smoke(self.smoke_path, self.prepared)

    def test_smoke_input_hash_must_match_full_inputs(self):
        (self.prepared / "expression.exp").write_text("different", encoding="utf-8")
        with patch.object(module.time, "sleep") as sleep, self.assertRaisesRegex(ValueError, "inputs differ"):
            module.wait_for_smoke(self.smoke_path, self.prepared)
        sleep.assert_not_called()

    def test_smoke_failed_top_level_without_record_fails_closed(self):
        self.smoke.update(status="failed", bootstraps={})
        self.write(self.smoke_path, self.smoke)
        with patch.object(module.time, "sleep") as sleep, self.assertRaisesRegex(RuntimeError, "smoke failed"):
            module.wait_for_smoke(self.smoke_path, self.prepared)
        sleep.assert_not_called()

    def test_smoke_failed_record_fails_closed(self):
        self.smoke["bootstraps"]["1"]["status"] = "failed"
        self.write(self.smoke_path, self.smoke)
        with patch.object(module.time, "sleep") as sleep, self.assertRaisesRegex(RuntimeError, "smoke failed"):
            module.wait_for_smoke(self.smoke_path, self.prepared)
        sleep.assert_not_called()

    def test_smoke_record_seed_must_be_one_and_unique(self):
        for label, mutate in (("wrong_record_seed", lambda state: state["bootstraps"]["1"].update(seed=2)),
                              ("extra_record", lambda state: state["bootstraps"].update({"2": copy.deepcopy(state["bootstraps"]["1"])}))):
            changed = copy.deepcopy(self.smoke)
            mutate(changed)
            self.write(self.smoke_path, changed)
            with self.subTest(label=label), self.assertRaises(ValueError):
                module.wait_for_smoke(self.smoke_path, self.prepared)

    def test_smoke_requires_adjacency_and_log_artifact_hashes(self):
        self.smoke["bootstraps"]["1"]["artifacts"] = {}
        self.write(self.smoke_path, self.smoke)
        with self.assertRaises(ValueError):
            module.wait_for_smoke(self.smoke_path, self.prepared)

    def test_smoke_completed_artifact_tamper_rejected(self):
        self.adj.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Completed output changed"):
            module.wait_for_smoke(self.smoke_path, self.prepared)

    def test_smoke_frozen_component_tamper_rejected(self):
        self.component.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Frozen input/component changed"):
            module.wait_for_smoke(self.smoke_path, self.prepared)

    def test_full_stages_run_in_order_after_smoke_and_publish_verified_report(self):
        def smoke_gate(path, prepared):
            self.assertEqual(self.calls, [])
            self.assertEqual(self.checkpoint()["status"], "waiting_for_smoke")
            self.events.append("smoke")
            return module.wait_for_smoke_original(path, prepared)

        with patch.object(module, "wait_for_smoke_original", module.wait_for_smoke, create=True):
            self.execute(wait=smoke_gate)
        self.assertEqual(self.events, ["smoke", "start0", "wait0", "start1", "wait1"])
        self.assertEqual(len(self.calls), 2)
        native, scoring = self.calls
        self.assertEqual(Path(native[1]).name, "run_legacy.py")
        self.assertEqual(native[2], "run")
        self.assertEqual(native[native.index("--bootstrap-count") + 1], "100")
        self.assertEqual(native[native.index("--workers") + 1], "8")
        self.assertIn(str(self.prep), native)
        self.assertIn(str(self.component), native)
        native_root = self.assets / "sources" / "SJARACNe-v0.2.1" / "SJARACNe"
        self.assertEqual(native[native.index("--binary") + 1], str(native_root / "bin" / "sjaracne.exe"))
        self.assertEqual(native[native.index("--config") + 1], str(native_root / "config"))
        self.assertEqual(native[native.index("--consensus-script") + 1],
                         str(native_root / "bin" / "create_consensus_network.py"))
        self.assertEqual(Path(scoring[1]).name, "complete_baseline.py")
        self.assertEqual(scoring[scoring.index("--wsl-r-env") + 1],
                         module.run_legacy.wsl_path(self.assets / "toolchain" / "r44"))
        self.assertEqual(scoring[scoring.index("--wsl-r-library") + 1],
                         module.run_legacy.wsl_path(self.assets / "toolchain" / "paper_r_library"))
        self.assertNotIn("--wait-for-run", scoring)
        status = self.checkpoint()
        self.assertEqual(status["status"], "complete")
        self.assertIsNone(status["child_pid"])
        self.assertEqual(status["smoke_duration_seconds"], 10)
        self.assertEqual(status["smoke_manifest_sha256"], module.sha256(self.smoke_path))
        self.assertIn("no PR70/PR71/K", status["scope"])

    def test_existing_driver_is_never_adopted_or_overwritten(self):
        driver = self.results / "driver"
        driver.mkdir()
        keep = driver / "keep"
        keep.write_text("preserve", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(keep.read_text(encoding="utf-8"), "preserve")
        self.assertFalse(self.calls)

    def test_incomplete_preparation_or_failed_audit_blocks_before_driver_creation(self):
        for filename, state in ((self.prep, {"status": "inference_inputs_ready"}),
                                (self.audit, {"status": "fail"})):
            original = filename.read_text(encoding="utf-8")
            self.write(filename, state)
            with self.subTest(path=filename), self.assertRaises(ValueError):
                self.execute()
            self.assertFalse((self.results / "driver").exists())
            self.assertFalse(self.calls)
            filename.write_text(original, encoding="utf-8")

    def test_audit_must_bind_preparation_before_any_child(self):
        self.write(self.audit, {"status": "pass", "prepare_manifest_sha256": "wrong"})
        with self.assertRaisesRegex(ValueError, "Audit does not bind"):
            self.execute()
        self.assertFalse(self.calls)

    def test_nonpositive_worker_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "Workers must be positive"):
            self.execute(workers=0)
        self.assertFalse((self.results / "driver").exists())

    def test_smoke_failure_never_starts_full_native(self):
        self.smoke["status"] = "failed"
        self.write(self.smoke_path, self.smoke)
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertFalse(self.calls)
        self.assertEqual(self.checkpoint()["status"], "failed")
        self.assertFalse(self.checkpoint()["child_may_still_be_running"])

    def test_failed_native_stage_prevents_scoring(self):
        class FailedProcess:
            pid = 32100

            def wait(self):
                return 3

        def fail(command, **kwargs):
            self.calls.append(command)
            return FailedProcess()

        with self.assertRaisesRegex(RuntimeError, "exit 3"):
            self.execute(popen=fail)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.checkpoint()["status"], "failed")
        self.assertIsNone(self.checkpoint()["child_pid"])
        self.assertFalse(self.checkpoint()["child_may_still_be_running"])

    def test_failed_scoring_stage_never_publishes_complete(self):
        def fail_second(command, **kwargs):
            process = self.fake_popen(command, **kwargs)
            if len(self.calls) == 2:
                process.wait = lambda: 7
            return process

        with self.assertRaisesRegex(RuntimeError, "exit 7"):
            self.execute(popen=fail_second)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.checkpoint()["status"], "failed")

    def test_provenance_mutation_after_native_blocks_scoring(self):
        def mutate(command, **kwargs):
            process = self.fake_popen(command, **kwargs)
            wait = process.wait

            def changing_wait():
                result = wait()
                self.prep.write_text(self.prep.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                return result

            process.wait = changing_wait
            return process

        with self.assertRaisesRegex(ValueError, "provenance/audit changed"):
            self.execute(popen=mutate)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.checkpoint()["status"], "failed")

    def test_changed_stage_source_blocks_scoring(self):
        actual = module.sha256
        changed = {"active": False}

        def hash_at_time(path):
            if changed["active"] and Path(path).name == "score_author.R":
                return "changed"
            return actual(path)

        def mutate(command, **kwargs):
            process = self.fake_popen(command, **kwargs)
            wait = process.wait

            def changing_wait():
                result = wait()
                changed["active"] = True
                return result

            process.wait = changing_wait
            return process

        with patch.object(module, "sha256", hash_at_time), self.assertRaisesRegex(ValueError, "Frozen stage source changed"):
            self.execute(popen=mutate)
        self.assertEqual(len(self.calls), 1)

    def test_interrupt_retains_live_child_pid_without_claiming_stopped(self):
        class InterruptedProcess:
            pid = 32200

            def wait(self):
                raise KeyboardInterrupt("synthetic interruption")

        with self.assertRaises(KeyboardInterrupt):
            self.execute(popen=lambda *args, **kwargs: InterruptedProcess())
        status = self.checkpoint()
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["child_pid"], 32200)
        self.assertTrue(status["child_may_still_be_running"])

    def test_success_exit_without_completion_files_fails_closed(self):
        def no_comparison(command, **kwargs):
            process = self.fake_popen(command, **kwargs)
            if len(self.calls) == 2:
                process.wait = lambda: 0
            return process

        with self.assertRaises(FileNotFoundError):
            self.execute(popen=no_comparison)
        self.assertEqual(self.checkpoint()["status"], "failed")

    def assert_completion_mutation_rejected(self, mutation, expected):
        def tamper(command, **kwargs):
            process = self.fake_popen(command, **kwargs)
            if len(self.calls) == 2:
                wait = process.wait

                def tampering_wait():
                    result = wait()
                    status_path = self.results / "comparison" / "status.json"
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    if mutation == "incomplete":
                        status["status"] = "scoring"
                    elif mutation == "missing":
                        del status["outputs"]["summary.json"]
                    elif mutation == "hash":
                        status["outputs"]["REPORT.md"]["sha256"] = "wrong"
                    else:
                        status["outputs"]["REPORT.md"]["path"] = str(self.adj)
                    self.write(status_path, status)
                    return result

                process.wait = tampering_wait
            return process

        with self.assertRaisesRegex(RuntimeError, expected):
            self.execute(popen=tamper)
        self.assertEqual(self.checkpoint()["status"], "failed")

    def test_completion_must_declare_complete(self):
        self.assert_completion_mutation_rejected("incomplete", "complete status")

    def test_completion_output_manifest_must_cover_both_files(self):
        self.assert_completion_mutation_rejected("missing", "output manifest is incomplete")

    def test_completion_report_hash_must_match(self):
        self.assert_completion_mutation_rejected("hash", "integrity check")

    def test_completion_report_path_must_match(self):
        self.assert_completion_mutation_rejected("path", "integrity check")


if __name__ == "__main__":
    unittest.main()
