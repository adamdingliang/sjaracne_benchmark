"""Small synthetic fixed-universe tests; never modify real benchmark inputs."""

import argparse
import csv
import itertools
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from sklearn.metrics import roc_auc_score

import score_fixed_universe as module


class FixedROCTests(unittest.TestCase):
    def check(self, scores, labels):
        emitted = [i for i, s in enumerate(scores) if s is not None]
        groups = module.group_scores([scores[i] for i in emitted], [labels[i] for i in emitted])
        positive = sum(labels)
        result, curve = module.fixed_roc(groups, positive, len(labels) - positive)
        dense_scores = [-1 if s is None else s for s in scores]
        expected = roc_auc_score(labels, dense_scores)
        self.assertAlmostEqual(result["AUROC_fixed_universe_MI_ties"], expected, places=12)
        wins = sum((dense_scores[i] > dense_scores[j]) + .5 * (dense_scores[i] == dense_scores[j])
                   for i, p in enumerate(labels) if p for j, q in enumerate(labels) if not q)
        self.assertAlmostEqual(result["AUROC_fixed_universe_MI_ties"], wins / (positive * (len(labels) - positive)), places=12)
        self.assertEqual((curve[0]["FPR"], curve[0]["sensitivity"]), (0, 0))
        self.assertEqual((curve[-1]["FPR"], curve[-1]["sensitivity"]), (1, 1))
        for row in curve:
            self.assertEqual(row["TP"] + row["FN"], positive)
            self.assertEqual(row["FP"] + row["TN"], len(labels) - positive)
        return result, curve

    def test_empty_and_complete_networks(self):
        self.assertEqual(self.check([None] * 4, [True, False, True, False])[0]["AUROC_fixed_universe_MI_ties"], .5)
        self.assertEqual(self.check([3, 2, 1, 0], [True, True, False, False])[0]["AUROC_fixed_universe_MI_ties"], 1)
        self.assertEqual(self.check([3, 2, 1, 0], [False, False, True, True])[0]["AUROC_fixed_universe_MI_ties"], 0)
        self.assertEqual(self.check([0] * 4, [True, False, True, False])[0]["AUROC_fixed_universe_MI_ties"], .5)

    def test_absent_below_emitted_zero_and_ties(self):
        self.assertEqual(self.check([0, None], [True, False])[0]["AUROC_fixed_universe_MI_ties"], 1)
        self.assertEqual(self.check([0, None], [False, True])[0]["AUROC_fixed_universe_MI_ties"], 0)
        self.check([.2, .2, .1, None, None, None], [True, False, False, True, True, False])
        self.assertEqual(self.check([.2, None, None, None], [True, True, False, False])[0]["AUROC_fixed_universe_MI_ties"], .75)
        self.assertEqual(self.check([.2, None, None, None], [False, False, True, True])[0]["AUROC_fixed_universe_MI_ties"], .25)

    def test_exhaustive_small_pairwise_comparison(self):
        # Covers all class assignments and missing/MI0/MI1 assignments for 2..4 pairs.
        for size in range(2, 5):
            for labels in itertools.product((False, True), repeat=size):
                if not 0 < sum(labels) < size:
                    continue
                for scores in itertools.product((None, 0, 1), repeat=size):
                    emitted = [i for i, value in enumerate(scores) if value is not None]
                    groups = module.group_scores([scores[i] for i in emitted], [labels[i] for i in emitted])
                    result, _ = module.fixed_roc(groups, sum(labels), size - sum(labels))
                    values = [-1 if x is None else x for x in scores]
                    expected = sum((values[i] > values[j]) + .5 * (values[i] == values[j])
                                   for i, p in enumerate(labels) if p for j, q in enumerate(labels) if not q)
                    self.assertAlmostEqual(result["AUROC_fixed_universe_MI_ties"], expected / (sum(labels) * (size - sum(labels))), places=12)

    def test_invalid_inputs_and_missing_class(self):
        for scores in ([float("nan")], [float("inf")], [-.1]):
            with self.assertRaises(ValueError):
                module.group_scores(scores, [True])
        for p, n in ((0, 1), (1, 0), (-1, 3)):
            with self.assertRaises(ValueError):
                module.fixed_roc([], p, n)
        with self.assertRaises(ValueError):
            module.fixed_roc([(1, 2, 0)], 1, 1)
        with self.assertRaises(ValueError):
            module.fixed_roc([(1, 1, 0), (1, 0, 1)], 1, 1)

    def test_topk_tie_expected_range_and_unavailable(self):
        groups = [(1, 1, 0), (.5, 2, 2)]
        result = module.topk_points(groups, 10, 20, [1, 2, 3, 5, 6])
        self.assertEqual(result[1]["TP_tie_expected"], 1.5)
        self.assertEqual((result[1]["TP_min"], result[1]["TP_max"]), (1, 2))
        self.assertEqual(result[1]["sensitivity_tie_expected"], .15)
        self.assertTrue(result[1]["split_MI_tie"])
        self.assertFalse(result[3]["split_MI_tie"])
        self.assertEqual(result[4]["status"], "exceeds_emitted_eligible_pairs")
        # Row ordering inside equal-score groups cannot affect any new ROC metric.
        a = module.group_scores([1, .5, .5], [True, False, True])
        b = module.group_scores([.5, 1, .5], [True, True, False])
        self.assertEqual(a, b)


class ProvenanceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.prepared = self.root / "prepared"
        self.prepared.mkdir()

        def tsv(path, rows):
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream, delimiter="\t").writerows(rows)

        self.tsv = tsv
        self.tsv(self.prepared / "gene_selection.tsv", [
            ["gene", "used_for_network", "strict_SIG_reference_annotation"],
            ["A", "TRUE", "TRUE"], ["B", "TRUE", "TRUE"],
            ["C", "TRUE", "FALSE"], ["D", "FALSE", "FALSE"]])
        self.tsv(self.prepared / "reference_eligible_sources.tsv", [["source"], ["A"], ["B"]])
        self.tsv(self.prepared / "reference_positive_edges.tsv", [
            ["source", "target"], ["A", "B"], ["A", "A"], ["B", "C"], ["B", "D"]])
        (self.prepared / "hubs.txt").write_text("A\nB\nC\n")
        (self.prepared / "expression.exp").write_text("synthetic frozen expression\n")
        outputs = {p.name: {"sha256": module.digest(p)} for p in self.prepared.iterdir()}
        self.prepare = {"status": "complete", "outputs": outputs,
                        "gene_panel": {"n_NT_nonzero_inference_genes": 3},
                        "reference": {"n_positive_pairs": 4}}
        self.prepare_path = self.prepared / "prepare_manifest.json"
        self.write_json(self.prepare_path, self.prepare)
        self.network = self.root / "edges.tsv"
        self.tsv(self.network, [["source", "target", "MI"], ["A", "B", .3], ["A", "C", .2], ["C", "A", .8], ["B", "C", 0]])
        self.run = {"status": "complete", "frozen": {"inputs": {
            "prepare_manifest": self.record(self.prepare_path), "expression": self.record(self.prepared / "expression.exp"),
            "hubs": self.record(self.prepared / "hubs.txt")}},
            "consensus": {"consensus_pc1e-02": {"status": "complete", "p": .01,
                                                   "artifacts": {"edges.tsv": self.record(self.network)}}}}
        self.run_path = self.root / "run_manifest.json"
        self.write_json(self.run_path, self.run)
        self.author_dir = self.root / "comparison" / "score_pc1e-02"
        self.author_dir.mkdir(parents=True)
        (self.author_dir / "original.tsv").write_text("preserved output\n")
        self.author = {"AUROC": .51, "reported_edges": 4, "reference_positive_reported_edges": 2,
                       "input_sha256": {"network": module.digest(self.network), "run_manifest": module.digest(self.run_path),
                                        "reference": module.digest(self.prepared / "reference_positive_edges.tsv")},
                       "output_sha256": {"original.tsv": module.digest(self.author_dir / "original.tsv")}}
        self.write_json(self.author_dir / "metrics.json", self.author)
        self.args = argparse.Namespace(prepared_dir=self.prepared, run_manifest=self.run_path,
                                       author_comparison_dir=self.author_dir.parent, out=self.root / "new_scores", top_k=[1, 2, 3, 4])

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def record(path):
        return {"path": str(path.resolve()), "sha256": module.digest(path)}

    def test_universe_and_end_to_end_input_immutability(self):
        inputs = {str(p): module.digest(p) for p in self.root.rglob("*") if p.is_file()}
        result = module.calculate(self.args)
        u = result["universe"]
        self.assertEqual((u["candidate_pairs"], u["reference_positive_pairs"], u["reference_negative_pairs"]), (4, 2, 2))
        self.assertEqual(u["excluded_reference_pairs"], {"source_not_eligible_inference_hub": 0, "target_not_inference_gene": 1, "self_pair": 1})
        score = result["scores"]["consensus_pc1e-02"]
        self.assertEqual(score["AUROC_fixed_universe_MI_ties"], .75)
        self.assertEqual(score["preserved_AUROC_within_emitted_edges_author_ordinal"], .51)
        self.assertEqual(score["operating_point_all_emitted"]["sensitivity"], 1)
        self.assertEqual(score["operating_point_all_emitted"]["specificity"], .5)
        self.assertEqual(score["excluded_unassayed_source_predictions"], 1)
        self.assertTrue((self.args.out / "metrics.json").is_file())
        self.assertEqual({p: module.digest(Path(p)) for p in inputs}, inputs)
        with self.assertRaises(FileExistsError):
            module.calculate(self.args)

    def test_fail_closed_tampered_reference(self):
        with (self.prepared / "reference_positive_edges.tsv").open("a") as stream:
            stream.write("A\tC\n")
        with self.assertRaisesRegex(ValueError, "Input hash mismatch"):
            module.calculate(self.args)
        self.assertFalse(self.args.out.exists())

    def test_fail_closed_changed_author_artifact(self):
        (self.author_dir / "original.tsv").write_text("changed\n")
        with self.assertRaisesRegex(ValueError, "Input hash mismatch"):
            module.calculate(self.args)
        self.assertFalse(self.args.out.exists())

    def test_duplicate_and_out_of_universe_predictions(self):
        u = module.make_universe(self.prepared)
        for extra in (["A", "B", .3], ["A", "A", .3], ["A", "D", .3]):
            self.tsv(self.network, [["source", "target", "MI"], ["A", "B", .3], extra])
            with self.assertRaises(ValueError):
                module.read_network(self.network, u, {"A", "B", "C"})


if __name__ == "__main__":
    unittest.main()
