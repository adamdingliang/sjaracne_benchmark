"""Small offline synthetic tests; never run inference or alter scientific inputs."""
import csv
import itertools
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

import score


class MetricTests(unittest.TestCase):
    def test_perfect_reversed_and_all_tied(self):
        labels = [True, True, False, False]
        for values, expected in (([4, 3, 2, 1], 1), ([1, 2, 3, 4], 0), ([0, 0, 0, 0], .5)):
            result = score.score_arrays(values, labels, ks=[1, 2, 4], curve_ks=[0, 1, 2, 4])
            self.assertEqual(result["AUROC_MI_ties"], expected)
            self.assertAlmostEqual(result["AUROC_ROC_integral_check"], expected)
            self.assertEqual(result["curve"][0]["specificity_tie_expected"], 1)
            self.assertEqual(result["curve"][-1]["sensitivity_tie_expected"], 1)
            self.assertEqual(result["curve"][-1]["EPR_tie_expected"], 1)
            self.assertEqual(len(result["roc_curve"]["FPR"]), 1001)
            self.assertEqual(result["roc_curve"]["sensitivity"][-1], 1)
            self.assertTrue(np.all(np.diff(result["roc_curve"]["sensitivity"]) >= 0))
            json.dumps(result, allow_nan=False)

    def test_topk_boundary_tie_expected_and_range(self):
        result = score.score_arrays([1, .5, .5, .5, .5, 0], [1, 1, 1, 0, 0, 0], ks=[2, 3, 5])
        row = result["top_k"][0]
        self.assertEqual(row["TP_tie_expected"], 1.5)
        self.assertEqual((row["TP_min"], row["TP_max"]), (1, 2))
        self.assertTrue(row["split_MI_tie"])
        self.assertFalse(result["top_k"][-1]["split_MI_tie"])
        self.assertEqual(row["random_TP_expectation_at_k"], 1)
        self.assertEqual(row["EPR_tie_expected"], 1.5)

    def test_exhaustive_pairwise_auc(self):
        for labels in itertools.product((False, True), repeat=4):
            p = sum(labels)
            if p in (0, 4):
                continue
            for values in itertools.product((0, 1), repeat=4):
                expected = sum((values[i] > values[j]) + .5 * (values[i] == values[j])
                               for i in range(4) if labels[i] for j in range(4) if not labels[j]) / (p * (4 - p))
                actual = score.score_arrays(values, labels, ks=[1, 4], curve_ks=[])
                self.assertEqual(actual["AUROC_MI_ties"], expected)

    def test_determinism_under_tie_permutation(self):
        a = score.score_arrays([2, 1, 1, 0], [1, 1, 0, 0], ks=[2])
        b = score.score_arrays([1, 0, 2, 1], [0, 0, 1, 1], ks=[2])
        self.assertEqual(a, b)

    def test_invalid_scores_classes_and_k(self):
        for values in ([float("nan"), 0], [float("inf"), 0], [-1, 0]):
            with self.assertRaises(ValueError):
                score.score_arrays(values, [1, 0], ks=[1])
        for labels in ([0, 0], [1, 1]):
            with self.assertRaises(ValueError):
                score.score_arrays([1, 0], labels, ks=[1])
        for ks in ([0], [3], [1, 1], [True], [1.5]):
            with self.assertRaises(ValueError):
                score.score_arrays([1, 0], [1, 0], ks=ks)
        with self.assertRaises(ValueError):
            score.score_arrays([1, 0], [1], ks=[1])


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "raw.adj"
        self.universe = score.Universe(("A", "B"), ("A", "B", "C"), np.array([1, 0, 0, 1]), {"definition_sha256": "synthetic"})
        self.header = ">  Input file      expr.exp\n>  MI threshold    0\n>  MI P-value      1\n>  DPI tolerance   1\n>  Subnetwork file /mnt/d/data/hubs.txt\n"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, body, header=None):
        self.path.write_text((self.header if header is None else header) + body, encoding="utf-8")

    def test_pair_index_source_major_excludes_self(self):
        self.assertEqual([self.universe.pair_index(*pair) for pair in (("A", "B"), ("A", "C"), ("B", "A"), ("B", "C"))], list(range(4)))
        with self.assertRaises(ValueError):
            self.universe.pair_index("A", "A")

    def test_complete_rows_omitted_zero_and_explicit_zero_share_tie(self):
        self.write("A\tB\t0.8\nB\tA\t0\n")
        values, validation = score.parse_adjacency(self.path, self.universe, expected_subnetwork=r"D:\data\hubs.txt", arm="before")
        np.testing.assert_array_equal(values, [.8, 0, 0, 0])
        self.assertEqual(validation["eligible_zero_MI_pairs"], 3)
        result = score.score_arrays(values, self.universe.labels, ks=[2])
        self.assertAlmostEqual(result["AUROC_MI_ties"], .75)
        self.assertEqual(result["top_k"][0]["TP_tie_expected"], 1 + 1 / 3)

    def test_complete_all_zero_rows_allowed_but_missing_row_rejected(self):
        self.write("A\nB\n")
        values, _ = score.parse_adjacency(self.path, self.universe)
        self.assertEqual(score.score_arrays(values, self.universe.labels, ks=[1])["AUROC_MI_ties"], .5)
        self.write("A\n")
        with self.assertRaisesRegex(ValueError, "Missing expected"):
            score.parse_adjacency(self.path, self.universe)

    def test_reject_malformed_rows_and_invalid_values(self):
        for body in ("A\tB\t1\tB\t2\nB\n", "A\nA\nB\n", "A\tA\t1\nB\n", "A\tX\t1\nB\n",
                     "A\tB.123\t1\nB\n", "A\tB\nB\n", "A\tB\tnan\nB\n", "A\tB\tinf\nB\n",
                     "A\tB\t-1\nB\n", "A\tB\tno\nB\n", "A\nB", "A\n\nB\n", "X\nA\nB\n"):
            with self.subTest(body=body):
                self.write(body)
                with self.assertRaises(ValueError):
                    score.parse_adjacency(self.path, self.universe)

    def test_reject_bad_and_missing_headers(self):
        for header in (self.header.replace("threshold    0", "threshold    .1"), self.header.replace("P-value      1", "P-value      1e-7"),
                       self.header.replace("tolerance   1", "tolerance   0"), self.header + "> MI threshold 0\n",
                       self.header.replace(">  MI P-value      1\n", ""), self.header + "> Unknown header 1\n"):
            self.write("A\nB\n", header)
            with self.assertRaises(ValueError):
                score.parse_adjacency(self.path, self.universe)
        self.write("A\nB\n")
        with self.assertRaises(ValueError):
            score.parse_adjacency(self.path, self.universe, expected_subnetwork="wrong")

    def test_sampling_after_headers_and_full_source_validation(self):
        extra = "> Sampling method fixed-size without replacement\n> Sampling request 80%\n> Eligible observations 121\n> Sampled observations 97\n"
        self.write("A\tB\t.1\nB\nC\tA\t.2\n", self.header + extra)
        values, validation = score.parse_adjacency(self.path, self.universe, expected_sources=["A", "B", "C"], arm="after")
        self.assertEqual(validation["emitted_pairs"], 2)
        self.assertEqual(validation["eligible_emitted_pairs"], 1)
        with self.assertRaises(ValueError):
            score.parse_adjacency(self.path, self.universe, expected_sources=["A", "B", "C"], arm="before")
        self.write("A\nB\n", self.header + extra.replace("97", "96"))
        with self.assertRaises(ValueError):
            score.parse_adjacency(self.path, self.universe, arm="after")

    def test_load_universe_exclusions_and_identifier_mapping(self):
        def tsv(name, rows):
            with (self.root / name).open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream, delimiter="\t").writerows(rows)
        tsv("gene_selection.tsv", [["gene", "used_for_network", "strict_SIG_reference_annotation"],
                                   ["A", "TRUE", "TRUE"], ["B", "TRUE", "TRUE"], ["C", "TRUE", "FALSE"], ["D", "FALSE", "FALSE"]])
        tsv("reference_eligible_sources.tsv", [["source"], ["B"], ["A"]])
        tsv("reference_positive_edges.tsv", [["source", "target"], ["A", "B"], ["B", "C"], ["A", "A"], ["B", "D"]])
        (self.root / "hubs.txt").write_text("A\nB\nC\n")
        universe = score.load_universe(self.root)
        self.assertEqual(universe.sources, ("A", "B"))
        np.testing.assert_array_equal(universe.labels, [1, 0, 0, 1])
        self.assertEqual((universe.size, universe.P, universe.N), (4, 2, 2))
        self.assertEqual(universe.definition["excluded_reference_pairs"], {"source_not_eligible_inference_hub": 0, "target_not_inference_gene": 1, "self_pair": 1})
        self.assertEqual(len(universe.definition_sha256), 64)
        with (self.root / "reference_positive_edges.tsv").open("a") as stream:
            stream.write("A\tB\n")
        with self.assertRaises(ValueError):
            score.load_universe(self.root)


if __name__ == "__main__":
    unittest.main()
