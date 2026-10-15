"""Offline extension orchestration tests; no native jobs or real input changes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import extend_pilot as module


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def record(path):
        return module.pilot.record(path)

    def plan(self):
        artifact = self.root / "frozen.txt"
        artifact.write_text("frozen")
        record = self.record(artifact)
        inputs = {key: record for key in ("expression", "full_sig_hubs", "prepare_manifest", "gene_selection", "eligible_sources", "positive_edges")}
        component = {"binary": record, "historical_run": record, "build_record": record,
                     "config": {"config_threshold.txt": record, "config_kernel.txt": record}}
        return {"inputs": inputs, "components": {arm: component for arm in module.pilot.ARMS},
                "parameters": {"ks": [1000, 5000]}, "source_scope": "eligible",
                "evaluated_source_count": 272, "evaluated_sources": record, "labels": record,
                "universe": {"candidate_pairs": 4, "reference_positive_pairs": 2,
                             "reference_negative_pairs": 2, "random_positive_fraction": .5},
                "execution": {"wsl_distro": "Ubuntu"}, "out": str(self.root)}

    def test_signature_ignores_only_output_paths_and_seed_population(self):
        original = self.plan()
        changed = copy.deepcopy(original)
        changed["out"] = "different"
        changed["seeds"] = list(range(1, 101))
        for value in changed["inputs"].values():
            value["path"] = "another-location"
        self.assertEqual(module.protocol_signature(original), module.protocol_signature(changed))
        changed["parameters"]["ks"] = [5000]
        self.assertNotEqual(module.protocol_signature(original), module.protocol_signature(changed))

    def test_signature_rejects_changed_data_sampling_or_scope(self):
        original = self.plan()
        for mutate in (lambda p: p["labels"].update(sha256="changed"),
                       lambda p: p.update(source_scope="full"),
                       lambda p: p["components"]["after"]["binary"].update(sha256="changed"),
                       lambda p: p["execution"].update(wsl_distro="Other")):
            changed = copy.deepcopy(original)
            mutate(changed)
            self.assertNotEqual(module.protocol_signature(original), module.protocol_signature(changed))

    def test_checkpoint_retries_permission_error_without_orphan_files(self):
        path = self.root / "status.json"
        real_replace = module.os.replace
        calls = []
        def replace(source, target):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("reader handle")
            real_replace(source, target)
        with patch.object(module.os, "replace", side_effect=replace), patch.object(module.time, "sleep"):
            module.write_checkpoint(path, {"status": "complete"}, attempts=3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(json.loads(path.read_text()), {"status": "complete"})
        self.assertEqual(list(self.root.glob("*.tmp-*")), [])

    def test_checkpoint_exhaustion_preserves_old_and_removes_temp(self):
        path = self.root / "status.json"
        path.write_text("original")
        with patch.object(module.os, "replace", side_effect=PermissionError("locked")), patch.object(module.time, "sleep"):
            with self.assertRaises(PermissionError):
                module.write_checkpoint(path, {"status": "complete"}, attempts=2)
        self.assertEqual(path.read_text(), "original")
        self.assertEqual(list(self.root.glob("*.tmp-*")), [])

    def test_prepared_binding_rejects_changed_reference_hash(self):
        plan = self.plan()
        outputs = {name: {"sha256": plan["inputs"]["expression"]["sha256"]} for name in
                   ("expression.exp", "hubs.txt", "gene_selection.tsv", "reference_eligible_sources.tsv", "reference_positive_edges.tsv")}
        with patch.object(module.pilot, "read_json", return_value={"outputs": outputs}):
            module.check_prepared_binding(plan)
            outputs["reference_positive_edges.tsv"]["sha256"] = "changed"
            with self.assertRaises(ValueError):
                module.check_prepared_binding(plan)

    def test_checked_job_rejects_wrong_command_or_artifact_population(self):
        plan = self.plan()
        directory = self.root / "jobs/before/seed_002"
        directory.mkdir(parents=True)
        job = {"status": "complete", "arm": "before", "seed": 2, "command": ["wrong"], "artifacts": {}}
        (directory / "job.json").write_text(json.dumps(job))
        with patch.object(module.pilot, "native_command", return_value=["expected"]):
            with self.assertRaisesRegex(ValueError, "command"):
                module.checked_job(plan, "before", 2)
            job["command"] = ["expected"]
            (directory / "job.json").write_text(json.dumps(job))
            with self.assertRaisesRegex(ValueError, "six"):
                module.checked_job(plan, "before", 2)

    def test_checked_job_rejects_external_artifact_paths(self):
        plan = self.plan()
        directory = self.root / "jobs/before/seed_002"
        directory.mkdir(parents=True)
        job = {"status": "complete", "arm": "before", "seed": 2, "command": ["expected"],
               "artifacts": {name: self.record(self.root / "frozen.txt") for name in module.ARTIFACTS}}
        (directory / "job.json").write_text(json.dumps(job))
        with patch.object(module.pilot, "native_command", return_value=["expected"]):
            with self.assertRaisesRegex(ValueError, "path"):
                module.checked_job(plan, "before", 2)

    def test_run_schedules_only_160_nonreused_jobs(self):
        plan = self.plan()
        plan["seeds"] = list(range(1, 101))
        plan["universe"]["definition_sha256"] = "same"
        reused = [{"arm": arm, "seed": seed} for seed in range(1, 21) for arm in module.pilot.ARMS]
        extension = {"reused_jobs": reused}
        old = copy.deepcopy(plan)
        class Universe:
            definition_sha256 = "same"
        calls = []
        def run_job(p, u, arm, seed):
            calls.append((arm, seed))
            return {"arm": arm, "seed": seed, "status": "complete"}
        with patch.object(module, "verify_extension", return_value=(plan, extension, old)), \
             patch.object(module, "_reused_results", return_value=reused), \
             patch.object(module.score, "load_universe", return_value=Universe()), \
             patch.object(module.pilot, "run_job", side_effect=run_job), \
             patch.object(module.pilot, "record", return_value={"sha256": "synthetic"}):
            result = module.run_extension(self.root / "plan.json", workers=3)
        self.assertEqual(len(calls), 160)
        self.assertEqual(set(calls), {(arm, seed) for seed in range(21, 101) for arm in module.pilot.ARMS})
        self.assertEqual(result["completed"], 200)
        self.assertFalse((self.root / ".run.lock").exists())

    def test_lock_blocks_duplicate_coordinator(self):
        plan = self.plan()
        (self.root / ".run.lock").write_text("{}")
        with patch.object(module, "verify_extension", return_value=(plan, {}, {})):
            with self.assertRaises(FileExistsError):
                module.run_extension(self.root / "plan.json")

    def test_resume_uses_strict_checker_instead_of_legacy_cached_branch(self):
        plan = self.plan()
        complete = self.root / "jobs/before/seed_002/job.json"
        complete.parent.mkdir(parents=True)
        complete.write_text("{}")
        expected = {"status": "complete", "arm": "before", "seed": 2}
        with patch.object(module, "checked_job", return_value=(complete, expected)) as checker, \
             patch.object(module.pilot, "run_job") as native:
            actual = module.run_or_verify_job(plan, object(), "before", 2)
        self.assertEqual(actual, expected)
        checker.assert_called_once_with(plan, "before", 2)
        native.assert_not_called()

    def test_fresh_job_delegates_to_unchanged_native_runner(self):
        plan = self.plan()
        universe = object()
        with patch.object(module.pilot, "run_job", return_value={"status": "complete"}) as native, \
             patch.object(module, "checked_job") as checker:
            module.run_or_verify_job(plan, universe, "before", 2)
        native.assert_called_once_with(plan, universe, "before", 2)
        checker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
