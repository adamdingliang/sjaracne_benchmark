"""Runner protocol checks, without native inference or real expression data."""

import csv
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import benchmark


class ProtocolTests(unittest.TestCase):
    def test_affine_cutoff_is_frozen_at_explicit_m(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config_threshold.txt").write_text("> bcell_mas5\n1.062\t-48.7\t-0.634\n")
            self.assertAlmostEqual(benchmark.affine_cutoff(root, 644, 1e-7),
                                   0.03759353615996272)
            self.assertGreater(benchmark.affine_cutoff(root, 644, 1e-7),
                               benchmark.affine_cutoff(root, 805, 1e-7))

    def test_reference_requires_explicit_both_class_nonself_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.tsv"
            path.write_text("source\ttarget\tlogFC\tlabel\nA\tB\t0.3\t1\nA\tC\t0.1\t0\n")
            self.assertEqual(benchmark.load_reference(path), {("A", "B"): True, ("A", "C"): False})
            with path.open("a") as stream:
                stream.write("A\tB\t0.3\t1\n")
            with self.assertRaises(ValueError):
                benchmark.load_reference(path)

    def test_reference_rejects_one_class_and_self_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.tsv"
            for rows in ("A\tB\t0.3\t1\n", "A\tA\t0.3\t1\nA\tC\t0.1\t0\n"):
                path.write_text("source\ttarget\tlogFC\tlabel\n" + rows)
                with self.assertRaises(ValueError):
                    benchmark.load_reference(path)

    def test_input_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expression.exp"
            path.write_text("isoformId\tgeneSymbol\tcell1\tcell2\nA\tA\t1\t2\nB\tB\t2\t1\n")
            self.assertEqual(benchmark.expression_dimensions(path), (2, 2))

    def test_headers_and_no_json_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "network.adj"
            path.write_text(">  Sampling method fixed-size without replacement\n"
                            ">  Eligible observations 5\n>  Sampled observations 4\nA\tB\t0.1\n")
            self.assertEqual(benchmark.native_header(path)["Sampled observations"], "4")
            benchmark.save_json(root / "state.json", {"value": None})
            with self.assertRaises(FileExistsError):
                benchmark.save_json(root / "state.json", {})


class MockedIntegrationTests(unittest.TestCase):
    """Exercise the entire run/score adapter using only tiny fabricated files."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.out = self.root / "prepared"
        self.out.mkdir()
        (self.out / "expression.exp").write_text(
            "isoformId\tgeneSymbol\tc1\tc2\tc3\tc4\tc5\n"
            "A\tA\t1\t2\t3\t4\t5\nB\tB\t5\t4\t3\t2\t1\n"
            "C\tC\t0\t1\t0\t1\t0\n", encoding="utf-8")
        (self.out / "hubs.txt").write_text("A\nB\n", encoding="utf-8")
        (self.out / "reference.tsv").write_text(
            "source\ttarget\tlogFC\tlabel\nA\tB\t0.5\t1\nA\tC\t0.1\t0\n"
            "B\tA\t0.1\t0\nB\tC\t-0.5\t1\n", encoding="utf-8")
        (self.out / "prepare_manifest.json").write_text("{}\n", encoding="utf-8")
        self.binary = self.root / "fake_binary"
        self.binary.write_bytes(b"mock native executable, never executed")
        self.config = self.root / "config"
        self.config.mkdir()
        (self.config / "config_threshold.txt").write_text(
            "> bcell_mas5\n1.062\t-48.7\t-0.634\n", encoding="utf-8")
        (self.config / "config_kernel.txt").write_text("mock kernel config\n", encoding="utf-8")
        self.args = SimpleNamespace(out=self.out, binary=self.binary, config=self.config,
                                    mi_cutoff=0.2, anchor_p=1e-7, allow_unpinned_binary=False,
                                    wsl_distro=None, seeds=[1], npar=40, workers=1, top_k=[1, 2, 4])
        self.commands = []
        self.empty_final = False

    def native(self, command, **kwargs):
        self.commands.append(command)
        output = Path(command[command.index("-o") + 1])
        stage = next(stage for stage in benchmark.STAGES if output.stem.endswith("_" + stage))
        legacy = "-r" in command
        cutoff = command[command.index("-t") + 1]
        tolerance = command[command.index("-e") + 1]
        self.assertEqual(cutoff, "0" if stage == "all_mi" else "0.2")
        self.assertEqual(tolerance, "0" if stage == "final" else "1")
        if legacy:
            all_edges = {("A", "B"): 0.9, ("A", "C"): 0.8,
                         ("B", "A"): 0.3, ("B", "C"): 0.1}
            final_edges = {("A", "B"): 0.9, ("A", "C"): 0.8}
        else:
            all_edges = {("A", "B"): 0.95, ("A", "C"): 0.15,
                         ("B", "A"): 0.1, ("B", "C"): 0.85}
            final_edges = {("A", "B"): 0.95, ("B", "C"): 0.85}
        edges = (all_edges if stage == "all_mi" else
                 {pair: value for pair, value in all_edges.items() if value >= 0.2}
                 if stage == "cutoff_raw" else {} if self.empty_final else final_edges)
        headers = [f">  MI threshold {cutoff}", f">  DPI tolerance {tolerance}",
                   ">  Eligible observations 5",
                   ">  Sampling method " + ("legacy bootstrap with replacement" if legacy else
                                              "fixed-size without replacement"),
                   ">  Resample draws 5" if legacy else ">  Sampled observations 4"]
        rows = []
        for source in ("A", "B"):
            fields = [source]
            for (edge_source, target), value in edges.items():
                if edge_source == source:
                    fields += [target, str(value)]
            rows.append("\t".join(fields))
        output.write_text("\n".join(headers + rows) + "\n", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    def run_fixture(self):
        with mock.patch.object(benchmark, "PINNED_BINARY_SHA256", benchmark.digest(self.binary)), \
             mock.patch.object(benchmark.subprocess, "run", side_effect=self.native):
            manifest = benchmark.run(self.args)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(len(manifest["jobs"]), 6)
        self.assertEqual(len(self.commands), 6)
        self.assertEqual(manifest["new_arm_draws"], 4)
        self.assertEqual(manifest["legacy_arm_draws"], 5)
        return manifest

    def test_run_score_and_render_tiny_fixture(self):
        before = {name: benchmark.digest(self.out / name) for name in
                  ("expression.exp", "hubs.txt", "reference.tsv", "prepare_manifest.json")}
        self.run_fixture()
        result = benchmark.score(self.args)
        finals = {row["arm"]: row for row in result["per_seed"] if row["stage"] == "final"}
        old = finals[benchmark.ARMS[0]]
        new = finals[benchmark.ARMS[1]]
        self.assertEqual(old["tp"], 1)
        self.assertEqual(old["precision"], 0.5)
        self.assertEqual(old["sensitivity"], 0.5)
        self.assertEqual(old["specificity"], 0.5)
        self.assertEqual(new["tp"], 2)
        self.assertEqual(new["precision"], 1)
        self.assertEqual(new["sensitivity"], 1)
        self.assertEqual(new["specificity"], 1)
        self.assertEqual(new["auroc_common"], 1)
        self.assertIsNone(new["auroc_reported"])
        for name in ("metrics.json", "ranked_curves.json", "REPORT.md",
                     "tp_epr_roc_reported.png", "tp_epr_roc_common.png"):
            self.assertTrue((self.out / name).is_file(), name)
        curves = json.loads((self.out / "ranked_curves.json").read_text())
        for curve in curves:
            if curve["tp"] and curve["tp"][-1]:
                self.assertEqual(curve["epr_shuffle"][-1], 1)
                self.assertEqual(curve["epr_expected"][-1], 1)
        self.assertEqual(before, {name: benchmark.digest(self.out / name) for name in before})

    def test_empty_final_networks_can_be_scored(self):
        self.empty_final = True
        self.run_fixture()
        # Real plot generation is covered above; skip repeated empty-legend warnings.
        with mock.patch.object(benchmark, "draw_plots"):
            result = benchmark.score(self.args)
        for row in result["per_seed"]:
            if row["stage"] == "final":
                self.assertEqual(row["reported_edges"], 0)
                self.assertIsNone(row["precision"])
                self.assertIsNone(row["auroc_reported"])
                self.assertEqual(row["auroc_common"], 0.5)

    def test_score_rejects_modified_reference(self):
        self.run_fixture()
        path = self.out / "reference.tsv"
        path.write_text(path.read_text() + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            benchmark.score(self.args)

    def test_score_rejects_modified_adjacency_even_when_edges_unchanged(self):
        self.run_fixture()
        path = self.out / "runs" / "legacy_seed1_all_mi.adj"
        path.write_text("> appended header change\n" + path.read_text(), encoding="utf-8")
        with self.assertRaises(ValueError):
            benchmark.score(self.args)

    def test_incomplete_stage_subset_is_rejected(self):
        self.run_fixture()
        # Keep hashes consistent to ensure this specifically exercises subset checks.
        path = self.out / "runs" / "legacy_seed1_cutoff_raw.adj"
        path.write_text(path.read_text().replace("A\tB\t0.9", "A\tB\t0.7"), encoding="utf-8")
        manifest_path = self.out / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for job in manifest["jobs"]:
            if job["arm"] == "legacy" and job["stage"] == "cutoff_raw":
                job["adjacency_sha256"] = benchmark.digest(path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            benchmark.score(self.args)

    def test_configuration_change_during_run_marks_manifest_failed(self):
        original_native = self.native

        def mutating_native(command, **kwargs):
            completed = original_native(command, **kwargs)
            if len(self.commands) == 1:
                (self.config / "config_kernel.txt").write_text("changed during inference\n", encoding="utf-8")
            return completed

        with mock.patch.object(benchmark, "PINNED_BINARY_SHA256", benchmark.digest(self.binary)), \
             mock.patch.object(benchmark.subprocess, "run", side_effect=mutating_native):
            with self.assertRaisesRegex(ValueError, "Configuration changed"):
                benchmark.run(self.args)
        manifest = json.loads((self.out / "run_manifest.json").read_text())
        self.assertEqual(manifest["status"], "failed")

    def test_binary_change_during_run_marks_manifest_failed(self):
        original_native = self.native

        def mutating_native(command, **kwargs):
            completed = original_native(command, **kwargs)
            if len(self.commands) == 1:
                self.binary.write_bytes(b"changed mock native executable")
            return completed

        with mock.patch.object(benchmark, "PINNED_BINARY_SHA256", benchmark.digest(self.binary)), \
             mock.patch.object(benchmark.subprocess, "run", side_effect=mutating_native):
            with self.assertRaisesRegex(ValueError, "Native binary changed"):
                benchmark.run(self.args)
        manifest = json.loads((self.out / "run_manifest.json").read_text())
        self.assertEqual(manifest["status"], "failed")


if __name__ == "__main__":
    unittest.main()
