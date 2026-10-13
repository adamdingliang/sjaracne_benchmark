"""Small checks that plotting cannot change EPR/ROC population definitions."""

import unittest

from plot_eligible_fig6a import eligible_roc, validate_ranked


class PlotDefinitionsTest(unittest.TestCase):
    def rows(self):
        return [{"k": "1000", "TP": "600", "Random_TP": "500", "EPR_R_seed1_shuffle": "1.2"},
                {"k": "1500", "TP": "750", "Random_TP": "750", "EPR_R_seed1_shuffle": "1"}]

    def test_ranked_endpoint_and_no_epr_origin(self):
        curve = validate_ranked(self.rows(), 1500, 750)
        self.assertEqual(curve["k"], [1000, 1500])
        self.assertEqual(curve["EPR"], [1.2, 1])

    def test_mismatched_ratio_rejected(self):
        rows = self.rows()
        rows[0]["EPR_R_seed1_shuffle"] = "1.3"
        with self.assertRaises(ValueError):
            validate_ranked(rows, 1500, 750)

    def test_no_padding_or_missing_checkpoints(self):
        with self.assertRaises(ValueError):
            validate_ranked(self.rows(), 2000, 750)

    def test_mi_ties_get_half_credit(self):
        auc, curve = eligible_roc([(0.2, 1, 1), (0.1, 1, 1)], 2, 2, .5)
        self.assertEqual(auc, .5)
        self.assertEqual(len(curve), 3)
        self.assertEqual([r["threshold_kind"] for r in curve], ["above_all", "emitted_MI", "emitted_MI"])
        self.assertEqual((curve[-1]["FPR"], curve[-1]["sensitivity"]), (1, 1))

    def test_fixed_universe_denominators_rejected(self):
        with self.assertRaises(ValueError):
            eligible_roc([(0.2, 1, 1)], 100, 100, .5)

    def test_wrong_auc_rejected(self):
        with self.assertRaises(ValueError):
            eligible_roc([(0.2, 1, 0), (0.1, 0, 1)], 1, 1, .5)


if __name__ == "__main__":
    unittest.main()
