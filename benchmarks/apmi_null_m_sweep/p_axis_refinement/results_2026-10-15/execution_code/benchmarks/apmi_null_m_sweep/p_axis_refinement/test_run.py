"""Synthetic-only fold, interpolation, summary and regression checks."""
from copy import deepcopy
import csv
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import grid
import run


def synthetic_items():
    return [{"m":m,"quantiles":[{"nominal_p":p,"cutoff":.3*math.log(1/p)**.3/m**.7}
                                for p in grid.ALL_P]} for m in grid.GRIDM]


class RefinementTests(unittest.TestCase):
    def test_all_sizes_methods_and_roles_retained(self):
        rows, diagnostics = run.prediction_specs(synthetic_items())
        self.assertEqual(len(rows),19*49*9)
        self.assertEqual(len(diagnostics),19*9)
        for row in rows:
            self.assertEqual(row["new_probe"],row["nominal_p"] in grid.NEW_PROBE_P)
            if row["smoother"]:
                self.assertNotIn(row["m"],row["train_m"])
                self.assertEqual(len(row["train_m"]),18)
            else:
                self.assertEqual(row["train_m"],[row["m"]])

    def test_no_own_m_training_leakage(self):
        first=synthetic_items()
        second=deepcopy(first)
        for quantile in next(item for item in second if item["m"] == 300)["quantiles"]:
            quantile["cutoff"] *= 2
        one,_=run.prediction_specs(first)
        two,_=run.prediction_specs(second)
        select=lambda rows:[r["cutoff"] for r in rows if r["m"] == 300 and r["smoother"]]
        self.assertEqual(select(one),select(two))

    def test_endpoint_no_extrapolation_and_baselines_remain_available(self):
        rows,_=run.prediction_specs(synthetic_items())
        for row in rows:
            if row["m"] in (30,1000) and row["smoother"] == "pchip":
                self.assertEqual(row["status"],"unavailable")
                self.assertEqual(row["invalid_reason"],"outside_training_m_range_no_extrapolation")
            if not row["smoother"]:
                self.assertEqual(row["status"],"valid")

    def test_crossing_rejects_whole_fold_without_repair(self):
        def crossed(train_m,values,m,method):
            return np.linspace(3.,1.,values.shape[1])
        with patch.object(run.models,"predict_quantiles",side_effect=crossed):
            rows,diagnostics=run.prediction_specs(synthetic_items())
        candidates=[row for row in rows if row["smoother"]]
        self.assertTrue(all(row["status"] == "unavailable" for row in candidates))
        self.assertTrue(any(d["crossings"] for d in diagnostics))
        self.assertTrue(all(row["status"] == "valid" for row in rows if not row["smoother"]))

    def test_diagnostics_record_adjacent_crossings(self):
        diagnostic=run.diagnose_knots([.1,.01,.001],[1.,3.,2.])
        self.assertEqual(diagnostic["crossings"],[{"smaller_p":.001,"larger_p":.01,
            "smaller_p_cutoff":2.,"larger_p_cutoff":3.}])

    def test_summary_masks_and_full_invalid_denominator(self):
        predictions,_=run.prediction_specs(synthetic_items())
        for row in predictions:
            row.update(stream="validation",relative_null_rate_error=.01,
                       pointwise_classification="unresolved_pointwise")
        target=next(row for row in predictions if row["method"] == "dense_logquadratic" and
                    row["new_probe"] and row["moderate"] and row["fold_kind"] == "interior_interpolation")
        target.update(status="unavailable",relative_null_rate_error=None)
        summaries=run.summarize(predictions)
        item=next(r for r in summaries if r["group"] == "main_new_probes" and r["method"] == "dense_logquadratic")
        self.assertEqual((item["total_checks"],item["valid_checks"],item["observed_within_10pct"]),(272,271,271))
        self.assertAlmostEqual(item["within_fraction_full_denominator"],271/272)
        other=next(r for r in summaries if r["group"] == "all_new_probes_to_1e_minus4" and r["method"] == "coarse_loglinear")
        self.assertEqual(other["total_checks"],357)
        primary=next(r for r in summaries if r["group"] == "operating_probabilities" and r["method"] == "dense_logquadratic")
        self.assertEqual(primary["total_checks"],34)

    def test_same_source_threshold_and_counts_reproduce_then_tamper_fails(self):
        rows=[]
        for m in grid.GRIDM:
            for p in grid.OLD_QUERY_P:
                for method in grid.SMOOTHERS:
                    for stream in ("fit","validation"):
                        rows.append({"m":m,"nominal_p":p,"method":"coarse_"+method,"stream":stream,
                                     "old_query":True,"status":"valid","cutoff":.1,"ge":5,"gt":4,"ties":1,"draws":10})
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"evaluation.csv"
            old=[dict(row,method=row["method"].replace("coarse_","quantile_")) for row in rows]
            with path.open("w",newline="",encoding="utf-8") as handle:
                writer=csv.DictWriter(handle,fieldnames=list(old[0]))
                writer.writeheader()
                writer.writerows(old)
            result=run.check_regression(rows,Path(temp))
            self.assertTrue(result["passed"])
            self.assertEqual(result["compared_rows"],1824)
            rows[0]["ge"]=6
            self.assertFalse(run.check_regression(rows,Path(temp))["passed"])


if __name__ == "__main__":
    unittest.main()
