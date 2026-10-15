"""Synthetic orchestration checks; never execute WSL or a real inference job."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_benchmark as runner


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def plan(self):
        return {"out": str(self.root), "sampling": copy.deepcopy(runner.SAMPLING),
                "inputs": {"expression": {"path": str(self.root / "expression.exp")},
                           "hubs": {"path": str(self.root / "hubs.txt")}},
                "component": {"binary": {"path": str(self.root / "sjaracne.exe")},
                              "config_dir": str(self.root / "config")},
                "execution": {"distro": "Ubuntu"}}

    def completed_job(self, plan, arm="legacy", seed=1, stage="raw"):
        directory = runner.job_directory(plan, arm, seed, stage)
        directory.mkdir(parents=True)
        for name in runner.ARTIFACTS:
            (directory / name).write_text("frozen" if name != "validation.json" else '{"status":"passed"}')
        value = {"status": "complete", "arm": arm, "seed": seed, "stage": stage,
                 "plan_sha256": runner.digest(self.root / "plan.json"),
                 "command": runner.native_command(plan, arm, seed, stage), "native_exit_code": 0,
                 "artifacts": {name: runner.record(directory / name) for name in runner.ARTIFACTS}}
        (directory / "job.json").write_text(json.dumps(value))
        return directory, value

    def test_exact_sixty_jobs_and_ten_smoke_jobs(self):
        self.assertEqual(len(runner.jobs_for()), 60)
        self.assertEqual(len(set(runner.jobs_for())), 60)
        smoke = runner.jobs_for(smoke=True)
        self.assertEqual(len(smoke), 10)
        self.assertEqual({(arm, seed) for arm, seed, stage in smoke}, {("legacy", 1), ("u80", 1)})
        self.assertEqual(set(runner.jobs_for()) - set(smoke),
                         {(arm, seed, stage) for seed in (1, 2, 3) for arm in runner.ARMS for stage in runner.STAGES}
                         - set(smoke))

    def test_all_commands_use_full_hubs_and_direct_fresh_mi(self):
        plan = self.plan()
        for arm, seed, stage in runner.jobs_for():
            command = runner.native_command(plan, arm, seed, stage)
            self.assertEqual(command[command.index("-l") + 1], runner.wsl_path(plan["inputs"]["hubs"]["path"]))
            self.assertEqual(command[command.index("-s") + 1], runner.wsl_path(plan["inputs"]["hubs"]["path"]))
            self.assertNotIn("-j", command)
            self.assertNotIn("-c", command)
            self.assertEqual(command[command.index("-N") + 1], "40")
            self.assertEqual(command[command.index("-a") + 1], "adaptive_partitioning")
            self.assertEqual(command[command.index("-n") + 1], "0")
            sampler = runner.SAMPLING[arm]
            self.assertEqual(command[command.index(sampler["flag"]) + 1], sampler["value"])
            self.assertNotIn("-u" if arm == "legacy" else "-r", command)

    def test_stage_thresholds_and_dpi_flags(self):
        plan = self.plan()
        for stage in runner.STAGES:
            command = runner.native_command(plan, "u80", 1, stage)
            self.assertEqual(command[command.index("-e") + 1], "0" if stage.endswith("post") else "1")
            if stage.startswith("nominal"):
                self.assertEqual(command[command.index("-p") + 1], "1e-7")
                self.assertNotIn("-t", command)
            else:
                self.assertEqual(command[command.index("-p") + 1], "1")
                self.assertEqual(float(command[command.index("-t") + 1]), 0 if stage == "raw" else runner.FIXED_MI)

    def test_out_of_protocol_jobs_rejected(self):
        for values in (("other", 1, "raw"), ("u80", 4, "raw"), ("legacy", 1, "other")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                runner.job_directory(self.plan(), *values)

    def test_output_must_be_fresh_child_of_runs(self):
        with patch.object(runner, "REPO", self.root):
            self.assertEqual(runner.fresh_output(self.root / "runs/new"), self.root / "runs/new")
            for path in (self.root, self.root / "runs", self.root / "elsewhere"):
                with self.assertRaises(ValueError):
                    runner.fresh_output(path)
            (self.root / "runs/existing").mkdir(parents=True)
            with self.assertRaises(FileExistsError):
                runner.fresh_output(self.root / "runs/existing")

    def test_atomic_create_never_overwrites(self):
        path = self.root / "value.json"
        runner.write_json(path, {"original": True})
        with self.assertRaises(FileExistsError):
            runner.write_json(path, {"replacement": True})
        self.assertEqual(runner.read_json(path), {"original": True})
        self.assertFalse(list(self.root.glob("*.tmp-*")))

    def test_checkpoint_retries_windows_permission_errors(self):
        path = self.root / "value.json"
        replace = runner.os.replace
        calls = []
        def temporary_busy(source, target):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("busy reader")
            replace(source, target)
        with patch.object(runner.os, "replace", side_effect=temporary_busy), patch.object(runner.time, "sleep"):
            runner.write_json(path, {"status": "ok"}, replace=True, attempts=3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(runner.read_json(path), {"status": "ok"})

    def test_checkpoint_exhaustion_keeps_previous(self):
        path = self.root / "value.json"
        path.write_text("original")
        with patch.object(runner.os, "replace", side_effect=PermissionError("busy")), patch.object(runner.time, "sleep"):
            with self.assertRaises(PermissionError):
                runner.write_json(path, {"new": True}, replace=True, attempts=2)
        self.assertEqual(path.read_text(), "original")
        self.assertFalse(list(self.root.glob("*.tmp-*")))

    def test_frozen_hash_change_is_rejected(self):
        path = self.root / "artifact"
        path.write_text("frozen")
        frozen = runner.record(path)
        path.write_text("changed")
        with self.assertRaises(ValueError):
            runner.verify_record(frozen)

    def test_existing_complete_job_strictly_verified_without_native_run(self):
        plan = self.plan()
        (self.root / "plan.json").write_text("frozen plan")
        _, expected = self.completed_job(plan)
        with patch.object(runner.subprocess, "run") as native:
            actual = runner.run_job(plan, "legacy", 1, "raw")
        self.assertEqual(actual, expected)
        native.assert_not_called()

    def test_wrong_command_or_missing_artifact_is_rejected(self):
        plan = self.plan()
        (self.root / "plan.json").write_text("frozen plan")
        directory, original = self.completed_job(plan)
        for mutate in (lambda p: p.update(command=["wrong"]),
                       lambda p: p.update(plan_sha256="wrong"),
                       lambda p: p["artifacts"].pop("time.tsv"),
                       lambda p: p.update(native_exit_code=1)):
            value = copy.deepcopy(original)
            mutate(value)
            (directory / "job.json").write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.checked_job(plan, "legacy", 1, "raw")

    def test_external_artifact_path_rejected(self):
        plan = self.plan()
        (self.root / "plan.json").write_text("frozen plan")
        directory, value = self.completed_job(plan)
        external = self.root / "elsewhere"
        external.write_text("frozen")
        value["artifacts"]["raw.adj"] = runner.record(external)
        (directory / "job.json").write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "outside"):
            runner.checked_job(plan, "legacy", 1, "raw")

    def test_incomplete_directory_preserved_without_native_run(self):
        plan = self.plan()
        directory = runner.job_directory(plan, "legacy", 1, "raw")
        directory.mkdir(parents=True)
        with patch.object(runner.subprocess, "run") as native, self.assertRaises(FileExistsError):
            runner.run_job(plan, "legacy", 1, "raw")
        self.assertTrue(directory.is_dir())
        native.assert_not_called()

    def test_worker_count_rejected_before_reading_plan(self):
        for workers in (0, 13):
            with self.assertRaises(ValueError):
                runner.run_plan(self.root / "missing.json", workers=workers)

    def test_full_run_requires_smoke_before_native_scheduling(self):
        with patch.object(runner, "verify_plan", return_value=self.plan()), patch.object(runner, "run_job") as native:
            with self.assertRaises(FileNotFoundError):
                runner.run_plan(self.root / "plan.json")
        native.assert_not_called()

    def test_smoke_population_and_lock_cleanup(self):
        plan = self.plan()
        (self.root / "plan.json").write_text("plan")
        calls = []
        def fake_job(p, arm, seed, stage):
            calls.append((arm, seed, stage))
            directory = runner.job_directory(p, arm, seed, stage)
            directory.mkdir(parents=True)
            (directory / "job.json").write_text("{}")
            return {"status": "complete", "arm": arm, "seed": seed, "stage": stage}
        with patch.object(runner, "verify_plan", return_value=plan), patch.object(runner, "run_job", side_effect=fake_job), \
             patch.object(runner, "validate_groups", return_value=[{"status": "passed"}]):
            result = runner.run_plan(self.root / "plan.json", workers=3, smoke=True)
        self.assertEqual(set(calls), set(runner.jobs_for(True)))
        self.assertEqual(result["completed"], 10)
        self.assertEqual(result["status"], "smoke_complete")
        self.assertFalse((self.root / ".run.lock").exists())
        gate = runner.read_json(self.root / "smoke_gate.json")
        self.assertEqual(len(gate["job_records"]), 10)

    def test_failure_never_produces_smoke_gate(self):
        plan = self.plan()
        with patch.object(runner, "verify_plan", return_value=plan), \
             patch.object(runner, "run_job", side_effect=RuntimeError("native failed")):
            with self.assertRaises(RuntimeError):
                runner.run_plan(self.root / "plan.json", workers=2, smoke=True)
        self.assertFalse((self.root / "smoke_gate.json").exists())
        self.assertEqual(runner.read_json(self.root / "status.json")["status"], "failed")
        self.assertFalse((self.root / ".run.lock").exists())

    def test_existing_lock_blocks_second_coordinator(self):
        plan = self.plan()
        lock = self.root / ".run.lock"
        lock.write_text('{"token":"original"}')
        with patch.object(runner, "verify_plan", return_value=plan), self.assertRaises(FileExistsError):
            runner.run_plan(self.root / "plan.json", smoke=True)
        self.assertEqual(runner.read_json(lock)["token"], "original")

    def test_synthetic_plan_freezes_all_runtime_inputs_and_protocol(self):
        repo, prepared, config = self.root / "repo", self.root / "prepared", self.root / "config"
        here = repo / "benchmarks/dream5_network3"
        for directory in (prepared, config, here):
            directory.mkdir(parents=True)
        for name in (*runner.CODE_NAMES, "PLAN_2026-10-15.md"):
            (here / name).write_text("frozen " + name)
        expression, hubs, binary = prepared / "dream5_net3.exp", prepared / "all334_tfs.txt", self.root / "native"
        expression.write_text("frozen expression")
        hubs.write_text("G1\nG2\n")
        binary.write_text("frozen executable")
        source_records = {}
        for index, name in enumerate(runner.SOURCE_SHA256):
            path = self.root / "originals" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("frozen source " + str(index))
            source_records[name] = runner.record(path)
        config_hashes = {}
        for name in runner.CONFIG_SHA256:
            (config / name).write_text("frozen config " + name)
            config_hashes[name] = runner.digest(config / name)
        provenance = {"schema": 1, "status": "prepared", "counts": runner.DATASET,
                      "outputs": {path.name: {key: value for key, value in runner.record(path).items() if key != "path"}
                                  for path in (expression, hubs)}, "source_files": source_records}
        (prepared / "provenance.json").write_text(json.dumps(provenance))
        patches = {"REPO": repo, "HERE": here, "EXPRESSION_SHA256": runner.digest(expression),
                   "HUBS_SHA256": runner.digest(hubs), "BINARY_SHA256": runner.digest(binary),
                   "CONFIG_SHA256": config_hashes,
                   "SOURCE_SHA256": {name: value["sha256"] for name, value in source_records.items()}}
        out = repo / "runs/synthetic"
        with patch.multiple(runner, **patches):
            plan = runner.create_plan(prepared, binary, config, out)
            self.assertEqual(runner.verify_plan(out / "plan.json"), plan)
            self.assertEqual(set(plan["code"]), set(runner.CODE_NAMES))
            self.assertEqual(plan["component"]["source_commit"], runner.ENGINE_COMMIT)
            self.assertEqual(plan["primary"], runner.PRIMARY)
            original = copy.deepcopy(plan)
            for mutate in (lambda p: p["parameters"].update(fixed_mi=.1),
                           lambda p: p["sampling"]["u80"].update(draws=645),
                           lambda p: p.update(seeds=[1]),
                           lambda p: p["primary"].update(endpoint="TP"),
                           lambda p: p["inputs"]["hubs"].update(sha256="changed")):
                changed = copy.deepcopy(original)
                mutate(changed)
                (out / "plan.json").write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    runner.verify_plan(out / "plan.json")
            (out / "plan.json").write_text(json.dumps(original))
            (here / "metrics.py").write_text("changed code")
            with self.assertRaises(ValueError):
                runner.verify_plan(out / "plan.json")

    def test_smoke_gate_requires_stage_comparisons(self):
        plan = self.plan()
        (self.root / "plan.json").write_text("plan")
        gate = {"status": "passed", "plan_sha256": runner.digest(self.root / "plan.json"),
                "job_records": [{"arm": arm, "seed": seed, "stage": stage} for arm, seed, stage in runner.jobs_for(True)]}
        (self.root / "smoke_gate.json").write_text(json.dumps(gate))
        with self.assertRaisesRegex(ValueError, "cross-stage"):
            runner.verify_smoke(plan)


if __name__ == "__main__":
    unittest.main()
