"""Synthetic checks for raw-MI report aggregation; no scientific inference."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("raw_mi_report", Path(__file__).with_name("report.py"))
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def score(arm: str, seed: int, tp: float, auc: float = .6) -> dict:
    def row(k: int, true_positive: float) -> dict:
        precision = true_positive / k if k else None
        return {
            "k": k, "TP_tie_expected": true_positive,
            "TP_min": int(true_positive), "TP_max": int(true_positive + .99),
            "FP_tie_expected": k - true_positive,
            "precision_tie_expected": precision,
            "sensitivity_tie_expected": true_positive / 2000,
            "specificity_tie_expected": 1 - (k - true_positive) / 8000,
            "FPR_tie_expected": (k - true_positive) / 8000,
            "random_TP_expectation_at_k": k * .2,
            "EPR_tie_expected": precision / .2 if k else None,
            "boundary_MI": .1, "boundary_group_size": 2, "split_MI_tie": True,
        }
    return {
        "arm": arm, "seed": seed, "status": "complete", "candidate_pairs": 10000,
        "reference_positive_pairs": 2000, "reference_negative_pairs": 8000,
        "random_positive_fraction": .2, "AUROC_MI_ties": auc,
        "AUROC_ROC_integral_check": auc,
        "top_k": [row(1000, tp / 5), row(5000, tp)],
        "curve": [row(0, 0), row(1000, tp / 5), row(5000, tp), row(10000, 2000)],
    }


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"seeds": [2, 4]}
        self.results = [score("before", 2, 1000), score("before", 4, 1100),
                        score("after", 2, 1050, .61), score("after", 4, 1200, .63)]

    def test_percentile_linear_and_single(self):
        self.assertEqual(report.percentile([1, 3], .25), 1.5)
        self.assertEqual(report.percentile([7], .75), 7)
        with self.assertRaises(ValueError):
            report.percentile([], .5)

    def test_paired_summary_and_direction(self):
        summary, rows = report.aggregate_results(self.results, self.plan)
        self.assertEqual(summary["primary_TP_direction_counts"], {"higher": 2, "lower": 0, "unchanged": 0})
        self.assertEqual(summary["top_k"]["5000"]["TP"]["paired_delta"]["median"], 75)
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["delta_FP"] == -row["delta_TP"] for row in rows))
        self.assertAlmostEqual(summary["AUROC"]["paired_delta"]["median"], .02)

    def test_mixed_direction_not_called_improvement(self):
        self.results[2] = score("after", 2, 900)
        summary, _ = report.aggregate_results(self.results, self.plan)
        self.assertIn("mixed", summary["descriptive_conclusion"])
        self.assertEqual(summary["primary_TP_direction_counts"]["lower"], 1)

    def test_all_lower_and_equal_directions(self):
        for delta, expected in ((-10, "lower"), (0, "unchanged")):
            results = [score("before", 2, 1000), score("after", 2, 1000 + delta)]
            summary, _ = report.aggregate_results(results, {"selected_seeds": [2]})
            self.assertIn(expected, summary["descriptive_conclusion"])

    def test_refuses_missing_duplicate_extra_and_incomplete(self):
        cases = [self.results[:-1], self.results + [self.results[0]],
                 self.results + [score("after", 5, 1200)]]
        incomplete = copy.deepcopy(self.results)
        incomplete[0]["status"] = "running"
        cases.append(incomplete)
        for results in cases:
            with self.subTest(count=len(results)):
                with self.assertRaises(ValueError):
                    report.aggregate_results(results, self.plan)

    def test_refuses_changed_universe_or_epr(self):
        for key, value in (("candidate_pairs", 10001), ("random_positive_fraction", .21)):
            changed = copy.deepcopy(self.results)
            changed[-1][key] = value
            with self.assertRaises(ValueError):
                report.aggregate_results(changed, self.plan)
        changed = copy.deepcopy(self.results)
        changed[-1]["top_k"][0]["EPR_tie_expected"] = 99
        with self.assertRaises(ValueError):
            report.aggregate_results(changed, self.plan)

    def test_refuses_changed_grids_and_missing_primary(self):
        for which in ("top_k", "curve"):
            changed = copy.deepcopy(self.results)
            changed[-1][which].pop()
            with self.assertRaises(ValueError):
                report.aggregate_results(changed, self.plan)
        with self.assertRaises(ValueError):
            report.aggregate_results(self.results, self.plan, primary_k=123)

    def test_report_cautions_and_no_significance_claim(self):
        summary, _ = report.aggregate_results(self.results, self.plan)
        text = report.report_markdown(summary)
        for phrase in ("121 draws", "97 distinct", "not independent biological replicates",
                       "not an exact reproduction", "not proven biological", "approximately six significant",
                       "not the difference of marginal medians", "no significance claim", "Existing unfavorable"):
            self.assertIn(phrase, text)

    def test_compact_outputs_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "report"
            summary = report.build_report(self.results, self.plan, out, plots=False)
            self.assertEqual(set(path.name for path in out.iterdir()), {"REPORT.md", "summary.json", "paired_seed_metrics.tsv"})
            self.assertFalse(summary["plots_generated"])
            self.assertEqual(json.loads((out / "summary.json").read_text())["n_matched_seeds"], 2)
            self.assertIn("Plot generation was disabled", (out / "REPORT.md").read_text())
            with self.assertRaises(FileExistsError):
                report.build_report(self.results, self.plan, out, plots=False)

    def test_plot_smoke(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "report"
            report.build_report(self.results, self.plan, out)
            self.assertGreater((out / "raw_mi_comparison.png").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
