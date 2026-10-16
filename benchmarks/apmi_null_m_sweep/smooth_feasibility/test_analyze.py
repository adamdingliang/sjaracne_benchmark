"""Synthetic-only checks; no real streams, simulations or engine invocation."""
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import analyze


def synthetic_items():
    items = []
    for m in analyze.GRID:
        items.append({"m": m, "quantiles": [
            {"nominal_p": p, "cutoff": .2/math.sqrt(m)*math.log(1/p)**.4}
            for p in analyze.ALL_P],
            "primary_fit": {"threshold": .1/math.sqrt(m), "scale": .01/math.sqrt(m),
                            "shape": .05, "tail_probability": .00499}})
    return items


class AnalyzeTests(unittest.TestCase):
    def test_entire_size_left_out_and_p_roles(self):
        predictions = analyze.prediction_specs(synthetic_items())
        self.assertEqual(len(predictions), 19*16*8)
        for row in predictions:
            if row["smoother"]:
                self.assertEqual(len(row["train_m"]), 18)
                self.assertNotIn(row["m"], row["train_m"])
            else:
                self.assertEqual(row["train_m"], [row["m"]])
            self.assertEqual(row["p_role"], "knot" if row["nominal_p"] in analyze.KNOT_P else "probe")

    def test_omitted_quantiles_and_parameters_cannot_change_prediction(self):
        original = synthetic_items()
        changed = synthetic_items()
        omitted_m = 300
        target = next(item for item in changed if item["m"] == omitted_m)
        for row in target["quantiles"]:
            row["cutoff"] *= 2
        target["primary_fit"]["shape"] = -.5
        first = [row for row in analyze.prediction_specs(original) if row["m"] == omitted_m and row["smoother"]]
        second = [row for row in analyze.prediction_specs(changed) if row["m"] == omitted_m and row["smoother"]]
        self.assertEqual([row["cutoff"] for row in first], [row["cutoff"] for row in second])
        self.assertEqual([row["predicted_parameters"] for row in first], [row["predicted_parameters"] for row in second])

    def test_endpoint_pchip_not_filled_and_gpd_body_unavailable(self):
        rows = analyze.prediction_specs(synthetic_items())
        for row in rows:
            if row["m"] in (30, 1000) and row["smoother"] == "pchip":
                self.assertEqual(row["status"], "unavailable")
                self.assertIsNone(row["cutoff"])
            if row["family"] in ("gpd", "gpd_exact_m") and row["nominal_p"] in (.05,.02,.01,.005):
                self.assertEqual(row["status"], "unavailable")

    def test_cp_boundaries_and_classification(self):
        self.assertEqual(analyze.cp_interval(0, 10)[0], 0)
        self.assertEqual(analyze.cp_interval(10, 10)[1], 1)
        self.assertEqual(analyze.classify_interval(.00095,.00105,.001), "pointwise_interval_inside_10pct_band")
        self.assertEqual(analyze.classify_interval(.0012,.0013,.001), "pointwise_interval_disjoint_from_10pct_band")
        self.assertEqual(analyze.classify_interval(.0008,.0011,.001), "unresolved_pointwise")
        with self.assertRaises(ValueError):
            analyze.cp_interval(11,10)

    def test_scoring_comparator_ties_and_denominator(self):
        prediction = {"m": 100, "method": "quantile_loglinear", "family": "quantile",
            "smoother": "loglinear", "fold_kind": "interior_interpolation", "nominal_p": .5,
            "p_role": "knot", "cutoff": .2, "empirical_cutoff": .25, "status": "valid",
            "invalid_reason": None, "train_m": [50,200], "predicted_parameters": None}
        items = [{"m":100, "sorted_cache": {stream:{"path": "synthetic"} for stream in ("fit","validation")}}]
        with patch.object(analyze,"GRID",[100]), patch.object(analyze.np,"load",return_value=np.array([0.,.1,.2,.2,.3])):
            rows = analyze.score_predictions([prediction], items)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual((row["ge"],row["gt"],row["ties"],row["draws"]), (3,1,2,5))
            self.assertAlmostEqual(row["actual_nominal"],1.2)
            self.assertAlmostEqual(row["relative_cutoff_error"],-.2)

    def test_summary_preserves_invalid_denominator(self):
        base = {"stream":"validation", "method":"test", "fold_kind":"interior_interpolation",
                "nominal_p":.001, "p_role":"knot", "status":"valid", "relative_null_rate_error":.05,
                "pointwise_classification":"unresolved_pointwise"}
        rows = [base, dict(base,status="unavailable",relative_null_rate_error=None)]
        summary = next(row for row in analyze.summarize(rows) if row["group"] == "primary_interior")
        self.assertEqual((summary["total_checks"],summary["valid_checks"],summary["unavailable_checks"]),(2,1,1))
        self.assertEqual(summary["observed_within_10pct"],1)

    def test_finite_physical_support_no_clipping(self):
        for value in (-.1,math.log(100)+.1,float("nan"),float("inf")):
            with self.assertRaises(ValueError):
                analyze.valid_cutoff(value,100)
        self.assertEqual(analyze.valid_cutoff(0,100),0)


if __name__ == "__main__":
    unittest.main()
