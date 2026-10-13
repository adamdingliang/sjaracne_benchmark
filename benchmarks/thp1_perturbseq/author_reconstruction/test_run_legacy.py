"""Small mocked protocol tests; no public-data/native benchmark is launched."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("run_legacy", Path(__file__).with_name("run_legacy.py"))
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)


class LegacyRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.expression = self.root / "expression.exp"
        self.expression.write_text("isoformId\tgeneSymbol\ta\tb\tc\nA\tA\t1\t2\t3\nB\tB\t3\t1\t2\nC\tC\t2\t3\t1\n")
        self.hubs = self.root / "hubs.txt"
        self.hubs.write_text("A\nB\n")
        self.binary = self.root / "native"
        self.binary.write_bytes(b"pinned mock binary")
        self.consensus = self.root / "create_consensus_network.py"
        self.consensus.write_text("# pinned mock original\n")
        self.config = self.root / "config"
        self.config.mkdir()
        (self.config / "config_threshold.txt").write_text("> bcell_mas5\n1.062\t-48.7\t-0.634\n")
        (self.config / "config_kernel.txt").write_text("> bcell_mas5\n0.52477\t-0.24\n")
        self.components = self.root / "build_record.json"
        self.components.write_text(json.dumps({
            "source_commit": legacy.SOURCE_COMMIT,
            "binary_sha256": legacy.digest(self.binary),
            "consensus_script_sha256": legacy.digest(self.consensus),
            "config_sha256": {name: legacy.digest(self.config / name) for name in legacy.CONFIG_FILES},
            "compiler": "mock", "build_command": "mock", "adaptations": [],
        }))
        self.out = self.root / "result"
        self.args = legacy.parser().parse_args([
            "run", "--expression", str(self.expression), "--hubs", str(self.hubs),
            "--out", str(self.out), "--binary", str(self.binary), "--config", str(self.config),
            "--consensus-script", str(self.consensus), "--component-manifest", str(self.components),
            "--bootstrap-count", "2", "--workers", "1",
        ])
        self.commands = []

    def tearDown(self):
        self.temporary.cleanup()

    def fake_run(self, command, stdout, stderr, check):
        self.commands.append(command)
        if "-r" in command:
            output = Path(command[command.index("-o") + 1])
            cutoff = legacy.affine_cutoff(self.config, 3, self.args.bootstrap_p)
            output.write_text(f">  MI threshold    {cutoff:.6g}\n>  MI P-value      1e-07\n"
                              ">  DPI tolerance   0\nA\tB\t0.7\tC\t0.8\nB\tA\t0.7\n")
            stdout.write("Marker No: 3 (3 active), Array No: 3\n")
        else:
            output = Path(command[command.index("-o") + 1])
            output.mkdir()
            (output / "consensus_network_3col_.txt").write_text("source\ttarget\tMI\nA\tB\t0.7000\nA\tC\t0.8000\n")
            (output / "consensus_network_ncol_.txt").write_text(
                "source\ttarget\tsource.symbol\ttarget.symbol\tMI\tpearson\tspearman\tslope\tp-value\n"
                "A\tB\tA\tB\t0.7000\t0\t0\t0\t1\nA\tC\tA\tC\t0.8000\t0\t0\t0\t1\n")
            (output / "bootstrap_info_.txt").write_text("Total edge tested: 3\n")
            (output / "parameter_info_.txt").write_text(">  Bootstrap No: 2\n")
            stdout.write("original consensus finished\n")
        return subprocess.CompletedProcess(command, 0)

    def run_mocked(self):
        # Tests are native-host command tests even when executed on Windows.
        with patch.object(legacy, "PLATFORM", "posix"), patch.object(legacy.subprocess, "run", self.fake_run):
            return legacy.execute(self.args)

    def test_default_plan_100_seeds_and_original_rules(self):
        self.args.bootstrap_count = 100
        self.args.action = "plan"
        state = self.run_mocked()
        commands = state["bootstrap_commands"]
        self.assertEqual(len(commands), 100)
        self.assertEqual(commands[0][commands[0].index("-S") + 1], "1")
        self.assertEqual(commands[-1][commands[-1].index("-S") + 1], "100")
        for command in commands:
            self.assertEqual(command[command.index("-r") + 1], "1")
            self.assertEqual(command[command.index("-N") + 1], "40")
            self.assertNotIn("-t", command)
            self.assertNotIn("-u", command)
            self.assertNotIn("-M", command)
        self.assertFalse(self.out.exists())

    def test_complete_end_to_end_exact_consensus_order(self):
        state = self.run_mocked()
        self.assertEqual(state["status"], "complete")
        self.assertEqual(len(state["bootstraps"]), 2)
        self.assertEqual(len(state["consensus"]), 2)
        self.assertEqual(len(self.commands), 4)
        for p in (0.01, 0.001):
            directory = self.out / legacy.consensus_name(p)
            self.assertEqual((directory / "edges.tsv").read_bytes(),
                             (directory / "consensus_network_3col_.txt").read_bytes())
            self.assertIn("A\tB\t0.7000\nA\tC\t0.8000", (directory / "edges.tsv").read_text())
        consensus = [command for command in self.commands if "-r" not in command]
        self.assertEqual([command[command.index("-a") + 1] for command in consensus],
                         [str(self.out / "adj")] * 2)
        self.assertFalse((self.out / ".runner.lock").exists())

    def test_resume_skips_verified_complete_jobs(self):
        self.run_mocked()
        self.args.resume = True
        self.args.workers = 3
        state = self.run_mocked()
        self.assertEqual(len(self.commands), 4)
        self.assertEqual(state["status"], "complete")

    def prepared_manifest(self, status):
        output_key = "outputs" if status == "complete" else "files"
        path = self.root / "prepare_manifest.json"
        path.write_text(json.dumps({"status": status, output_key: {
            "expression.exp": {"sha256": legacy.digest(self.expression)},
            "hubs.txt": {"sha256": legacy.digest(self.hubs)},
        }}))
        self.args.prepare_manifest = path
        return path

    def test_complete_preparation_binds_expression_and_hubs(self):
        path = self.prepared_manifest("complete")
        self.args.action = "plan"
        state = self.run_mocked()
        binding = state["frozen"]["preparation_binding"]
        self.assertEqual(binding["status"], "complete")
        self.assertEqual(binding["manifest"]["sha256"], legacy.digest(path))
        self.assertEqual(binding["expression"]["path"], str(self.expression.resolve()))

    def test_ready_preparation_binds_actual_inputs(self):
        self.prepared_manifest("inference_inputs_ready")
        self.args.action = "plan"
        state = self.run_mocked()
        self.assertEqual(state["frozen"]["preparation_binding"]["status"], "inference_inputs_ready")

    def test_mismatched_prepared_expression_rejected(self):
        self.prepared_manifest("complete")
        self.expression.write_text(self.expression.read_text().replace("A\tA\t1", "A\tA\t8"))
        with self.assertRaisesRegex(ValueError, "prepared artifact: expression.exp"):
            self.run_mocked()

    def test_mismatched_prepared_hubs_rejected(self):
        self.prepared_manifest("inference_inputs_ready")
        self.hubs.write_text("A\n")
        with self.assertRaisesRegex(ValueError, "prepared artifact: hubs.txt"):
            self.run_mocked()

    def test_partial_preparation_manifest_rejected(self):
        path = self.prepared_manifest("started")
        with self.assertRaisesRegex(ValueError, "complete or inference_inputs_ready"):
            self.run_mocked()
        record = json.loads(path.read_text())
        record["status"] = "complete"
        record["outputs"] = {}
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "prepared artifact: expression.exp"):
            self.run_mocked()

    def test_existing_run_requires_resume(self):
        self.run_mocked()
        with self.assertRaises(FileExistsError):
            self.run_mocked()

    def test_resume_rejects_parameter_change(self):
        self.run_mocked()
        self.args.resume = True
        self.args.bootstrap_p = 0.001
        with self.assertRaisesRegex(ValueError, "differs from frozen"):
            self.run_mocked()

    def test_resume_rejects_expression_change(self):
        self.run_mocked()
        self.args.resume = True
        self.expression.write_text(self.expression.read_text().replace("A\tA\t1", "A\tA\t9"))
        with self.assertRaisesRegex(ValueError, "differs from frozen"):
            self.run_mocked()

    def test_resume_rejects_output_tamper(self):
        self.run_mocked()
        self.args.resume = True
        (self.out / "adj" / "bootstrap_001.adj").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Completed output changed"):
            self.run_mocked()

    def test_component_hash_and_commit_checked(self):
        self.binary.write_bytes(b"not pinned")
        with self.assertRaisesRegex(ValueError, "Component hash mismatch: binary"):
            self.run_mocked()
        record = json.loads(self.components.read_text())
        record["source_commit"] = "e59973a1891672a14f06d7847545c53368f3066c"
        self.components.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "version 0.2.1"):
            self.run_mocked()

    def test_legacy_header_labels_are_positional(self):
        self.expression.write_text(self.expression.read_text().replace("isoformId\tgeneSymbol", "gene\tlabel"))
        self.args.action = "plan"
        state = self.run_mocked()
        self.assertEqual(state["frozen"]["observations"], 3)

    def test_exclusive_publish_keeps_existing_target(self):
        temporary, target = self.root / "temporary", self.root / "target"
        temporary.write_text("new")
        target.write_text("old")
        with self.assertRaises(FileExistsError):
            legacy.publish_file(temporary, target)
        self.assertEqual(target.read_text(), "old")

    def test_uncheckpointed_adjacency_blocks_all_jobs(self):
        (self.out / "adj").mkdir(parents=True)
        orphan = self.out / "adj" / "bootstrap_001.adj"
        orphan.write_text("must preserve")
        with self.assertRaisesRegex(FileExistsError, "Uncheckpointed output"):
            self.run_mocked()
        self.assertEqual(orphan.read_text(), "must preserve")
        self.assertFalse(self.commands)

    def test_uncheckpointed_consensus_blocks_overwrite(self):
        self.args.action = "bootstrap"
        self.run_mocked()
        target = self.out / "consensus_pc1e-02"
        target.mkdir()
        (target / "edges.tsv").write_text("must preserve")
        self.args.resume = True
        self.args.action = "consensus"
        with self.assertRaisesRegex(FileExistsError, "Uncheckpointed consensus"):
            self.run_mocked()
        self.assertEqual((target / "edges.tsv").read_text(), "must preserve")

    def test_windows_native_and_wsl_consensus_command(self):
        with patch.object(legacy, "PLATFORM", "nt"):
            command = legacy.native_command(self.args, 9, self.out / "native.adj")
            self.assertEqual(command[:4], ["wsl.exe", "-d", "Ubuntu", "--"])
            self.assertTrue(command[4].startswith("/mnt/"))
            self.args.consensus_wsl = True
            self.args.python = "/usr/bin/python3"
            command = legacy.consensus_command(self.args, 0.01, self.out / "consensus")
            self.assertEqual(command[:5], ["wsl.exe", "-d", "Ubuntu", "--", "/usr/bin/python3"])
            self.assertTrue(command[5].startswith("/mnt/"))

    def test_failed_native_attempt_retained_and_resume_retries(self):
        good_run = self.fake_run
        first = True
        def failing(command, **kwargs):
            nonlocal first
            if first:
                first = False
                output = Path(command[command.index("-o") + 1])
                output.write_text("partial output")
                kwargs["stdout"].write("failed attempt\n")
                return subprocess.CompletedProcess(command, 2)
            return good_run(command, **kwargs)
        with patch.object(legacy, "PLATFORM", "posix"), patch.object(legacy.subprocess, "run", failing):
            with self.assertRaisesRegex(RuntimeError, "bootstraps failed"):
                legacy.execute(self.args)
        partial = self.out / "attempts" / "bootstrap_001_001" / "bootstrap_001.adj"
        self.assertEqual(partial.read_text(), "partial output")
        self.args.resume = True
        state = self.run_mocked()
        self.assertEqual(state["status"], "complete")
        self.assertEqual(partial.read_text(), "partial output")
        self.assertTrue((self.out / "attempts" / "bootstrap_001_002").is_dir())

    def test_extra_adj_file_rejected_before_consensus(self):
        self.args.action = "bootstrap"
        self.run_mocked()
        (self.out / "adj" / "unexpected.txt").write_text("not adjacency")
        self.args.action = "consensus"
        self.args.resume = True
        with self.assertRaisesRegex(ValueError, "exact completed bootstrap set"):
            self.run_mocked()

    def test_empty_consensus_is_valid(self):
        directory = self.root / "empty"
        directory.mkdir()
        (directory / legacy.CONSENSUS_FILES[0]).write_text("source\ttarget\tMI\n")
        (directory / legacy.CONSENSUS_FILES[1]).write_text("source\ttarget\tsource.symbol\ttarget.symbol\tMI\n")
        for name in legacy.CONSENSUS_FILES[2:]:
            (directory / name).write_text("information")
        self.assertEqual(legacy.validate_consensus(directory, {"A", "B"}, {"A"})["edges"], 0)

    def test_native_threshold_and_draw_count_validated(self):
        frozen, genes, hubs = legacy.make_frozen(self.args)
        adjacency, log = self.root / "wrong.adj", self.root / "wrong.log"
        adjacency.write_text("> MI threshold 0.00001\n> MI P-value 1e-7\n> DPI tolerance 0\nA\tB\t0.9\n")
        log.write_text("Array No: 3\n")
        with self.assertRaisesRegex(ValueError, "MI threshold"):
            legacy.validate_adjacency(adjacency, genes, hubs, frozen, log)

    def test_stage_change_detected_and_checkpointed_failed(self):
        good_run = self.fake_run
        changed = False
        def mutate(command, **kwargs):
            nonlocal changed
            result = good_run(command, **kwargs)
            if not changed:
                changed = True
                self.consensus.write_text("changed script")
            return result
        with patch.object(legacy, "PLATFORM", "posix"), patch.object(legacy.subprocess, "run", mutate):
            with self.assertRaises(RuntimeError):
                legacy.execute(self.args)
        manifest = json.loads((self.out / "run_manifest.json").read_text())
        self.assertEqual(manifest["bootstraps"]["1"]["status"], "failed")
        self.assertIn("Frozen input/component changed", manifest["bootstraps"]["1"]["error"])
        self.assertFalse((self.out / "adj" / "bootstrap_001.adj").exists())

    def test_lock_blocks_concurrent_run(self):
        self.out.mkdir()
        (self.out / ".runner.lock").write_text("another owner")
        with self.assertRaises(FileExistsError):
            self.run_mocked()
        self.assertEqual((self.out / ".runner.lock").read_text(), "another owner")


if __name__ == "__main__":
    unittest.main()
