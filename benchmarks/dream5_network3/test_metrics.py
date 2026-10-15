"""Synthetic protocol, MI identity, tie metrics and explicit-label scoring tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

import metrics


class RankingTests(unittest.TestCase):
    def test_matches_sklearn_perfect_reversed_and_tied(self):
        for values in ([3, 2, 1, 0], [0, 1, 2, 3], [0, 0, 0, 0], [.2, .2, .1, 0]):
            labels = [1, 1, 0, 0]
            result = metrics.ranking_metrics(values, labels, raw=True, ks=(1, 2, 4))
            self.assertAlmostEqual(result["AUROC_fixed_explicit_universe_MI_ties"], roc_auc_score(labels, values), places=12)
            self.assertAlmostEqual(result["average_precision_fixed_explicit_universe"], average_precision_score(labels, values), places=12)

    def test_randomized_sklearn_crosscheck(self):
        rng = np.random.default_rng(271)
        for size in (10, 100, 1000):
            values = np.round(rng.random(size), 1)
            labels = rng.random(size) < .2
            labels[0], labels[-1] = True, False
            result = metrics.ranking_metrics(values, labels, raw=True, ks=(1,))
            self.assertAlmostEqual(result["AUROC_fixed_explicit_universe_MI_ties"], roc_auc_score(labels, values), places=12)
            self.assertAlmostEqual(result["average_precision_fixed_explicit_universe"], average_precision_score(labels, values), places=12)

    def test_tie_topk_ranges_and_fixed_EPR(self):
        result = metrics.ranking_metrics([1, .5, .5, .5, .5, 0], [1, 1, 1, 0, 0, 0], raw=True, ks=(2,))
        point = result["top_k"][0]
        self.assertEqual((point["TP_tie_expected"], point["TP_min"], point["TP_max"]), (1.5, 1, 2))
        self.assertEqual(point["EPR_fixed_universe"], 1.5)

    def test_post_topk_not_padded_but_auc_has_zero_bottom_tie(self):
        result = metrics.ranking_metrics([1, 0, 0, 0], [1, 1, 0, 0], emitted=[1, 0, 0, 0], ks=(1, 2))
        self.assertEqual(result["top_k"][1]["status"], "exceeds_labelled_emitted_pairs")
        self.assertEqual(result["AUROC_fixed_explicit_universe_MI_ties"], .75)

    def test_unlabelled_predictions_not_false_positives(self):
        parsed = metrics.ParsedStage(np.array([[0, .8, .7, .6]]), np.array([[0, 1, 1, 1]], bool), {}, 1, {})
        result = metrics.score_stage(parsed, np.array([0, 0]), np.array([1, 2]), np.array([1, 0], bool), raw=True)
        self.assertEqual((result["TP"], result["FP"], result["edges_unlabelled"]), (1, 1, 1))

    def test_invalid_scores_or_classes_rejected(self):
        for values, labels in (([float("nan"), 0], [1, 0]), ([-1, 0], [1, 0]), ([1, 0], [1, 1])):
            with self.assertRaises(ValueError):
                metrics.ranking_metrics(values, labels, raw=True)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan = {"arms": ["legacy", "u80"], "seeds": [1], "dataset": {"genes": 3, "TFs": 2, "profiles": 5},
                     "inputs": {"expression": {"path": "D:/expr.exp"}, "hubs": {"path": "D:/hubs.txt"}},
                     "sampling": {"legacy": {"draws": 5, "population": 5, "method": "legacy bootstrap with replacement", "value": "1"},
                                  "u80": {"draws": 4, "population": 5, "method": "fixed-size without replacement", "value": "80%"}},
                     "parameters": {"fixed_mi": .03759353615996272, "nominal_p": 1e-7, "nominal_cutoffs": {"legacy": .03759353615996272, "u80": .03759353615996272}}}

    def tearDown(self):
        self.temp.cleanup()

    def write_stage(self, stage, body="A\tB\t0.0375935\nB\n", arm="legacy", cutoff=None):
        directory = self.root / stage
        directory.mkdir(exist_ok=True)
        sample = self.plan["sampling"][arm]
        cutoff = metrics.expected_cutoff(self.plan, arm, stage) if cutoff is None else cutoff
        p = 1e-7 if stage.startswith("nominal") else 1
        count_header = "Resample draws" if arm == "legacy" else "Sampled observations"
        request = "legacy -r 1" if arm == "legacy" else "80%"
        header = f"> Input file /mnt/d/expr.exp\n> MI threshold {cutoff:.6g}\n> MI P-value {p}\n> DPI tolerance {0 if stage.endswith('post') else 1}\n> Subnetwork file /mnt/d/hubs.txt\n> Sampling method {sample['method']}\n> Sampling request {request}\n> Eligible observations 5\n> {count_header} {sample['draws']}\n"
        (directory / "raw.adj").write_text(header + body)
        log = f"Marker No: 3 (3 active), Array No: {sample['draws']}\n[SUBNETWORK] Requested: 2, matched: 2, missing: 0\nGene: 2 Time: 1\nWriting matrix: out\nMaximum observed npar: 3\n"
        if stage.startswith("nominal"):
            log += "MI threshold determined for p=1e-07: .0375935\n"
        if stage.endswith("post"):
            log += "[NETWORK] Applying DPI ...\n"
        if arm == "u80":
            log += "selected 4 of 5 eligible observations (request: 80%)\n"
        (directory / "stdout.log").write_text(log)
        return directory

    def test_rounding_band_accepts_retained_MI_slightly_below_exact_cutoff(self):
        path = self.write_stage("fixed_pre")
        with patch.object(metrics, "native_identifiers", return_value=(("A", "B", "C"), ("A", "B"))):
            result = metrics.validate_job_output(path / "raw.adj", path / "stdout.log", plan=self.plan, arm="legacy", stage="fixed_pre")
        self.assertEqual(result["edges_all"], 1)
        self.assertLess(result["minimum_emitted_MI"], self.plan["parameters"]["fixed_mi"])

    def test_missing_empty_source_rows_allowed_only_with_complete_log(self):
        path = self.write_stage("fixed_pre", "A\tB\t0.1\n")
        with patch.object(metrics, "native_identifiers", return_value=(("A", "B", "C"), ("A", "B"))):
            metrics.validate_job_output(path / "raw.adj", path / "stdout.log", plan=self.plan, arm="legacy", stage="fixed_pre")
            (path / "stdout.log").write_text("Incomplete traversal\n")
            with self.assertRaises(ValueError):
                metrics.validate_job_output(path / "raw.adj", path / "stdout.log", plan=self.plan, arm="legacy", stage="fixed_pre")

    def test_subset_and_exact_MI_identity(self):
        paths = {stage: self.write_stage(stage) for stage in metrics.STAGES}
        with patch.object(metrics, "native_identifiers", return_value=(("A", "B", "C"), ("A", "B"))):
            self.assertEqual(metrics.validate_arm_stages(self.plan, "legacy", 1, paths)["status"], "passed")
            text = (paths["nominal_post"] / "raw.adj").read_text().replace("A\tB\t0.0375935", "A\tB\t0.0375936")
            (paths["nominal_post"] / "raw.adj").write_text(text)
            with self.assertRaisesRegex(ValueError, "MI differs"):
                metrics.validate_arm_stages(self.plan, "legacy", 1, paths)

    def test_post_not_in_pre_rejected_even_within_cutoff_rounding_band(self):
        paths = {stage: self.write_stage(stage) for stage in metrics.STAGES}
        self.write_stage("fixed_pre", "A\nB\n")
        with patch.object(metrics, "native_identifiers", return_value=(("A", "B", "C"), ("A", "B"))):
            with self.assertRaisesRegex(ValueError, "subset"):
                metrics.validate_arm_stages(self.plan, "legacy", 1, paths)

    def test_pre_cannot_drop_raw_edge_clearly_above_cutoff(self):
        paths = {stage: self.write_stage(stage, "A\tB\t0.1\nB\n") for stage in metrics.STAGES}
        self.write_stage("fixed_pre", "A\nB\n")
        self.write_stage("fixed_post", "A\nB\n")
        with patch.object(metrics, "native_identifiers", return_value=(("A", "B", "C"), ("A", "B"))):
            with self.assertRaisesRegex(ValueError, "clearly above"):
                metrics.validate_arm_stages(self.plan, "legacy", 1, paths)

    def test_parser_rejects_duplicate_self_unknown_nonfinite_negative_and_truncation(self):
        for body in ("A\tB\t1\tB\t2\n", "A\tA\t1\n", "A\tZ\t1\n", "A\tB\tnan\n", "A\tB\t-1\n", "A\tB\t0\n", "A\tB\t1", "A\tB\n", "A\nA\n"):
            path = self.root / "invalid.adj"
            path.write_text(body)
            with self.subTest(body=body), self.assertRaises(ValueError):
                metrics.parse_adjacency(path, ("A", "B", "C"), ("A", "B"))

    def test_bad_header_cutoff_sampling_or_DPI_rejected(self):
        for old, new in (("MI P-value 1", "MI P-value 0.1"), ("DPI tolerance 1", "DPI tolerance 0"),
                         ("Resample draws 5", "Resample draws 4"), ("Subnetwork file /mnt/d/hubs.txt", "Subnetwork file /mnt/d/other.txt")):
            path = self.write_stage("raw")
            file = path / "raw.adj"
            file.write_text(file.read_text().replace(old, new))
            with patch.object(metrics, "native_identifiers", return_value=(("A", "B", "C"), ("A", "B"))):
                with self.assertRaises(ValueError):
                    metrics.validate_job_output(file, path / "stdout.log", plan=self.plan, arm="legacy", stage="raw")


class AggregationTests(unittest.TestCase):
    def cohort(self):
        results = []
        for arm in metrics.ARMS:
            for seed in (1, 2, 3):
                scalar = {"edges_all": 0, "edges_explicit_labelled": 0, "edges_unlabelled": 0,
                          "TP": 0, "FP": 0, "precision": None, "sensitivity": 0., "specificity": 1.,
                          "AUROC_fixed_explicit_universe_MI_ties": .5,
                          "average_precision_fixed_explicit_universe": .02 if arm == "u80" else .01}
                pruning = {key: None for key in ("global_pruning_fraction", "labelled_pruning_fraction", "TP_pruned", "FP_pruned", "TP_pruning_fraction", "FP_pruning_fraction")}
                results.append({"arm": arm, "seed": seed, "stages": {stage: dict(scalar) for stage in metrics.STAGES},
                                "DPI_pruning": {prefix: dict(pruning) for prefix in ("nominal", "fixed")}})
        return results

    def test_primary_endpoint_paired_and_empty_precision_preserved(self):
        summary = metrics.aggregate(self.cohort())
        self.assertEqual(summary["matched_seeds"], 3)
        self.assertEqual(summary["primary_after_higher"], 3)
        self.assertAlmostEqual(summary["primary_paired_AP_delta_median"], .01)
        self.assertIsNone(summary["medians"]["legacy"]["nominal_post"]["precision"])

    def test_missing_duplicate_or_noninteger_seed_rejected(self):
        for cohort in (self.cohort()[:-1], self.cohort() + [self.cohort()[0]]):
            with self.assertRaises(ValueError):
                metrics.aggregate(cohort)
        cohort = self.cohort()
        cohort[0]["seed"] = True
        with self.assertRaises(ValueError):
            metrics.aggregate(cohort)


if __name__ == "__main__":
    unittest.main()
