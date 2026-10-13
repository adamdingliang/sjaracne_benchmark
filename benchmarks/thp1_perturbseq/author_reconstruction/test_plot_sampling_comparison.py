"""Synthetic regression checks for additive matched sampling comparison plots."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import plot_sampling_comparison as comparison
import score_fixed_universe as fixed
import score_three_populations as three


class ComparisonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prepared = self.root / "prepared"
        self.prepared.mkdir()
        (self.prepared / "gene_selection.tsv").write_text(
            "gene\tused_for_network\tstrict_SIG_reference_annotation\n" +
            "".join(f"{g}\tTRUE\t{'TRUE' if g == 'A' else 'FALSE'}\n" for g in "ABCDEZ"), encoding="utf-8")
        (self.prepared / "reference_eligible_sources.tsv").write_text("source\nA\n", encoding="utf-8")
        (self.prepared / "reference_positive_edges.tsv").write_text("source\ttarget\nA\tB\nA\tD\nA\tE\n", encoding="utf-8")
        (self.prepared / "hubs.txt").write_text("A\nZ\n", encoding="utf-8")
        (self.prepared / "expression.exp").write_text("fixture\n", encoding="utf-8")
        (self.prepared / "prepare_manifest.json").write_text('{"status": "complete"}\n', encoding="utf-8")
        self.universe = fixed.make_universe(self.prepared)
        self.before = self.make_arm("before", [("B", .9), ("C", .9), ("D", .8), ("E", .7)])
        self.after = self.make_arm("after", [("B", .9), ("C", .9), ("D", .8)])
        self.args = argparse.Namespace(before_metrics=self.before[0], after_metrics=self.after[0],
                                       before_epr=self.before[1], after_epr=self.after[1],
                                       prepared_dir=self.prepared, out=self.root / "comparison",
                                       before_label="Replacement", after_label="No replacement")

    def write_json(self, path, value):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def make_arm(self, name, edges):
        directory = self.root / name
        directory.mkdir()
        network = directory / "edges.tsv"
        network.write_text("source\ttarget\tMI\n" + "".join(f"A\t{target}\t{mi}\n" for target, mi in edges) + "Z\tA\t0.6\n", encoding="utf-8")
        groups, full_count, positive = fixed.read_network(network, self.universe, {"A", "Z"})
        ks, consensus = [1, 2, 5], "consensus_pc1e-02"
        parameters = dict(bootstrap_count=100, seeds=list(range(1, 101)), bootstrap_p=1e-7,
                          consensus_p=[.01], npar=40, dpi_tolerance=0, algorithm="adaptive_partitioning",
                          explicit_mi_override=None, sampling="with replacement" if name == "before" else "without replacement",
                          affine_mi_cutoff=.13 if name == "before" else .15)
        run = {"status": "complete", "frozen": {"observations": 5, "label": name, "parameters": parameters},
               "consensus": {consensus: {"status": "complete", "artifacts": {"edges.tsv": {"path": str(network), "sha256": fixed.digest(network)}}}}}
        if name == "after":
            run["frozen"]["profile"] = "sampling_only_backport"
            run["frozen"]["parameters"]["sampling_draws"] = 4
        run_path = directory / "run_manifest.json"
        self.write_json(run_path, run)
        population = {
            "eligible_emitted": three.population_metrics(groups, positive, len(edges) - positive, 3, 2, ks, "eligible_emitted"),
            "full_emitted": three.population_metrics([*groups, (.6, 0, 1)], positive, full_count - positive, 3, 2, ks, "full_emitted"),
            "fixed_eligible_universe": three.population_metrics(groups, 3, 2, 3, 2, ks, "fixed_eligible_universe"),
        }
        _, roc = fixed.fixed_roc(groups, 3, 2)
        coverage = next(r for r in roc if r["threshold_kind"] == "emitted_MI" and r["selected_pairs"] == len(edges))
        inputs = {str(p): fixed.digest(p) for p in [run_path, network, *[self.prepared / n for n in comparison.PREPARED_FILES]]}
        universe = {"sources": ["A"], "targets": list("ABCDEZ"), "candidate_pairs": 5,
                    "reference_positive_pairs": 3, "definition_sha256": "synthetic-fixture", "n_sources": 1, "n_targets": 6}
        metrics = {"status": "complete", "primary_population": "eligible_emitted", "top_k_prespecified": ks,
                   "definitions": {"AUROC": "whole MI ties", "labels": "response membership"}, "universe": universe,
                   "script_sha256": fixed.digest(Path(three.__file__)), "helper_sha256": fixed.digest(Path(fixed.__file__)),
                   "scores": {consensus: {"consensus_p": .01, "populations": population,
                                            "fixed_reference_coverage": coverage}},
                   "input_sha256": inputs, "output_sha256": {}}
        metrics_dir = directory / "three"
        metrics_dir.mkdir()
        metrics_path = metrics_dir / "metrics.json"
        self.write_json(metrics_path, metrics)
        checkpoints = sorted({1, 2, len(edges)})
        cumulative = {1: 1, 2: 1, 3: 2, 4: 3}
        random_cumulative = {1: 0, 2: 1, 3: 2, 4: 3}
        tie_points = fixed.topk_points(groups, positive, len(edges) - positive, checkpoints)
        ranked = []
        for point in tie_points:
            k = point["k"]
            tp, shuffled = cumulative[k], random_cumulative[k]
            ranked.append({"consensus": consensus, "consensus_p": .01, "k": k, "TP": tp,
                           "Random_TP": shuffled, "EPR_R_seed1_shuffle": tp / shuffled if shuffled else "NA",
                           "TP_tie_expected": point["TP_tie_expected"], "TP_min": point["TP_min"], "TP_max": point["TP_max"]})
        epr_dir = directory / "epr"
        epr_dir.mkdir()
        ranked_path = epr_dir / "ranked_curves.tsv"
        fixed.write_tsv(ranked_path, ranked)
        epr = {"status": "complete", "primary_population": "eligible_emitted", "seed": 1,
               "RNGkind": ["Mersenne-Twister", "Inversion", "Rejection"], "R_version": "4.4.3",
               "script_sha256": fixed.digest(Path(comparison.__file__).with_name("score_eligible_epr.R")),
               "definitions": {"EPR": "integer TP / realized shuffled TP"},
               "scores": {consensus: {"consensus_p": .01, "eligible_emitted_pairs": len(edges),
                                       "reference_positive_emitted_pairs": positive}},
               "input_sha256": {**inputs, str(metrics_path): fixed.digest(metrics_path)},
               "output_sha256": {"ranked_curves.tsv": fixed.digest(ranked_path)}}
        epr_path = epr_dir / "metrics.json"
        self.write_json(epr_path, epr)
        return metrics_path, epr_path

    def load(self):
        hashes = {}
        before = comparison.load_arm("before", "Replacement", *self.before, self.prepared, self.universe, hashes)
        after = comparison.load_arm("after", "No replacement", *self.after, self.prepared, self.universe, hashes)
        return [before, after], hashes

    def test_whole_tie_roc_and_endpoint(self):
        arms, _ = self.load()
        comparison.validate_matched(*arms)
        curve = arms[0]["curves"]["consensus_pc1e-02"]
        self.assertEqual(curve["AUROC"], 1 / 6)
        self.assertEqual([r["threshold_kind"] for r in curve["roc"]], ["above_all", "emitted_MI", "emitted_MI", "emitted_MI"])
        self.assertEqual((curve["roc"][-1]["FPR"], curve["roc"][-1]["sensitivity"]), (1, 1))
        self.assertEqual(curve["ranked"][0]["TP_tie_expected"], .5)
        self.assertEqual((curve["ranked"][0]["TP_min"], curve["ranked"][0]["TP_max"]), (0, 1))
        self.assertIsNone(curve["ranked"][0]["EPR_R_seed1_shuffle"])

    def test_own_pool_not_padded_and_primary_epr_not_analytic_lift(self):
        arms, _ = self.load()
        self.assertEqual([r["k"] for r in arms[0]["curves"]["consensus_pc1e-02"]["ranked"]], [1, 2, 4])
        self.assertEqual([r["k"] for r in arms[1]["curves"]["consensus_pc1e-02"]["ranked"]], [1, 2, 3])
        _, rows = comparison.comparison_rows(arms)
        unavailable = next(r for r in rows if r["population"] == "eligible_emitted" and r["k"] == 5)
        self.assertEqual(unavailable["after_status"], "exceeds_emitted_pairs")
        self.assertIsNone(unavailable["delta_TP_tie_expected"])
        point = next(r for r in rows if r["population"] == "eligible_emitted" and r["k"] == 2)
        self.assertEqual(point["before_EPR_R_seed1_shuffle"], 1)
        self.assertNotEqual(point["before_EPR_R_seed1_shuffle"], point["before_precision_lift_over_random_expectation"])

    def test_successful_additive_output_and_hashes(self):
        with patch.object(comparison, "render", return_value=[]):
            data = comparison.calculate(self.args)
        self.assertEqual(data["arms"][1]["run_profile"], "sampling_only_backport")
        manifest = json.loads((self.args.out / "manifest.json").read_text())
        for name, sha in manifest["output_sha256"].items():
            self.assertEqual(fixed.digest(self.args.out / name), sha)
        self.assertTrue(all(Path(p).exists() for p in manifest["input_sha256"]))
        self.assertIn("not exact Figure 6a", (self.args.out / "REPORT.md").read_text())

    def test_existing_output_refused(self):
        self.args.out.mkdir()
        with self.assertRaises(FileExistsError):
            comparison.calculate(self.args)

    def test_frozen_network_tamper_rejected(self):
        network = self.root / "before" / "edges.tsv"
        network.write_text(network.read_text() + "A\tZ\t0.5\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.load()

    def test_saved_output_tamper_rejected(self):
        ranked = self.after[1].parent / "ranked_curves.tsv"
        ranked.write_text(ranked.read_text() + "tamper\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.load()

    def test_scoring_definition_mismatch_rejected(self):
        arms, _ = self.load()
        arms[1]["three"]["definitions"]["labels"] = "different labels"
        with self.assertRaisesRegex(ValueError, "definitions"):
            comparison.validate_matched(*arms)

    def test_non_sampling_parameter_mismatch_rejected(self):
        arms, _ = self.load()
        arms[1]["parameters"]["dpi_tolerance"] = .1
        with self.assertRaisesRegex(ValueError, "dpi_tolerance"):
            comparison.validate_matched(*arms)

    def test_different_seed_shuffle_rejected(self):
        arms, _ = self.load()
        arms[1]["epr"]["seed"] = 2
        with self.assertRaisesRegex(ValueError, "seed"):
            comparison.validate_matched(*arms)

    def test_ranked_ratio_and_tie_corruption_rejected(self):
        groups = [(0.9, 1, 1), (0.8, 1, 0), (0.7, 1, 0)]
        arms, _ = self.load()
        saved = arms[0]["curves"]["consensus_pc1e-02"]["ranked"]
        rows = [{k: ("NA" if v is None else str(v)) for k, v in r.items()} for r in saved]
        rows[1]["EPR_R_seed1_shuffle"] = "2"
        with self.assertRaisesRegex(ValueError, "EPR is not"):
            comparison.validate_ranked(rows, 4, 3, [1, 2, 5], groups)
        rows[1]["EPR_R_seed1_shuffle"] = "1"
        rows[0]["TP_tie_expected"] = "1"
        with self.assertRaisesRegex(ValueError, "tie-expected"):
            comparison.validate_ranked(rows, 4, 3, [1, 2, 5], groups)

    def test_frozen_inputs_change_during_render_rejected(self):
        def mutate(arms, out):
            (self.prepared / "hubs.txt").write_text("A\nZ\nB\n")
            return []
        with patch.object(comparison, "render", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "changed during comparison"):
                comparison.calculate(self.args)
        self.assertFalse((self.args.out / "manifest.json").exists())

    def test_deterministic_png_pdf_with_no_overwrite(self):
        arms, _ = self.load()
        a, b = self.root / "render_a", self.root / "render_b"
        a.mkdir()
        b.mkdir()
        first, second = comparison.render(arms, a), comparison.render(arms, b)
        self.assertEqual(len(first), 4)
        self.assertEqual([fixed.digest(p) for p in first], [fixed.digest(p) for p in second])


if __name__ == "__main__":
    unittest.main()
