"""Synthetic auto-completion tests; no actual native jobs or R scoring."""

import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import complete_baseline as module


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.prepared = self.root / "prepared"
        self.prepared.mkdir()
        for name, content in (("expression.exp", "expression"), ("hubs.txt", "A\n"),
                              ("reference_positive_edges.tsv", "source\ttarget\teffect\nA\tB\t1\n")):
            (self.prepared / name).write_text(content)
        self.prepare_path = self.prepared / "prepare_manifest.json"
        self.prepared_hashes = {path.name: module.legacy.digest(path) for path in self.prepared.iterdir()}
        self.write(self.prepare_path, {"status": "complete", "outputs": {
            name: {"sha256": value} for name, value in self.prepared_hashes.items()}})
        self.audit = self.root / "audit.json"
        self.write(self.audit, {"status": "pass", "prepare_manifest_sha256": module.legacy.digest(self.prepare_path),
                               "prepared_files_sha256": self.prepared_hashes})
        self.pub = self.root / "publication"
        self.pub.mkdir()
        (self.pub / "tp.tsv").write_text("k\tTP\tmethod\n1000\t1\tscMINER\n1000\t2\tRandom\n5000\t54\tscMINER\n5000\t5\tRandom\n10000\t80\tscMINER\n10000\t10\tRandom\n")
        (self.pub / "epr.tsv").write_text("k\tEPR\n1000\t0.5\n5000\t10.8\n10000\t8\n")
        (self.pub / "roc_segment.tsv").write_text("FPR\tTPR\tmethod\n0.8\t0.95\tscMINER\n1\t1\tscMINER\n")
        self.write(self.pub / "manifest.json", {"full_ROC_available": False, "published_AUROC_rounded": .75,
                    "outputs_sha256": {name: module.legacy.digest(self.pub / name) for name in ("tp.tsv", "epr.tsv", "roc_segment.tsv")}})
        self.native = self.root / "native"
        (self.native / "adj").mkdir(parents=True)
        self.run_path = self.native / "run_manifest.json"
        component = self.root / "component"
        component.write_text("pinned component")
        inputs = {key: module.legacy.record_file(self.prepared / name) for key, name in (
            ("expression", "expression.exp"), ("hubs", "hubs.txt"), ("prepare_manifest", "prepare_manifest.json"))}
        bootstraps = {}
        for seed in range(1, 101):
            adjacency = self.native / "adj" / f"bootstrap_{seed:03d}.adj"
            adjacency.write_text("A\tB\t0.2\n")
            bootstraps[str(seed)] = {"seed": seed, "status": "complete", "artifacts": {"adjacency": module.legacy.record_file(adjacency)}}
        consensus = {}
        for p in module.PC:
            directory = self.native / module.legacy.consensus_name(p)
            directory.mkdir()
            network = directory / "edges.tsv"
            network.write_text("source\ttarget\tMI\nA\tB\t0.2\n")
            consensus[module.legacy.consensus_name(p)] = {"status": "complete", "p": p,
                "artifacts": {"edges.tsv": module.legacy.record_file(network)}}
        self.run = {"status": "complete", "frozen": {
            "source_commit": module.legacy.SOURCE_COMMIT,
            "parameters": {"bootstrap_count": 100, "seeds": list(range(1, 101)), "bootstrap_p": 1e-7,
                           "consensus_p": list(module.PC), "npar": 40, "dpi_tolerance": 0,
                           "sampling": "legacy -r 1", "algorithm": "adaptive_partitioning", "explicit_mi_override": None},
            "inputs": inputs, "component_manifest": module.legacy.record_file(component),
            "components": {"binary": module.legacy.record_file(component)}},
            "bootstraps": bootstraps, "consensus": consensus}
        self.write(self.run_path, self.run)
        self.out = self.root / "comparison"
        self.args = module.parser().parse_args([
            "--run-manifest", str(self.run_path), "--prepared-dir", str(self.prepared),
            "--publication-dir", str(self.pub), "--audit-file", str(self.audit), "--out", str(self.out),
            "--wsl-r-env", "/mnt/d/isolated/toolchain/r44", "--wsl-r-library", "/mnt/d/isolated/toolchain/paper_r_library"])
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value))

    def fake_command(self, args, network, output):
        return ["mock_R", str(network), str(output)]

    def fake_score(self, command, stdout, stderr, check):
        self.calls.append(command)
        network, output = Path(command[1]), Path(command[2])
        output.mkdir()
        with (output / "ranked_curves.tsv").open("w", newline="") as stream:
            writer = csv.writer(stream, delimiter="\t")
            writer.writerow(["k", "TP", "Random_TP", "EPR", "split_MI_tie"])
            for k in range(1000, 10001, 1000):
                writer.writerow([k, k // 10, k // 20, 2, "FALSE"])
        for name in module.SCORE_OUTPUTS[1:]:
            (output / name).write_text("synthetic output")
        inputs = {"network": module.legacy.digest(network), "reference": self.prepared_hashes["reference_positive_edges.tsv"],
                  "run_manifest": module.legacy.digest(self.run_path), "prepare_manifest": module.legacy.digest(self.prepare_path),
                  "publication_manifest": module.legacy.digest(self.pub / "manifest.json"),
                  "publication_tp": module.legacy.digest(self.pub / "tp.tsv"),
                  "publication_epr": module.legacy.digest(self.pub / "epr.tsv"),
                  "publication_roc_segment": module.legacy.digest(self.pub / "roc_segment.tsv")}
        metrics = {"status": "complete", "exact_reproduction_established": False,
                   "script_sha256": module.legacy.digest(Path(module.__file__).with_name("score_author.R")),
                   "input_sha256": inputs, "output_sha256": {name: module.legacy.digest(output / name) for name in module.SCORE_OUTPUTS},
                   "reported_edges": 10000, "reference_positive_reported_edges": 1000, "AUROC": .62, "Random_AUROC": .51}
        self.write(output / "metrics.json", metrics)
        stdout.write("synthetic score complete\n")
        return subprocess.CompletedProcess(command, 0)

    def execute(self, scorer=None):
        with patch.object(module, "score_command", self.fake_command), patch.object(module.subprocess, "run", scorer or self.fake_score):
            return module.complete(self.args)

    def test_complete_writes_two_verified_scores_and_report(self):
        result = self.execute()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result["consensus"]["0.01"]["points"]["1000"]["tp"], 100)
        self.assertIsNone(result["consensus"]["0.01"]["points"]["100000"]["epr"])
        self.assertEqual(result["published_points"]["10000"]["epr"], 8)
        report = (self.out / "REPORT.md").read_text()
        self.assertIn("| 10000 | 80 | 8 | 1000 | 2 | 1000 | 2 |", report)
        self.assertIn("partial published ROC", report)
        self.assertIn("does not establish a PR70 improvement", report)
        self.assertEqual(json.loads((self.out / "status.json").read_text())["status"], "complete")

    def test_refuses_existing_output(self):
        self.out.mkdir()
        (self.out / "keep").write_text("preserve")
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual((self.out / "keep").read_text(), "preserve")

    def test_audit_must_pass_and_bind_manifest(self):
        self.write(self.audit, {"status": "fail"})
        with self.assertRaisesRegex(ValueError, "audit is not PASS"):
            self.execute()
        self.assertFalse(self.out.exists())

    def test_audit_must_bind_actual_prepared_files(self):
        audit = json.loads(self.audit.read_text())
        audit["prepared_files_sha256"]["hubs.txt"] = "wrong"
        self.write(self.audit, audit)
        with self.assertRaisesRegex(ValueError, "Audit does not bind"):
            self.execute()

    def test_incomplete_run_without_wait_fails_durably(self):
        self.run["status"] = "incomplete"
        self.write(self.run_path, self.run)
        with self.assertRaisesRegex(RuntimeError, "not complete"):
            self.execute()
        self.assertEqual(json.loads((self.out / "status.json").read_text())["status"], "failed")
        self.assertFalse(self.calls)

    def test_wait_uses_30second_polls_then_scores(self):
        self.run["status"] = "incomplete"
        self.write(self.run_path, self.run)
        self.args.wait_for_run = True
        def finish(seconds):
            self.assertEqual(seconds, 30)
            self.run["status"] = "complete"
            self.write(self.run_path, self.run)
        with patch.object(module.time, "sleep", finish):
            self.assertEqual(self.execute()["status"], "complete")

    def test_native_failure_is_not_waited_or_retried(self):
        self.run["status"] = "incomplete"
        self.run["bootstraps"]["1"]["status"] = "failed"
        self.write(self.run_path, self.run)
        self.args.wait_for_run = True
        with patch.object(module.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "contains a failure"):
                self.execute()
            sleep.assert_not_called()
        self.assertFalse(self.calls)

    def test_incomplete100count_or_wrong_parameters_rejected(self):
        del self.run["bootstraps"]["100"]
        self.write(self.run_path, self.run)
        with self.assertRaisesRegex(ValueError, "exactly 100"):
            self.execute()

    def test_unmatched_prepared_context_rejected(self):
        self.run["frozen"]["inputs"]["expression"]["sha256"] = "wrong"
        self.write(self.run_path, self.run)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.execute()

    def test_bootstrap_tamper_or_extra_file_rejected(self):
        (self.native / "adj" / "extra").write_text("extra")
        with self.assertRaisesRegex(ValueError, "Extra or missing"):
            self.execute()

    def test_r_failure_records_failed_status(self):
        def fail(command, **kwargs):
            return subprocess.CompletedProcess(command, 1)
        with self.assertRaisesRegex(RuntimeError, "R scorer failed"):
            self.execute(fail)
        self.assertEqual(json.loads((self.out / "status.json").read_text())["status"], "failed")
        self.assertFalse((self.out / "summary.json").exists())

    def test_scoring_input_tamper_rejected(self):
        def mutate(command, **kwargs):
            result = self.fake_score(command, **kwargs)
            self.run["created"] = "changed"
            self.write(self.run_path, self.run)
            return result
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            self.execute(mutate)

    def test_score_output_tamper_rejected(self):
        def mutate(command, **kwargs):
            result = self.fake_score(command, **kwargs)
            (Path(command[2]) / "ranked_curves.tsv").write_text("changed")
            return result
        with self.assertRaisesRegex(ValueError, "Scorer output changed"):
            self.execute(mutate)

    def test_epr_uses_actual_shuffle_not_expected_baseline(self):
        curve = self.root / "curve.tsv"
        curve.write_text("k\tTP\tRandom_TP\tEPR\n1000\t100\t0\tNA\n")
        self.assertIsNone(module.load_curves(curve, 1000)[1000]["epr"])
        curve.write_text("k\tTP\tRandom_TP\tEPR\n1000\t100\t25\t3\n")
        with self.assertRaisesRegex(ValueError, "actual shuffled TP"):
            module.load_curves(curve, 1000)

    def test_windows_command_derives_posix_mamba_path(self):
        command = module.score_command(self.args, self.native / "consensus_pc1e-02" / "edges.tsv", self.out / "scores")
        self.assertIn("/mnt/d/isolated/toolchain/micromamba", command)
        self.assertIn("R_LIBS_USER=/mnt/d/isolated/toolchain/paper_r_library", command)

    def test_windows_prefix_arguments_normalize_for_driver(self):
        self.assertEqual(module.linux_argument("D:\\isolated\\toolchain\\r44"), "/mnt/d/isolated/toolchain/r44")
        self.assertEqual(module.linux_argument("/mnt/d/isolated/toolchain/r44"), "/mnt/d/isolated/toolchain/r44")
        with self.assertRaises(ValueError):
            module.linux_argument("relative/prefix")

    def test_interruption_records_failed_status(self):
        def interrupt(command, **kwargs):
            raise KeyboardInterrupt("stopped")
        with self.assertRaises(KeyboardInterrupt):
            self.execute(interrupt)
        self.assertEqual(json.loads((self.out / "status.json").read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
