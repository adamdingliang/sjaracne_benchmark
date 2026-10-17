"""Synthetic fitting/selection tests; no scientific raw file is accessed."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location("broad_fit_models", Path(__file__).with_name("fit_models.py"))
fit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fit)


def fixture(ms=(50, 100, 200, 500, 1000, 5000, 10000)):
    ms = np.asarray(ms, dtype=float)
    # Positive, noncrossing and comfortably inside the physical support.
    qs = np.asarray([[0.01 * (m / 50) ** -0.5 * (-math.log(p)) for p in fit.P_KNOTS] for m in ms])
    return ms, qs


def counts():
    return [{"m": m, "p": p, "count": round(p * 10000000), "n": 10000000}
            for m in fit.DEVELOPMENT_M for p in fit.SELECTION_P]


class SurfaceTests(unittest.TestCase):
    def test_frozen_grid_shape(self):
        self.assertEqual(len(fit.P_KNOTS), 25)
        self.assertEqual(sum(p >= 0.0001 for p in fit.P_KNOTS), 22)

    def test_known_power_function_quadratic(self):
        ms, qs = fixture()
        model = fit.fit_surface(ms, qs)
        for m in (50, 80, 450, 644, 725, 6000, 10000):
            result = fit.predict_surface(model, m, fit.P_KNOTS)
            for row in result:
                self.assertTrue(row["available"], row)
                exact = 0.01 * (m / 50) ** -0.5 * (-math.log(row["p"]))
                self.assertAlmostEqual(row["cutoff"], exact, places=13)

    def test_quadratic_known_curvature(self):
        ms, qs = fixture()
        xs = (np.log(ms) - math.log(50)) / (math.log(10000) - math.log(50))
        qs *= np.exp(0.15 * xs * xs)[:, None]
        model = fit.fit_surface(ms, qs)
        row = fit.predict_surface(model, 644, [0.001])[0]
        x = (math.log(644) - math.log(50)) / (math.log(10000) - math.log(50))
        expected = 0.01 * (644 / 50) ** -0.5 * (-math.log(0.001)) * math.exp(0.15 * x * x)
        self.assertAlmostEqual(row["cutoff"], expected, places=13)

    def test_pchip_literal_exact_m_and_p_bit_preservation(self):
        ms, qs = fixture()
        qs[2, 10] = np.nextafter(qs[2, 10], np.inf)
        model = fit.fit_surface(ms, qs, "pchip")
        for i, m in enumerate(ms):
            rows = fit.predict_surface(model, m, fit.P_KNOTS)
            self.assertEqual([r["cutoff_hex"] for r in rows], [float(t).hex() for t in qs[i]])

    def test_pchip_known_linear_log_function(self):
        ms, qs = fixture()
        model = fit.fit_surface(ms, qs, "pchip")
        rows = fit.predict_surface(model, 725, fit.P_KNOTS)
        for row in rows:
            exact = 0.01 * (725 / 50) ** -0.5 * (-math.log(row["p"]))
            self.assertAlmostEqual(row["cutoff"], exact, places=13)

    def test_json_roundtrip(self):
        ms, qs = fixture()
        for method in fit.METHODS:
            model = fit.fit_surface(ms, qs, method)
            recovered = json.loads(json.dumps(model, allow_nan=False))
            self.assertEqual(fit.predict_surface(model, 725, fit._GRID.ALL_P),
                             fit.predict_surface(recovered, 725, fit._GRID.ALL_P))

    def test_quadratic_never_overrides_observed_knot(self):
        ms, qs = fixture()
        qs[2] *= 1.2
        model = fit.fit_surface(ms, qs, "quadratic")
        row = fit.predict_surface(model, ms[2], [0.001])[0]
        self.assertNotEqual(row["cutoff_hex"], float(qs[2, fit.P_KNOTS.index(0.001)]).hex())

    def test_exact_p_returns_predicted_literal_without_second_roundtrip(self):
        ms, qs = fixture()
        model = fit.fit_surface(ms, qs)
        predicted, _ = fit._predicted_knots(model, 725)
        rows = fit.predict_surface(model, 725, fit.P_KNOTS)
        self.assertEqual([r["cutoff_hex"] for r in rows], [v.hex() for v in predicted])

    def test_rare_column_nan_preserves_body(self):
        ms, qs = fixture()
        qs[1, -1] = np.nan
        model = fit.fit_surface(ms, qs, "pchip")
        json.dumps(model, allow_nan=False)
        rows = fit.predict_surface(model, 725, [0.001, 0.0001, 0.00005, 0.0000001])
        self.assertEqual([r["available"] for r in rows], [True, True, False, False])
        self.assertIn("nonfinite_training_cutoff", rows[-1]["reason"])

    def test_rare_crossing_preserves_body(self):
        ms, qs = fixture()
        qs[:, -1] = qs[:, -2] * 0.9
        model = fit.fit_surface(ms, qs, "pchip")
        rows = fit.predict_surface(model, 725, [0.05, 0.0001, 0.00005])
        self.assertEqual([r["available"] for r in rows], [True, True, False])
        self.assertEqual(rows[-1]["reason"], "crossed_scope_knots")

    def test_body_crossing_is_not_sorted(self):
        ms, qs = fixture()
        qs[:, 10] = qs[:, 9] * 0.9
        model = fit.fit_surface(ms, qs, "pchip")
        rows = fit.predict_surface(model, 725, [0.05, 0.0001])
        self.assertTrue(all(not r["available"] for r in rows))
        self.assertTrue(all(r["reason"] == "crossed_scope_knots" for r in rows))

    def test_equal_knots_allowed(self):
        ms, qs = fixture()
        qs[:, 10] = qs[:, 9]
        model = fit.fit_surface(ms, qs, "pchip")
        self.assertTrue(fit.predict_surface(model, 725, [0.001])[0]["available"])

    def test_shared_boundary_invalidates_both(self):
        ms, qs = fixture()
        qs[0, fit.P_KNOTS.index(0.0001)] = 0
        model = fit.fit_surface(ms, qs, "pchip")
        self.assertTrue(all(not r["available"] for r in fit.predict_surface(model, 725, [0.05, 0.0001, 0.00001])))

    def test_boundary_returns_identical_literal(self):
        ms, qs = fixture()
        model = fit.fit_surface(ms, qs, "pchip")
        value = fit.predict_surface(model, ms[2], [0.0001])[0]
        self.assertEqual(value["cutoff_hex"], float(qs[2, fit.P_KNOTS.index(0.0001)]).hex())
        self.assertEqual(value["source"], "moderate")

    def test_monotonic_dense_predictions(self):
        ms, qs = fixture()
        for method in fit.METHODS:
            rows = fit.predict_surface(fit.fit_surface(ms, qs, method), 725, fit._GRID.ALL_P)
            self.assertTrue(all(row["available"] for row in rows))
            self.assertTrue(np.all(np.diff([r["cutoff"] for r in rows]) >= 0))

    def test_query_domains_and_no_extrapolation(self):
        ms, qs = fixture()
        model = fit.fit_surface(ms, qs)
        for m in (49, 10001, float("nan"), float("inf"), True, "50"):
            self.assertFalse(fit.predict_surface(model, m, [0.001])[0]["available"])
        for p in (0, -1, 0.06, 1e-8, float("nan"), float("inf"), True, "0.001"):
            row = fit.predict_surface(model, 725, [p])[0]
            self.assertFalse(row["available"])
            json.dumps(row, allow_nan=False)
        subms, subqs = fixture((100, 200, 1000))
        submodel = fit.fit_surface(subms, subqs)
        self.assertIn("m_outside_training_range", fit.predict_surface(submodel, 50, [0.001])[0]["reason"])

    def test_invalid_fitting_arguments(self):
        ms, qs = fixture()
        for badms in ([100, 50, 200], [50, 50, 100], [49, 100, 200], [50, 100, 10001],
                      [50, 100, float("nan")], [True, 100, 200], [50, 100]):
            with self.assertRaises(ValueError):
                fit.fit_surface(badms, qs[:len(badms)])
        for badqs in (qs[:, :24], np.zeros((7, 25), dtype=complex), np.ones((7, 25), dtype=bool)):
            with self.assertRaises(ValueError):
                fit.fit_surface(ms, badqs)
        with self.assertRaises(ValueError):
            fit.fit_surface(ms, qs, "linear")

    def test_nonpositive_and_above_support_columns(self):
        ms, qs = fixture()
        qs[0, 0] = -1
        qs[1, -1] = math.log(ms[1]) + 1
        model = fit.fit_surface(ms, qs)
        self.assertEqual(model["columns"][0]["reason"], "nonpositive_training_cutoff")
        self.assertEqual(model["columns"][-1]["reason"], "training_cutoff_above_log_m")
        self.assertTrue(all(not row["available"] for row in fit.predict_surface(model, 725, [0.05, 1e-7])))

    def test_model_tampering_rejected(self):
        ms, qs = fixture()
        model = fit.fit_surface(ms, qs)
        model["schema"] = "wrong"
        with self.assertRaises(ValueError):
            fit.predict_surface(model, 725, [0.001])


class SelectionTests(unittest.TestCase):
    def test_exact_objective(self):
        rows = counts()
        report = fit.selection_loss(rows)
        expected = sum(math.log(((r["count"] + 0.5) / (r["n"] + 1)) / r["p"]) ** 2 for r in rows) / 80
        self.assertTrue(report["eligible"])
        self.assertAlmostEqual(report["loss"], expected, places=20)
        self.assertEqual(report["worst_absolute_relative_error"], 0.0)

    def test_missing_duplicate_unexpected_and_unavailable(self):
        for bad in (counts()[:-1], counts() + [counts()[0]], counts() + [dict(counts()[0], m=50)],
                    [dict(r, available=False) if i == 0 else r for i, r in enumerate(counts())]):
            result = fit.selection_loss(bad)
            self.assertFalse(result["eligible"])
            self.assertIsNone(result["loss"])
            json.dumps(result, allow_nan=False)

    def test_invalid_counts(self):
        for key, value in (("count", -1), ("count", 10000001), ("count", 1.2), ("count", True),
                           ("n", 0), ("n", float("nan")), ("n", True)):
            rows = counts()
            rows[0][key] = value
            self.assertFalse(fit.selection_loss(rows)["eligible"])

    def test_zero_and_all_counts_still_finite(self):
        rows = counts()
        rows[0]["count"] = 0
        rows[1]["count"] = rows[1]["n"]
        report = fit.selection_loss(rows)
        self.assertTrue(report["eligible"])
        self.assertTrue(math.isfinite(report["loss"]))

    def test_selection_tie_and_ineligible(self):
        tied = [{"method": "pchip", "eligible": True, "loss": 1.0},
                {"method": "quadratic", "eligible": True, "loss": 1.0 + 0.5e-12}]
        self.assertEqual(fit.select_surface(tied)["selected_method"], "quadratic")
        tied[1]["loss"] = 1.0 + 2e-12
        self.assertEqual(fit.select_surface(tied)["selected_method"], "pchip")
        tied[0]["eligible"] = False
        self.assertEqual(fit.select_surface(tied)["selected_method"], "quadratic")

    def test_no_finite_winner(self):
        rows = [{"method": "quadratic", "eligible": False, "loss": None},
                {"method": "pchip", "eligible": True, "loss": float("inf")}]
        self.assertIsNone(fit.select_surface(rows)["selected_method"])

    def test_unknown_duplicate_method_rejected(self):
        with self.assertRaises(ValueError):
            fit.select_surface([{"method": "linear", "eligible": True, "loss": 1}])
        with self.assertRaises(ValueError):
            fit.select_surface([{"method": "pchip"}, {"method": "pchip"}])


if __name__ == "__main__":
    unittest.main()
