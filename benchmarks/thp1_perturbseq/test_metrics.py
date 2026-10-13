"""Small hand-checkable tests; no data downloads or external tools required."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np


spec = importlib.util.spec_from_file_location("thp1_metrics", Path(__file__).with_name("metrics.py"))
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class RankingTests(unittest.TestCase):
    def test_perfect_and_inverse(self):
        self.assertEqual(metrics.ranking_metrics([2, 1], [True, False]), (1.0, 1.0))
        auc, ap = metrics.ranking_metrics([0, 1, 2], [True, False, False])
        self.assertEqual(auc, 0.0)
        self.assertAlmostEqual(ap, 1 / 3)

    def test_ties_receive_half_credit_and_grouped_ap(self):
        self.assertEqual(metrics.ranking_metrics([1, 1], [True, False]), (0.5, 0.5))
        auc, ap = metrics.ranking_metrics([0.9, 0.8, 0.8, 0.1], [True, False, True, False])
        self.assertAlmostEqual(auc, 0.875)
        self.assertAlmostEqual(ap, 5 / 6)
        # Reordering labels within an equal-score group must not change metrics.
        self.assertEqual(metrics.ranking_metrics([0.9, 0.8, 0.8, 0.1], [True, True, False, False]),
                         (auc, ap))

    def test_single_class_and_empty(self):
        self.assertEqual(metrics.ranking_metrics([], []), (None, None))
        self.assertEqual(metrics.ranking_metrics([0, 1], [False, False]), (None, None))
        self.assertEqual(metrics.ranking_metrics([0, 1], [True, True]), (None, 1.0))

    def test_invalid_inputs(self):
        for scores, labels in [([1], []), ([float("nan")], [True]),
                               ([float("inf")], [True]), ([-1], [True]),
                               ([0], [1]), ([0], [None]), ([[0]], [True])]:
            with self.subTest(scores=scores, labels=labels):
                with self.assertRaises(ValueError):
                    metrics.ranking_metrics(scores, labels)

    def test_generators_supported(self):
        self.assertEqual(metrics.ranking_metrics((s for s in [2, 1]),
                                                 (y for y in [True, False])), (1.0, 1.0))

    def test_grouped_roc(self):
        curve = metrics.roc_curve([0.9, 0.8, 0.8, 0.1], [True, False, True, False])
        self.assertEqual(curve["selected"], [0, 1, 3, 4])
        self.assertEqual(curve["fpr"], [0, 0, 0.5, 1])
        self.assertEqual(curve["tpr"], [0, 0.5, 1, 1])
        self.assertIsNone(curve["thresholds"][0])
        json.dumps(curve, allow_nan=False)


class EarlyPrecisionTests(unittest.TestCase):
    def test_full_list_epr_equals_one(self):
        curve = metrics.ranked_curve([4, 3, 2, 1], [True, True, False, False], [1, 2, 4])
        self.assertEqual(curve["tp"][-1], 2)
        self.assertEqual(curve["tp_random"][-1], 2)
        self.assertEqual(curve["epr_shuffle"][-1], 1)
        self.assertEqual(curve["epr_expected"][-1], 1)
        self.assertEqual(curve["expected_random_precision"], 0.5)
        self.assertEqual(curve["epr_expected"][0], 2)
        self.assertEqual(curve["fpr"][-1], 1)
        self.assertEqual(curve["tpr"][-1], 1)
        json.dumps(curve, allow_nan=False)

    def test_zero_shuffle_denominator_is_null(self):
        labels = [True, False, False, False]
        seed = next(seed for seed in range(100)
                    if np.random.default_rng(seed).permutation(4)[0] != 0)
        curve = metrics.ranked_curve([4, 3, 2, 1], labels, [1, 4], random_seed=seed)
        self.assertIsNone(curve["epr_shuffle"][0])
        self.assertEqual(curve["epr_expected"][0], 4)
        self.assertEqual(curve["epr_shuffle"][-1], 1)

    def test_seed_and_tie_flag(self):
        args = ([2, 1, 1, 0], [True, False, True, False], [1, 2, 3, 4])
        self.assertEqual(metrics.ranked_curve(*args, random_seed=42),
                         metrics.ranked_curve(*args, random_seed=42))
        self.assertEqual(metrics.ranked_curve(*args)["split_tie"], [False, True, False, False])

    def test_absent_classes_and_empty(self):
        curve = metrics.ranked_curve([2, 1], [False, False], [2])
        self.assertEqual(curve["epr_expected"], [None])
        self.assertEqual(curve["epr_shuffle"], [None])
        self.assertEqual(curve["tpr"], [None])
        self.assertEqual(metrics.ranked_curve([], [], [])["k"], [])

    def test_invalid_k_and_seed(self):
        for requested in [[0], [3], [2, 1], [1, 1], [True], [1.0]]:
            with self.subTest(requested=requested):
                with self.assertRaises(ValueError):
                    metrics.ranked_curve([2, 1], [True, False], requested)
        for seed in [-1, True, 1.5]:
            with self.assertRaises(ValueError):
                metrics.ranked_curve([2, 1], [True, False], [1], random_seed=seed)


class EvaluationTests(unittest.TestCase):
    def test_common_universe_missing_scores_and_operating_point(self):
        reference = {("S", "A"): True, ("S", "B"): True,
                     ("S", "C"): False, ("S", "D"): False}
        result = metrics.evaluate({("S", "A"): 0.9, ("S", "C"): 0.1}, reference)
        primary = result["all_candidates"]
        self.assertAlmostEqual(primary["auroc"], 0.625)
        self.assertAlmostEqual(primary["average_precision"], 0.75)
        self.assertEqual([primary[key] for key in ["tp", "fp", "tn", "fn"]], [1, 1, 1, 1])
        self.assertEqual(primary["precision"], 0.5)
        self.assertEqual(primary["sensitivity"], 0.5)
        self.assertEqual(primary["specificity"], 0.5)
        self.assertEqual(result["reported_only"]["auroc"], 1)
        self.assertEqual(result["reported_only"]["average_precision"], 1)
        self.assertEqual(result["reported_fraction"], 0.5)
        json.dumps(result, allow_nan=False)

    def test_no_outputs_yields_chance_ranking_and_no_precision(self):
        result = metrics.evaluate({}, {("S", "A"): True, ("S", "B"): False})
        self.assertEqual(result["all_candidates"]["auroc"], 0.5)
        self.assertEqual(result["all_candidates"]["average_precision"], 0.5)
        self.assertIsNone(result["all_candidates"]["precision"])
        self.assertEqual(result["reported_only"]["pairs"], 0)

    def test_unknown_pairs_rejected(self):
        with self.assertRaises(ValueError):
            metrics.evaluate({("S", "B"): 1}, {("S", "A"): True})

    def test_zero_mi_reported_edge_is_selected(self):
        result = metrics.evaluate({("S", "A"): 0}, {("S", "A"): True, ("S", "B"): False})
        self.assertEqual(result["all_candidates"]["tp"], 1)
        self.assertEqual(result["all_candidates"]["fn"], 0)
        self.assertEqual(result["all_candidates"]["auroc"], 0.5)


class AdjacencyTests(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.adj"
            path.write_text(text, encoding="utf-8")
            return metrics.adjacency(path)

    def test_valid_with_headers_and_empty_rows(self):
        self.assertEqual(self.read("\ufeff> MI threshold 0\n\nS\tA\t0.2\tB\t0\nEMPTY\n"),
                         {("S", "A"): 0.2, ("S", "B"): 0})

    def test_invalid_and_duplicate_rows_or_edges(self):
        texts = ["S\tA\n", "\tA\t1\n", "S\t\t1\n", "S\tA\tnan\n",
                 "S\tA\tinf\n", "S\tA\t-1\n", "S\tA\tbad\n",
                 "S\tA\t1\tA\t1\n", "S\tA\t1\nS\tB\t2\n"]
        for text in texts:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.read(text)


if __name__ == "__main__":
    unittest.main()
