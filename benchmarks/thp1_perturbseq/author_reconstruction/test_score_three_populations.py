"""Small independent tests for the additive three-population scorer."""

import argparse
import json
from pathlib import Path
import tempfile
import unittest

from sklearn.metrics import roc_auc_score

import score_fixed_universe as fixed
import score_three_populations as module
import test_score_fixed_universe as fixtures


class PopulationMathTests(unittest.TestCase):
    def test_conditional_auc_and_denominators(self):
        scores, labels = [1, .5, .5, 0], [True, True, False, False]
        groups = fixed.group_scores(scores, labels)
        emitted = module.population_metrics(groups, 2, 2, 10, 20, [1, 2, 4, 5], "eligible_emitted")
        universe = module.population_metrics(groups, 10, 20, 10, 20, [1, 2, 4, 5], "fixed_eligible_universe")
        self.assertAlmostEqual(emitted["AUROC_MI_ties"], roc_auc_score(labels, scores))
        self.assertAlmostEqual(universe["AUROC_MI_ties"], roc_auc_score(labels + [True]*8 + [False]*18, scores + [-1]*26))
        k2 = emitted["top_k"][1]
        self.assertEqual(k2["TP_tie_expected"], 1.5)
        self.assertEqual((k2["TP_min"], k2["TP_max"]), (1, 2))
        self.assertEqual(k2["sensitivity_within_population_at_k"], .75)
        self.assertEqual(k2["fixed_reference_sensitivity_at_k"], .15)
        self.assertEqual(k2["random_TP_expectation_at_k"], 1)
        self.assertEqual(k2["precision_lift_over_random_expectation"], 1.5)
        self.assertEqual(universe["top_k"][1]["random_TP_expectation_at_k"], 2/3)
        self.assertEqual(emitted["top_k"][-1]["status"], "exceeds_emitted_pairs")
        self.assertEqual(universe["top_k"][-1]["status"], "exceeds_emitted_pairs")
        self.assertEqual(emitted["fixed_reference_sensitivity_all_emitted"], .2)

    def test_full_pool_not_given_fixed_specificity(self):
        result = module.population_metrics([(1, 1, 1)], 1, 1, 10, 20, [1], "full_emitted")
        self.assertNotIn("fixed_reference_specificity_at_k", result["top_k"][0])
        self.assertEqual(result["role"], "secondary")

    def test_invalid_k(self):
        for k in (0, -1):
            with self.assertRaises(ValueError):
                module.population_metrics([(1, 1, 1)], 1, 1, 10, 20, [k], "eligible_emitted")


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProvenanceIntegrationTests()
        self.fixture.setUp()
        fixed.calculate(self.fixture.args)
        self.args = argparse.Namespace(fixed_metrics=self.fixture.args.out / "metrics.json",
                                       prepared_dir=self.fixture.prepared, run_manifest=self.fixture.run_path,
                                       out=self.fixture.root / "three_populations", top_k=[1, 2, 3, 4, 5])

    def tearDown(self):
        self.fixture.tearDown()

    def test_all_three_populations_and_immutable_inputs(self):
        before = {str(p): fixed.digest(p) for p in self.fixture.root.rglob("*") if p.is_file()}
        result = module.calculate(self.args)
        scores = result["scores"]["consensus_pc1e-02"]["populations"]
        self.assertEqual(result["primary_population"], "eligible_emitted")
        self.assertEqual([scores[p]["candidate_pairs"] for p in module.POPULATIONS], [3, 4, 4])
        self.assertEqual(scores["eligible_emitted"]["AUROC_MI_ties"], .5)
        self.assertEqual(scores["full_emitted"]["AUROC_MI_ties"], .25)
        self.assertEqual(scores["fixed_eligible_universe"]["AUROC_MI_ties"], .75)
        for p in module.POPULATIONS:
            self.assertEqual(scores[p]["fixed_reference_sensitivity_all_emitted"], 1)
        self.assertEqual({path: fixed.digest(Path(path)) for path in before}, before)
        self.assertTrue((self.args.out / "REPORT.md").is_file())
        self.assertEqual(json.loads((self.args.out / "metrics.json").read_text())["status"], "complete")
        with self.assertRaises(FileExistsError):
            module.calculate(self.args)

    def test_reject_tampered_reference(self):
        with (self.fixture.prepared / "reference_positive_edges.tsv").open("a") as stream:
            stream.write("A\tC\n")
        with self.assertRaisesRegex(ValueError, "Input hash mismatch"):
            module.calculate(self.args)
        self.assertFalse(self.args.out.exists())

    def test_reject_changed_saved_report(self):
        (self.fixture.args.out / "REPORT.md").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Input hash mismatch"):
            module.calculate(self.args)

    def test_reject_unbound_run(self):
        run_copy = self.fixture.root / "other_run.json"
        run_copy.write_text(self.fixture.run_path.read_text())
        self.args.run_manifest = run_copy
        with self.assertRaisesRegex(ValueError, "not bound"):
            module.calculate(self.args)

    def test_grouping_validation(self):
        universe = fixed.make_universe(self.fixture.prepared)
        full, eligible = module.network_groups(self.fixture.network, universe, {"A", "B", "C"})
        self.assertEqual(sum(p+n for _, p, n in full), 4)
        self.assertEqual(sum(p+n for _, p, n in eligible), 3)
        for extra in (["A", "B", .3], ["A", "A", .3], ["A", "D", .3], ["A", "C", "nan"]):
            self.fixture.tsv(self.fixture.network, [["source", "target", "MI"], ["A", "B", .3], extra])
            with self.assertRaises(ValueError):
                module.network_groups(self.fixture.network, universe, {"A", "B", "C"})


if __name__ == "__main__":
    unittest.main()
