"""Recovery protocol tests using temporary artifacts and no real child processes."""

import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import resume_full_baseline as module
import complete_baseline


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.actual_here = Path(module.__file__).resolve().parent
        self.originals = {name: (self.actual_here / name).read_bytes() for name in
                          ("run_legacy.py", "run_full_baseline.py", "complete_baseline.py", "score_author.R")}
        self.tmp = tempfile.TemporaryDirectory(prefix="resume-helper-test-", dir=self.actual_here)
        self.temp_root = Path(self.tmp.name).resolve()
        self.here = self.temp_root / "stages"
        self.here.mkdir()
        for name in (*self.originals, "resume_full_baseline.py"):
            shutil.copyfile(self.actual_here / name, self.here / name)
        self.root = self.temp_root / "results"
        self.root.mkdir()
        self.assets = self.temp_root / "assets"
        self.assets.mkdir()
        for name in ("r44", "paper_r_library", "micromamba"):
            (self.assets / "toolchain" / name).mkdir(parents=True)
        publication = self.root / "publication"
        publication.mkdir()
        self.score_input = publication / "synthetic_reference.tsv"
        self.score_input.write_text("source\ttarget\nA\tB\n", encoding="utf-8")
        self.prepared = self.root / "prepared"
        self.prepared.mkdir()
        self.expression = self.prepared / "expression.exp"
        self.expression.write_text("probe\tsymbol\ta\tb\tc\nA\tA\t1\t2\t3\nB\tB\t3\t1\t2\n", encoding="utf-8")
        self.hubs = self.prepared / "hubs.txt"
        self.hubs.write_text("A\n", encoding="utf-8")
        self.prep = self.prepared / "prepare_manifest.json"
        self.write(self.prep, {"status": "complete", "outputs": {
            name: module.run_legacy.record_file(self.prepared / name)
            for name in ("expression.exp", "hubs.txt")}})
        self.audit = self.root / "independent_audit.json"
        self.write(self.audit, {"status": "pass", "prepare_manifest_sha256": module.run_legacy.digest(self.prep)})
        native = self.assets / "sources" / "SJARACNe-v0.2.1"
        self.binary = native / "SJARACNe" / "bin" / "sjaracne.exe"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"synthetic pinned native executable")
        self.consensus = self.binary.with_name("create_consensus_network.py")
        self.consensus.write_text("# synthetic pinned consensus\n", encoding="utf-8")
        self.config = native / "SJARACNe" / "config"
        self.config.mkdir()
        (self.config / "config_threshold.txt").write_text("> bcell_mas5\n1.062\t-48.7\t-0.634\n", encoding="utf-8")
        (self.config / "config_kernel.txt").write_text("> bcell_mas5\n0.52477\t-0.24\n", encoding="utf-8")
        self.component = native / "build_record.json"
        self.write(self.component, {
            "source_commit": module.run_legacy.SOURCE_COMMIT,
            "binary_sha256": module.run_legacy.digest(self.binary),
            "consensus_script_sha256": module.run_legacy.digest(self.consensus),
            "config_sha256": {name: module.run_legacy.digest(self.config / name)
                              for name in module.run_legacy.CONFIG_FILES},
        })
        self.legacy = self.root / "legacy"
        (self.legacy / "adj").mkdir(parents=True)
        self.command = [module.sys.executable, str(self.here / "run_legacy.py"), "run",
                        "--expression", str(self.expression), "--hubs", str(self.hubs),
                        "--prepare-manifest", str(self.prep), "--binary", str(self.binary),
                        "--config", str(self.config), "--consensus-script", str(self.consensus),
                        "--component-manifest", str(self.component), "--out", str(self.legacy),
                        "--bootstrap-count", "100", "--workers", "8"]
        args = module.run_legacy.parser().parse_args(self.command[2:])
        frozen, _, _ = module.run_legacy.make_frozen(args)
        self.run = {"frozen": frozen, "bootstraps": {}, "consensus": {}, "status": "incomplete"}
        for seed in range(1, 73):
            adjacency = self.legacy / "adj" / f"bootstrap_{seed:03d}.adj"
            adjacency.write_text("A\tB\t0.7000\n", encoding="utf-8")
            attempt = self.legacy / "attempts" / f"bootstrap_{seed:03d}_001"
            attempt.mkdir(parents=True)
            log = attempt / "native.log"
            log.write_text(f"original completed bootstrap {seed}\n", encoding="utf-8")
            self.run["bootstraps"][str(seed)] = {
                "seed": seed, "status": "complete", "attempt": str(attempt),
                "artifacts": {"adjacency": module.run_legacy.record_file(adjacency),
                              "log": module.run_legacy.record_file(log)},
            }
        self.manifest = self.legacy / "run_manifest.json"
        self.write(self.manifest, self.run)
        driver = self.root / "driver"
        driver.mkdir()
        self.driver_status = driver / "status.json"
        self.old = {
            "status": "native_100_and_consensus", "pid": 21001, "child_pid": 21002,
            "scope": "author-style legacy reconstruction; no PR70/PR71/K; exact author inputs unavailable",
            "workers": 8, "command": self.command,
            "prepare_manifest_sha256": module.run_legacy.digest(self.prep),
            "audit_sha256": module.run_legacy.digest(self.audit),
            "driver_sha256": module.run_legacy.digest(self.here / "run_full_baseline.py"),
            "stage_code_sha256": {name: module.run_legacy.digest(self.here / name)
                                  for name in ("run_legacy.py", "complete_baseline.py", "score_author.R")},
        }
        self.write(self.driver_status, self.old)
        (driver / "native_100_and_consensus.log").write_text("Original attempt evidence\n", encoding="utf-8")
        self.runner_lock = self.legacy / ".runner.lock"
        self.write(self.runner_lock, {"pid": self.old["child_pid"], "started": 123})
        self.lock_bytes = self.runner_lock.read_bytes()
        self.recovery = self.root / "recovery"
        self.calls = []
        self.events = []
        self.native_callback = None
        self.score_callback = None
        self.returncodes = [0, 0]
        self.process_alive_original = module.process_alive
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(module, "__file__", str(self.here / "resume_full_baseline.py")))
        self.alive = self.stack.enter_context(patch.object(module, "process_alive", return_value=False))
        self.wsl = self.stack.enter_context(patch.object(module.subprocess, "run",
                                                       return_value=subprocess.CompletedProcess([], 1, "", "")))
        self.popen = self.stack.enter_context(patch.object(module.subprocess, "Popen", side_effect=self.fake_popen))
        self.score_freeze = self.stack.enter_context(patch.object(
            complete_baseline, "freeze_context", return_value=({"inputs": {
                "reference": module.run_legacy.record_file(self.score_input)}}, None, None)))

    def tearDown(self):
        self.stack.close()
        try:
            for name, original in self.originals.items():
                self.assertEqual((self.actual_here / name).read_bytes(), original,
                                 "Test must never alter an actual frozen stage source")
        finally:
            self.tmp.cleanup()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def checkpoint(self):
        return module.read_json(self.recovery / "status.json")

    def finish_comparison(self):
        comparison = self.root / "comparison"
        comparison.mkdir()
        (comparison / "REPORT.md").write_text("Synthetic comparison\n", encoding="utf-8")
        self.write(comparison / "summary.json", {"exact_reproduction_established": False})
        self.write(comparison / "status.json", {"status": "complete", "outputs": {
            name: module.run_legacy.record_file(comparison / name) for name in ("REPORT.md", "summary.json")}})

    def fake_popen(self, command, *, stdout, stderr):
        self.assertEqual(stderr, module.subprocess.STDOUT)
        self.assertFalse(stdout.closed)
        number = len(self.calls)
        self.assertLess(number, 2, "Unexpected child stage")
        self.calls.append(list(command))
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
                stdout.write("Synthetic stage output\n")
                if number == 0 and owner.native_callback:
                    owner.native_callback(command)
                elif number == 1 and owner.returncodes[1] == 0:
                    owner.finish_comparison()
                    if owner.score_callback:
                        owner.score_callback()
                return owner.returncodes[number]

        return Process()

    def execute(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return module.recover(self.root, self.assets, self.recovery)

    def assert_preflight_rejected(self, exception, message):
        with self.assertRaisesRegex(exception, message):
            self.execute()
        self.popen.assert_not_called()
        self.assertFalse(self.recovery.exists())
        self.assertEqual(self.runner_lock.read_bytes(), self.lock_bytes)

    def test_resume_command_is_exact_original_plus_resume_and_scoring_runs_second(self):
        before = {path: path.read_bytes() for path in (self.root / "driver").iterdir()}
        result = self.execute()
        self.assertEqual(self.calls[0], [*self.command, "--resume"])
        self.assertEqual(self.events, ["start0", "wait0", "start1", "wait1"])
        expected_score = [module.sys.executable, str(self.here / "complete_baseline.py"),
                          "--run-manifest", str(self.manifest), "--prepared-dir", str(self.prepared),
                          "--publication-dir", str(self.root / "publication"), "--audit-file", str(self.audit),
                          "--out", str(self.root / "comparison"),
                          "--wsl-r-env", module.run_legacy.wsl_path(self.assets / "toolchain" / "r44"),
                          "--wsl-r-library", module.run_legacy.wsl_path(self.assets / "toolchain" / "paper_r_library")]
        self.assertEqual(self.calls[1], expected_score)
        self.assertEqual(result["status"], "complete")
        self.assertIsNone(result["child_pid"])
        self.assertEqual(result["completed_at_resume"], list(range(1, 73)))
        self.assertEqual(result["pending_at_resume"], list(range(73, 101)))
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual((self.recovery / "original_driver_status.json").read_bytes(), before[self.driver_status])
        self.assertEqual((self.recovery / "interrupted_run_manifest.json").read_bytes(), self.manifest.read_bytes())
        for name, original in self.originals.items():
            self.assertEqual((self.here / name).read_bytes(), original)

    def test_actual_resume_coordinator_reuses_all_72_verified_jobs(self):
        completed = copy.deepcopy(self.run["bootstraps"])
        original_artifacts = {Path(record["path"]): Path(record["path"]).read_bytes()
                              for item in completed.values() for record in item["artifacts"].values()}
        seeds = []
        cuts = []

        def bootstrap(args, frozen, genes, hubs, seed):
            seeds.append(seed)
            adjacency = args.out / "adj" / f"bootstrap_{seed:03d}.adj"
            adjacency.write_text("A\tB\t0.7000\n", encoding="utf-8")
            return {"seed": seed, "status": "complete", "artifacts": {
                "adjacency": module.run_legacy.record_file(adjacency)}}

        def consensus(args, state, genes, hubs, p):
            cuts.append(p)
            return {"p": p, "status": "complete", "artifacts": {}}

        def native(command):
            args = module.run_legacy.parser().parse_args(command[2:])
            with patch.object(module.run_legacy, "bootstrap_job", side_effect=bootstrap), \
                    patch.object(module.run_legacy, "consensus_job", side_effect=consensus), \
                    contextlib.redirect_stderr(io.StringIO()):
                state = module.run_legacy.execute(args)
            self.assertEqual(state["status"], "complete")

        self.native_callback = native
        self.execute()
        self.assertEqual(sorted(seeds), list(range(73, 101)))
        self.assertEqual(cuts, [0.01, 0.001])
        after = module.read_json(self.manifest)
        self.assertEqual({key: after["bootstraps"][key] for key in completed}, completed)
        self.assertEqual({path: path.read_bytes() for path in original_artifacts}, original_artifacts)
        self.assertFalse(self.runner_lock.exists())

    def test_stale_exact_runner_lock_is_preserved_with_hash(self):
        state = self.execute()
        preserved = self.recovery / "interrupted_runner.lock"
        self.assertFalse(self.runner_lock.exists())
        self.assertEqual(preserved.read_bytes(), self.lock_bytes)
        self.assertEqual(state["stale_lock"]["sha256"], module.run_legacy.digest(preserved))
        self.assertEqual(state["stale_lock"]["path"], str(self.runner_lock))
        self.assertEqual(state["stale_lock"]["preserved_path"], str(preserved))

    def test_live_original_driver_or_child_blocks_without_any_child(self):
        for pid in (self.old["pid"], self.old["child_pid"]):
            with self.subTest(pid=pid):
                self.alive.side_effect = lambda candidate: candidate == pid
                self.assert_preflight_rejected(RuntimeError, "may still be running")
        self.wsl.assert_not_called()

    def test_lock_owner_that_became_live_is_never_moved_or_launched(self):
        self.alive.side_effect = [False, False, True]
        with self.assertRaisesRegex(RuntimeError, "absent original child"):
            self.execute()
        self.popen.assert_not_called()
        self.assertEqual(self.runner_lock.read_bytes(), self.lock_bytes)
        self.assertFalse((self.recovery / "interrupted_runner.lock").exists())
        self.assertEqual(self.checkpoint()["status"], "failed")

    def test_runner_lock_with_different_owner_is_retained(self):
        self.write(self.runner_lock, {"pid": self.old["child_pid"] + 1})
        changed = self.runner_lock.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "absent original child"):
            self.execute()
        self.popen.assert_not_called()
        self.assertEqual(self.runner_lock.read_bytes(), changed)
        self.assertEqual(self.checkpoint()["status"], "failed")

    def test_missing_runner_lock_is_allowed_without_inventing_evidence(self):
        self.runner_lock.unlink()
        self.assertIsNone(self.execute()["stale_lock"])
        self.assertFalse((self.recovery / "interrupted_runner.lock").exists())

    def test_native_nonzero_exit_retains_log_and_prevents_scoring(self):
        self.returncodes[0] = 3
        with self.assertRaisesRegex(RuntimeError, "native_resume_and_consensus failed.*exit 3"):
            self.execute()
        self.assertEqual(len(self.calls), 1)
        status = self.checkpoint()
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["returncode"], 3)
        self.assertIsNone(status["child_pid"])
        self.assertFalse(status["child_may_still_be_running"])
        self.assertIn("Synthetic stage output", (self.recovery / "native_resume_and_consensus.log").read_text())

    def test_scoring_nonzero_exit_is_failed_not_complete(self):
        self.returncodes[1] = 7
        with self.assertRaisesRegex(RuntimeError, "score_and_compare failed.*exit 7"):
            self.execute()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.checkpoint()["status"], "failed")
        self.assertEqual(self.checkpoint()["returncode"], 7)
        self.assertFalse((self.root / "comparison").exists())

    def test_wait_interruption_records_possible_live_child(self):
        self.native_callback = lambda command: (_ for _ in ()).throw(KeyboardInterrupt("synthetic interruption"))
        with self.assertRaises(KeyboardInterrupt):
            self.execute()
        status = self.checkpoint()
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["child_pid"], 31000)
        self.assertTrue(status["child_may_still_be_running"])
        self.assertEqual(len(self.calls), 1)

    def test_all_frozen_original_sources_reject_mutation_before_launch(self):
        for name in self.originals:
            with self.subTest(name=name):
                source = self.here / name
                original = source.read_bytes()
                source.write_bytes(original + b"\n# synthetic mutation\n")
                try:
                    self.assert_preflight_rejected(ValueError, "frozen stage/provenance changed")
                finally:
                    source.write_bytes(original)

    def test_preparation_or_audit_mutation_rejects_before_launch(self):
        for source in (self.prep, self.audit):
            with self.subTest(source=source.name):
                original = source.read_bytes()
                source.write_bytes(original + b"\n")
                try:
                    self.assert_preflight_rejected(ValueError, "frozen stage/provenance changed")
                finally:
                    source.write_bytes(original)

    def test_frozen_input_and_native_component_mutations_reject_before_launch(self):
        for source in (self.expression, self.hubs, self.binary, self.consensus):
            with self.subTest(source=source.name):
                original = source.read_bytes()
                changed = (original.replace(b"A\tA\t1", b"A\tA\t8") if source == self.expression
                           else b"B\n" if source == self.hubs else original + b"\n")
                source.write_bytes(changed)
                try:
                    self.assert_preflight_rejected(ValueError, "(Input not bound|Component hash mismatch)")
                finally:
                    source.write_bytes(original)

    def test_completed_adjacency_or_log_mutation_rejects_before_launch(self):
        for record in self.run["bootstraps"]["1"]["artifacts"].values():
            source = Path(record["path"])
            with self.subTest(source=source.name):
                original = source.read_bytes()
                source.write_bytes(original + b"tamper")
                try:
                    self.assert_preflight_rejected(ValueError, "Completed output changed")
                finally:
                    source.write_bytes(original)

    def test_missing_or_uncheckpointed_adjacency_rejects_before_launch(self):
        extra = self.legacy / "adj" / "bootstrap_073.adj"
        extra.write_text("uncheckpointed", encoding="utf-8")
        self.assert_preflight_rejected(ValueError, "missing or uncheckpointed")
        extra.unlink()
        missing = self.legacy / "adj" / "bootstrap_001.adj"
        missing.unlink()
        self.assert_preflight_rejected(FileNotFoundError, "bootstrap_001")

    def test_changed_command_is_not_accepted_as_frozen_original(self):
        for change in (lambda command: command.append("--resume"),
                       lambda command: command.__setitem__(0, "different-python"),
                       lambda command: command.__setitem__(command.index("--workers") + 1, "4")):
            old = copy.deepcopy(self.old)
            change(old["command"])
            self.write(self.driver_status, old)
            with self.subTest(command=old["command"]):
                self.assert_preflight_rejected(ValueError, "(expected interpreter/stage|eight-worker)")

    def test_different_reconstructed_frozen_manifest_rejects_before_launch(self):
        changed = copy.deepcopy(self.run)
        changed["frozen"]["parameters"]["npar"] = 41
        self.write(self.manifest, changed)
        self.assert_preflight_rejected(ValueError, "differs from the frozen native manifest")

    def test_worker_presence_or_failed_wsl_check_rejects_before_launch(self):
        for returncode, stdout in ((0, "120\n"), (2, ""), (1, "unexpected\n")):
            self.wsl.return_value = subprocess.CompletedProcess([], returncode, stdout, "synthetic diagnostic")
            with self.subTest(returncode=returncode, stdout=stdout):
                self.assert_preflight_rejected(RuntimeError, "worker-absence check failed")
        self.assertEqual(self.wsl.call_args.args[0],
                         ["wsl.exe", "--distribution", "Ubuntu", "--exec", "pgrep", "-x", "sjaracne.exe"])

    def test_existing_comparison_or_recovery_is_never_overwritten(self):
        comparison = self.root / "comparison"
        comparison.mkdir()
        keep = comparison / "keep"
        keep.write_text("retain comparison evidence", encoding="utf-8")
        self.assert_preflight_rejected(FileExistsError, "comparison")
        keep.unlink()
        comparison.rmdir()
        self.recovery.mkdir()
        keep = self.recovery / "keep"
        keep.write_text("retain recovery evidence", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.execute()
        self.popen.assert_not_called()
        self.assertEqual(keep.read_text(), "retain recovery evidence")
        self.assertEqual(self.runner_lock.read_bytes(), self.lock_bytes)

    def test_source_mutation_after_native_blocks_scoring(self):
        def mutate(command):
            source = self.here / "score_author.R"
            source.write_bytes(source.read_bytes() + b"\n# changed during native\n")

        self.native_callback = mutate
        with self.assertRaisesRegex(ValueError, "frozen provenance/stage changed"):
            self.execute()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.checkpoint()["status"], "failed")
        self.assertFalse(self.checkpoint()["child_may_still_be_running"])

    def test_score_context_failure_rejects_before_directory_or_child_creation(self):
        self.score_freeze.side_effect = ValueError("Synthetic scoring context mismatch")
        self.assert_preflight_rejected(ValueError, "scoring context mismatch")

    def test_score_input_mutation_after_native_blocks_scoring(self):
        self.native_callback = lambda command: self.score_input.write_text("changed reference", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "frozen provenance/stage changed"):
            self.execute()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.checkpoint()["status"], "failed")

    def test_wrong_assets_root_or_missing_scoring_toolchain_blocks_before_launch(self):
        other_assets = self.temp_root / "other-assets"
        other_assets.mkdir()
        with self.assertRaisesRegex(ValueError, "Assets root differs"):
            module.recover(self.root, other_assets, self.recovery)
        self.assertFalse(self.recovery.exists())
        self.popen.assert_not_called()
        (self.assets / "toolchain" / "micromamba").rmdir()
        self.assert_preflight_rejected(FileNotFoundError, "micromamba")

    def test_verify_only_reports_72_completed_without_creating_any_output_or_lock(self):
        argv = [str(self.here / "resume_full_baseline.py"), "--result-root", str(self.root),
                "--assets-root", str(self.assets), "--recovery-name", "recovery", "--verify-only"]
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        stdout = io.StringIO()
        with patch.object(module.sys, "argv", argv), contextlib.redirect_stdout(stdout):
            module.main()
        result = json.loads(stdout.getvalue())
        self.assertEqual(result, {"status": "verified", "completed": list(range(1, 73)),
                                  "pending": list(range(73, 101))})
        self.assertEqual({path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}, before)
        self.assertFalse(self.recovery.exists())
        self.assertFalse((self.root / ".baseline_recovery.lock").exists())
        self.popen.assert_not_called()
        self.score_freeze.assert_not_called()

    def test_completion_status_files_hashes_and_paths_fail_closed(self):
        for mutation, exception, message in (
                ("incomplete", RuntimeError, "completed report artifacts"),
                ("missing", RuntimeError, "completed report artifacts"),
                ("hash", ValueError, "output hash mismatch"),
                ("path", ValueError, "output binding mismatch")):
            with self.subTest(mutation=mutation):
                def tamper():
                    path = self.root / "comparison" / "status.json"
                    status = module.read_json(path)
                    if mutation == "incomplete":
                        status["status"] = "scoring"
                    elif mutation == "missing":
                        del status["outputs"]["summary.json"]
                    elif mutation == "hash":
                        status["outputs"]["REPORT.md"]["sha256"] = "changed"
                    else:
                        status["outputs"]["REPORT.md"]["path"] = str(self.expression)
                    self.write(path, status)

                self.score_callback = tamper
                with self.assertRaisesRegex(exception, message):
                    self.execute()
                self.assertEqual(self.checkpoint()["status"], "failed")
                shutil.rmtree(self.recovery)
                shutil.rmtree(self.root / "comparison")
                self.write(self.runner_lock, {"pid": self.old["child_pid"], "started": 123})
                self.calls.clear()

    def test_recovery_lock_excludes_second_coordinator_and_removes_only_owned_lock(self):
        path = self.root / ".baseline_recovery.lock"
        with module.recovery_lock(self.root):
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                with module.recovery_lock(self.root):
                    self.fail("A second coordinator acquired the lock")
            self.assertEqual(path.read_bytes(), original)
        self.assertFalse(path.exists())
        self.popen.assert_not_called()

    def test_windows_process_absence_requires_invalid_parameter_not_access_denied(self):
        kernel = MagicMock()
        kernel.OpenProcess.return_value = None
        with patch.object(module.ctypes, "WinDLL", return_value=kernel, create=True), \
                patch.object(module.ctypes, "get_last_error", return_value=87, create=True):
            self.assertFalse(self.process_alive_original(12345))
            kernel.CloseHandle.assert_not_called()
        with patch.object(module.ctypes, "WinDLL", return_value=kernel, create=True), \
                patch.object(module.ctypes, "get_last_error", return_value=5, create=True), \
                self.assertRaisesRegex(OSError, "Could not establish"):
            self.process_alive_original(12345)

    def test_windows_live_process_handle_is_closed_and_blocks_absence(self):
        kernel = MagicMock()
        kernel.OpenProcess.return_value = 456
        with patch.object(module.ctypes, "WinDLL", return_value=kernel, create=True):
            self.assertTrue(self.process_alive_original(12345))
        kernel.OpenProcess.assert_called_once_with(0x1000, False, 12345)
        kernel.CloseHandle.assert_called_once_with(456)


if __name__ == "__main__":
    unittest.main()
