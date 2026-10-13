"""Tiny synthetic tests of the after-arm postprocessing gate; no inference or R."""

import argparse
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "score_sampling_after", Path(__file__).with_name("score_sampling_after.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class AfterScoringGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="after-scoring-test-")
        self.root = Path(self.temporary.name)
        self.run_root = self.root / "sampling_after_80pct_20261012"
        self.run_root.mkdir()
        (self.run_root / "adj").mkdir()
        self.manifest = self.run_root / "run_manifest.json"
        self.run = {"status": "complete", "bootstraps": {}, "consensus": {}}
        for seed in range(1, 101):
            adj = self.run_root / "adj" / f"bootstrap_{seed:03d}.adj"
            adj.write_text("A\tB\t0.7\n", encoding="utf-8")
            log = self.run_root / f"bootstrap_{seed:03d}.log"
            log.write_text("97 unique observations\n", encoding="utf-8")
            self.run["bootstraps"][str(seed)] = {
                "seed": seed, "status": "complete", "returncode": 0,
                "artifacts": {"adjacency": module.legacy.record_file(adj),
                              "log": module.legacy.record_file(log)}}
        for p in module.completion.PC:
            name = module.legacy.consensus_name(p)
            directory = self.run_root / name
            directory.mkdir()
            edges = directory / "edges.tsv"
            edges.write_text("source\ttarget\tMI\nA\tB\t0.7000\n", encoding="utf-8")
            log = directory / "consensus.log"
            log.write_text("complete\n", encoding="utf-8")
            self.run["consensus"][name] = {
                "p": p, "status": "complete", "returncode": 0,
                "artifacts": {"edges.tsv": module.legacy.record_file(edges),
                              "log": module.legacy.record_file(log)}}
        self.manifest.write_text("{}\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def check(self, run=None):
        return module.verify_checkpoints(self.manifest, self.run if run is None else run)

    def test_accepts_exact_100_hash_bound_checkpoints_and_both_consensuses(self):
        actual = self.check()
        self.assertEqual(set(actual), {0.01, 0.001})
        self.assertEqual(actual[0.01], (self.run_root / "consensus_pc1e-02" / "edges.tsv").resolve())

    def test_rejects_incomplete_top_level_status(self):
        self.run["status"] = "incomplete"
        with self.assertRaisesRegex(ValueError, "must be complete"):
            self.check()

    def test_rejects_live_runner_lock(self):
        (self.run_root / ".runner.lock").write_text("1234\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "still has a lock"):
            self.check()

    def test_rejects_missing_seed(self):
        del self.run["bootstraps"]["100"]
        with self.assertRaisesRegex(ValueError, "exactly 100"):
            self.check()

    def test_rejects_extra_seed(self):
        self.run["bootstraps"]["101"] = copy.deepcopy(self.run["bootstraps"]["100"])
        with self.assertRaisesRegex(ValueError, "exactly 100"):
            self.check()

    def test_rejects_bad_bootstrap_checkpoint(self):
        for key, value in (("status", "failed"), ("seed", 2), ("returncode", 1)):
            with self.subTest(key=key):
                run = copy.deepcopy(self.run)
                run["bootstraps"]["1"][key] = value
                with self.assertRaisesRegex(ValueError, "failed sampling checkpoint"):
                    self.check(run)

    def test_rejects_extra_adjacency_file(self):
        (self.run_root / "adj" / "unexpected.adj").write_text("A\tB\t1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unexpected or missing"):
            self.check()

    def test_rejects_extra_adjacency_directory(self):
        (self.run_root / "adj" / "unexpected-directory").mkdir()
        with self.assertRaisesRegex(ValueError, "Unexpected or missing"):
            self.check()

    def test_rejects_tampered_adjacency(self):
        (self.run_root / "adj" / "bootstrap_001.adj").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
            self.check()

    def test_rejects_tampered_bootstrap_log(self):
        (self.run_root / "bootstrap_001.log").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
            self.check()

    def test_rejects_adjacency_from_another_output(self):
        elsewhere = self.root / "another_run.adj"
        elsewhere.write_text("A\tB\t0.7\n", encoding="utf-8")
        self.run["bootstraps"]["1"]["artifacts"]["adjacency"] = module.legacy.record_file(elsewhere)
        with self.assertRaisesRegex(ValueError, "outside the declared run"):
            self.check()

    def test_rejects_missing_consensus(self):
        del self.run["consensus"][module.legacy.consensus_name(0.001)]
        with self.assertRaisesRegex(ValueError, "both declared"):
            self.check()

    def test_rejects_extra_consensus(self):
        self.run["consensus"]["consensus_pc1e-04"] = {}
        with self.assertRaisesRegex(ValueError, "both declared"):
            self.check()

    def test_rejects_failed_or_inconsistent_consensus(self):
        name = module.legacy.consensus_name(0.01)
        for key, value in (("status", "failed"), ("p", 0.001), ("returncode", 1)):
            with self.subTest(key=key):
                run = copy.deepcopy(self.run)
                run["consensus"][name][key] = value
                with self.assertRaisesRegex(ValueError, "failed sampling consensus"):
                    self.check(run)

    def test_rejects_tampered_consensus_edges(self):
        (self.run_root / module.legacy.consensus_name(0.01) / "edges.tsv").write_text(
            "changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
            self.check()

    def test_rejects_consensus_from_another_run(self):
        other = self.root / "another_edges.tsv"
        other.write_text("source\ttarget\tMI\nA\tB\t0.7000\n", encoding="utf-8")
        name = module.legacy.consensus_name(0.01)
        self.run["consensus"][name]["artifacts"]["edges.tsv"] = module.legacy.record_file(other)
        with self.assertRaisesRegex(ValueError, "outside the declared run"):
            self.check()

    def frozen(self):
        prepared = self.root / "prepared"
        component = self.root / "components"
        baseline = self.root / "legacy"
        return {
            "inputs": {name: {"path": str(prepared / filename)} for name, filename in (
                ("expression", "expression.exp"), ("hubs", "hubs.txt"),
                ("prepare_manifest", "prepare_manifest.json"))},
            "components": {name: {"path": str(component / filename)} for name, filename in (
                ("binary", "bin/sjaracne.exe"), ("config_threshold.txt", "config/config_threshold.txt"),
                ("consensus_script", "bin/create_consensus_network.py"))},
            "component_manifest": {"path": str(component / "build_record.json")},
            "baseline_binding": {"records": {"run_manifest": {"path": str(baseline / "run_manifest.json")},
                                               "summary": {"path": str(self.root / "comparison/summary.json")}}},
            "gate_binding": {"record": {"path": str(self.root / "acceptance.json")}},
            "execution": {"consensus_python": "C:/fixture/Python/python.exe",
                          "wsl_distro": "Ubuntu-fixture", "consensus_wsl": False}}

    def test_native_arguments_preserve_frozen_paths_and_execution(self):
        frozen = self.frozen()
        args = module.native_arguments(self.manifest, frozen)
        expected = {
            "expression": frozen["inputs"]["expression"]["path"],
            "hubs": frozen["inputs"]["hubs"]["path"],
            "prepare_manifest": frozen["inputs"]["prepare_manifest"]["path"],
            "out": str(self.manifest.parent),
            "binary": frozen["components"]["binary"]["path"],
            "config": str(module.completion.local_path(frozen["components"]["config_threshold.txt"]["path"]).parent),
            "consensus_script": frozen["components"]["consensus_script"]["path"],
            "component_manifest": frozen["component_manifest"]["path"],
            "baseline_run_manifest": frozen["baseline_binding"]["records"]["run_manifest"]["path"],
            "baseline_summary": frozen["baseline_binding"]["records"]["summary"]["path"],
            "gate_decision": frozen["gate_binding"]["record"]["path"]}
        for name, path in expected.items():
            self.assertEqual(getattr(args, name), module.completion.local_path(path))
        self.assertEqual(args.action, "run")
        self.assertTrue(args.resume)
        self.assertEqual(args.workers, 1)
        self.assertEqual(args.python, frozen["execution"]["consensus_python"])
        self.assertEqual(args.wsl_distro, "Ubuntu-fixture")
        self.assertFalse(args.consensus_wsl)
        self.assertEqual(args.subsample_percent, 80)
        self.assertEqual(args.bootstrap_count, 100)
        self.assertEqual(args.bootstrap_p, 1e-7)
        self.assertEqual(args.consensus_p, [0.01, 0.001])
        self.assertEqual(args.npar, 40)

    def test_native_arguments_preserve_consensus_wsl(self):
        frozen = self.frozen()
        frozen["execution"]["consensus_wsl"] = True
        self.assertTrue(module.native_arguments(self.manifest, frozen).consensus_wsl)

    def test_r_command_preserves_linux_environment_and_library_on_windows(self):
        args = argparse.Namespace(wsl_r_env="/home/fixture/r-env", wsl_r_library="/home/fixture/R/library",
                                  wsl_micromamba="/opt/fixture/micromamba", wsl_distro="Ubuntu-fixture")
        paths = [self.root / "input.json", self.root / "output"]
        converted = [module.legacy.wsl_path(module.CODE / "score_eligible_epr.R"),
                     *[module.legacy.wsl_path(path) for path in paths]]
        with patch.object(module.os, "name", "nt"):
            command = module.r_command(args, "score_eligible_epr.R", paths)
        self.assertEqual(command, ["wsl.exe", "-d", "Ubuntu-fixture", "--", "/opt/fixture/micromamba",
                                   "run", "--prefix", "/home/fixture/r-env", "env",
                                   "R_LIBS_USER=/home/fixture/R/library", "Rscript", *converted])

    def test_r_command_default_micromamba_is_linux_env_sibling(self):
        args = argparse.Namespace(wsl_r_env="/home/fixture/r-env", wsl_r_library=None,
                                  wsl_micromamba=None, wsl_distro="Ubuntu-fixture")
        with patch.object(module.os, "name", "nt"):
            command = module.r_command(args, "score_eligible_epr.R", [])
        self.assertEqual(command[4], "/home/fixture/micromamba")
        self.assertNotIn("env", command)

    def test_r_command_without_windows_does_not_add_wsl_prefix(self):
        args = argparse.Namespace(wsl_r_env="/home/fixture/r-env", wsl_r_library=None,
                                  wsl_micromamba="/opt/fixture/micromamba", wsl_distro="Ubuntu-fixture")
        converted = "/mnt/d/fixture/score_eligible_epr.R"
        with patch.object(module.os, "name", "posix"), patch.object(module.legacy, "wsl_path", return_value=converted):
            command = module.r_command(args, "score_eligible_epr.R", [])
        self.assertEqual(command, ["/opt/fixture/micromamba", "run", "--prefix", "/home/fixture/r-env", "Rscript", converted])

    def test_linux_argument_retains_literal_linux_path(self):
        self.assertEqual(module.completion.linux_argument("/home/fixture/r-env"), "/home/fixture/r-env")
        self.assertEqual(module.completion.linux_argument("/opt/micromamba"), "/opt/micromamba")

    def test_existing_output_refused_before_any_native_or_subprocess_execution(self):
        output = self.root / "existing_scoring"
        output.mkdir()
        args = argparse.Namespace(result_root=self.root, out=output)
        with patch.object(module.sampling, "execute") as native_execute, \
             patch.object(module.sampling, "make_frozen") as native_preflight, \
             patch.object(module.subprocess, "run") as subprocess_run:
            with self.assertRaisesRegex(FileExistsError, "must be fresh"):
                module.execute(args)
        native_execute.assert_not_called()
        native_preflight.assert_not_called()
        subprocess_run.assert_not_called()

    def test_baseline_validate_native_still_rejects_changed_sampling_protocol(self):
        run = {"frozen": {"source_commit": module.legacy.SOURCE_COMMIT, "parameters": {
            "bootstrap_count": 100, "seeds": list(range(1, 101)), "bootstrap_p": 1e-7,
            "consensus_p": [0.01, 0.001], "npar": 40, "dpi_tolerance": 0,
            "sampling": "80% without replacement", "algorithm": "adaptive_partitioning",
            "explicit_mi_override": None}}}
        args = argparse.Namespace(run_manifest=self.root / "legacy/run_manifest.json", prepared_dir=self.root / "prepared")
        with self.assertRaisesRegex(ValueError, "100-bootstrap legacy protocol"):
            module.completion.validate_native(args, run)

    def test_baseline_validate_native_still_rejects_wrong_source_commit(self):
        args = argparse.Namespace(run_manifest=self.root / "legacy/run_manifest.json", prepared_dir=self.root / "prepared")
        with self.assertRaisesRegex(ValueError, "paper-era 0.2.1 baseline"):
            module.completion.validate_native(args, {"frozen": {"source_commit": "wrong", "parameters": {}}})


if __name__ == "__main__":
    unittest.main()
