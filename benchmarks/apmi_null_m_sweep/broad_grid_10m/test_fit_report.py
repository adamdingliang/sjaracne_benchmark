"""Synthetic atom counts, exact intervals and honest denominator tests."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import unittest

import numpy as np
from scipy.stats import beta

SPEC = importlib.util.spec_from_file_location("broad_fit_report", Path(__file__).with_name("fit_report.py"))
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def prediction(p=0.001, cutoff=0.1, m=450, **kwargs):
    result = {"m": m, "p": p, "available": True, "cutoff": cutoff, "reason": None}
    result.update(kwargs)
    return result


class ScoringTests(unittest.TestCase):
    def test_atoms_and_adjacent_floats(self):
        threshold = 0.1
        lower, upper = np.nextafter(threshold, -np.inf), np.nextafter(threshold, np.inf)
        values = np.asarray([0, lower, threshold, threshold, upper, 0.2], dtype=np.float64)
        row = report.score_predictions(values, [prediction(cutoff=threshold)], "pchip", "internal")[0]
        self.assertEqual((row["n"], row["count"], row["gt"], row["ties"]), (6, 4, 2, 2))
        self.assertEqual((row["minus_ulp_ge"], row["plus_ulp_ge"]), (5, 2))
        self.assertEqual(row["cutoff_hex"], threshold.hex())
        self.assertEqual(row["zero_count"], 1)
        self.assertEqual(row["unique_count"], 5)

    def test_exact_CP_reference(self):
        values = np.asarray([0, 0, 0.1, 0.2], dtype=np.float64)
        row = report.score_predictions(values, [prediction()], "quadratic", "development")[0]
        self.assertEqual(row["point_lower"], float(beta.ppf(0.0005, 2, 3)))
        self.assertEqual(row["point_upper"], float(beta.ppf(0.9995, 3, 2)))
        self.assertEqual(row["actual"], 0.5)
        self.assertEqual(row["ratio"], 500)
        self.assertEqual(row["relative_error"], 499)

    def test_zero_and_all_counts_endpoints(self):
        values = np.asarray([0, 0.1, 0.2], dtype=np.float64)
        rows = report.score_predictions(values, [prediction(cutoff=1), prediction(cutoff=0)], "pchip", "development")
        self.assertEqual(rows[0]["count"], 0)
        self.assertEqual(rows[0]["point_lower"], 0)
        self.assertEqual(rows[1]["count"], 3)
        self.assertEqual(rows[1]["point_upper"], 1)
        self.assertEqual(rows[1]["engine_zero_omission_count"], 2)

    def test_simultaneous_only_single_primary_final_eight(self):
        values = np.asarray([0, 0.1, 0.2], dtype=np.float64)
        for primary, phase in ((False, "final_validation"), (True, "development")):
            row = report.score_predictions(values, [prediction()], "quadratic", phase, primary=primary)[0]
            self.assertIsNone(row["simultaneous_lower"])
            self.assertIsNone(row["classification"])
        rows = report.score_predictions(values, [prediction(), prediction(p=0.002)], "pchip", "final_validation", primary=True)
        self.assertTrue(rows[0]["simultaneous_applicable"])
        self.assertEqual(rows[0]["simultaneous_lower"], float(beta.ppf(0.01 / 1600 / 2, 2, 2)))
        self.assertIsNone(rows[1]["simultaneous_lower"])
        self.assertFalse(rows[1]["simultaneous_applicable"])

    def test_unavailable_preserved_and_primary_class_invalid(self):
        values = np.asarray([0, 0.1], dtype=np.float64)
        rows = report.score_predictions(values, [prediction(available=False, cutoff=None, reason="crossed")],
                                        "pchip", "final_validation", primary=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "crossed")
        self.assertIsNone(rows[0]["count"])
        self.assertEqual(rows[0]["classification"], "invalid")
        json.dumps(rows, allow_nan=False)

    def test_invalid_numeric_prediction_is_JSON_safe(self):
        values = np.asarray([0, 0.1], dtype=np.float64)
        for item in (prediction(cutoff=float("nan")), prediction(p=float("nan")), prediction(m=float("nan")),
                     prediction(cutoff=-0.1), prediction(cutoff=math.log(450) + 1)):
            row = report.score_predictions(values, [item], "pchip", "development")[0]
            self.assertFalse(row["available"])
            json.dumps(row, allow_nan=False)

    def test_non_sorted_or_nonfloat_arrays_rejected(self):
        for values in (np.asarray([0.1, 0.0]), np.asarray([0, 1], dtype=int), np.asarray([], dtype=float),
                       np.asarray([0.0, np.nan]), np.asarray([-0.1, 0.0])):
            with self.assertRaises(ValueError):
                report.score_predictions(values, [prediction()], "pchip", "development")

    def test_empty_predictions(self):
        self.assertEqual(report.score_predictions(np.asarray([0.0]), [], "pchip", "development"), [])

    def test_simultaneous_interval_is_wider_than_pointwise(self):
        values = np.asarray([0, 0.1, 0.2], dtype=np.float64)
        row = report.score_predictions(values, [prediction()], "pchip", "final_validation", primary=True)[0]
        self.assertLess(row["simultaneous_lower"], row["point_lower"])
        self.assertGreater(row["simultaneous_upper"], row["point_upper"])

    def test_numpy_scalar_prediction_serializes_and_source_is_unchanged(self):
        values = np.asarray([0.0, 0.1])
        supplied = prediction(m=np.int64(450), p=np.float64(0.001), cutoff=np.float64(0.1))
        rows = report.score_predictions(values, [supplied], "pchip", "development")
        json.dumps(rows, allow_nan=False)
        self.assertNotIn("count", supplied)

    def test_invalid_labels_and_primary(self):
        values = np.asarray([0.0])
        for method, phase, primary in (("", "development", False), ("pchip", "", False), ("pchip", "development", 1)):
            with self.assertRaises(ValueError):
                report.score_predictions(values, [prediction()], method, phase, primary)

    def test_interval_classification_confirmed_inconsistent_unresolved(self):
        values = np.linspace(0, 1, 1_000_000, dtype=np.float64)
        rows = report.score_predictions(values, [prediction(p=0.05, cutoff=0.95),
                                                 prediction(p=0.01, cutoff=0.5),
                                                 prediction(p=1e-7, cutoff=1.1)],
                                        "pchip", "final_validation", primary=True)
        self.assertEqual([row["classification"] for row in rows], ["confirmed", "inconsistent", "unresolved"])


class SummaryTests(unittest.TestCase):
    def rows(self, m=450):
        return [{"method": "pchip", "phase": "development", "m": m, "p": p,
                 "available": True, "relative_error": 0.01, "classification": None}
                for p in report.ALL_P]

    def item(self, summaries, pscope="core_four", m_group="all"):
        return next(row for row in summaries if row["pscope"] == pscope and row["m_group"] == m_group)

    def test_fixed_development_denominator_does_not_drop_missing(self):
        summary = self.item(report.summarize(self.rows()))
        self.assertEqual(summary["total"], 80)
        self.assertEqual(summary["available"], 4)
        self.assertEqual(summary["missing"], 76)
        self.assertEqual(summary["within10_fraction"], 4 / 80)
        self.assertEqual(summary["error_stat_denominator"], 4)

    def test_explicit_frozen_subset_denominator(self):
        summary = self.item(report.summarize(self.rows(), expected_m=[450]))
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["within10_count"], 4)
        self.assertEqual(summary["within10_fraction"], 1)
        self.assertEqual(summary["classes"], {"not_applicable": 4})

    def test_invalid_duplicate_count_as_nonpasses(self):
        rows = self.rows()
        rows[0]["available"] = False
        rows.append(dict(rows[report.ALL_P.index(0.001)]))
        summary = self.item(report.summarize(rows, expected_m=[450]))
        self.assertEqual(summary["invalid"], 2)
        self.assertEqual(summary["duplicate_cells"], 1)
        self.assertEqual(summary["available"], 2)
        self.assertEqual(summary["within10_fraction"], 0.5)

    def test_unknown_phase_does_not_use_observed_only_denominator(self):
        rows = [dict(row, phase="diagnostic") for row in self.rows()]
        summary = self.item(report.summarize(rows))
        self.assertEqual(summary["total"], 800)
        self.assertEqual(summary["missing"], 796)

    def test_out_of_grid_rows_remain_visible(self):
        rows = self.rows() + [dict(self.rows()[0], p=None)]
        summary = self.item(report.summarize(rows, expected_m=[450]))
        self.assertEqual(summary["out_of_grid_rows"], 1)

    def test_all_scopes_and_groups(self):
        rows = [dict(row, phase="final_validation") for row in self.rows(m=350)]
        summaries = report.summarize(rows)
        self.assertEqual(len(summaries), 16)
        self.assertEqual(self.item(summaries, "all_49")["total"], 9800)
        self.assertEqual(self.item(summaries, "primary_eight")["total"], 1600)
        self.assertEqual(self.item(summaries, "core_four", "final_interpolation_test")["total"], 80)

    def test_classes_preserved(self):
        rows = self.rows()
        for p, label in zip(report.CORE_P, ("confirmed", "inconsistent", "unresolved", "invalid")):
            row = rows[report.ALL_P.index(p)]
            row["classification"] = label
            row["available"] = label != "invalid"
        summary = self.item(report.summarize(rows, expected_m=[450]))
        self.assertEqual(summary["classes"], {"confirmed": 1, "inconsistent": 1, "invalid": 1, "unresolved": 1})

    def test_invalid_expected_grid_and_rows(self):
        for expected in ([], [50, 50], [30], [True], [50.0]):
            with self.assertRaises(ValueError):
                report.summarize(self.rows(), expected_m=expected)
        with self.assertRaises(ValueError):
            report.summarize([{"p": 0.001}])

    def test_empty_summary(self):
        self.assertEqual(report.summarize([]), [])


if __name__ == "__main__":
    unittest.main()
