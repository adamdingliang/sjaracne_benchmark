"""Synthetic-only tests of smooth calibration candidates; no data access."""

import importlib.util
from pathlib import Path
import unittest

import numpy as np
from scipy.stats import genpareto


SPEC = importlib.util.spec_from_file_location("smooth_feasibility_models", Path(__file__).with_name("models.py"))
MODELS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODELS)


class QuantileModelsTests(unittest.TestCase):
    def setUp(self):
        self.m = np.array([30., 50., 80., 100., 200., 500.])
        self.factors = np.array([0.1, 0.3, 0.6])
        self.quantiles = self.m[:, None] ** -0.7 * self.factors

    def test_power_law_recovered_by_all_methods(self):
        test = np.array([40., 90., 300.])
        expected = test[:, None] ** -0.7 * self.factors
        for method in MODELS.METHODS:
            with self.subTest(method=method):
                np.testing.assert_allclose(
                    MODELS.predict_quantiles(self.m, self.quantiles, test, method),
                    expected, rtol=1e-12)

    def test_log_quadratic_recovered(self):
        x = np.log(self.m)
        values = np.exp(0.2 - 0.7 * x + 0.03 * x ** 2)[:, None]
        test = 150.
        expected = np.exp(0.2 - 0.7 * np.log(test) + 0.03 * np.log(test) ** 2)
        np.testing.assert_allclose(
            MODELS.predict_quantiles(self.m, values, test, "logquadratic"), [expected], rtol=1e-12)

    def test_scalar_and_vector_shapes(self):
        for method in MODELS.METHODS:
            self.assertEqual(MODELS.predict_quantiles(self.m, self.quantiles, 90., method).shape, (3,))
            self.assertEqual(MODELS.predict_quantiles(self.m, self.quantiles, [90.], method).shape, (1, 3))

    def test_pchip_does_not_extrapolate(self):
        result = MODELS.predict_quantiles(self.m, self.quantiles, [20., 50., 1000.], "pchip")
        self.assertTrue(np.isnan(result[0]).all())
        self.assertTrue(np.isfinite(result[1]).all())
        self.assertTrue(np.isnan(result[2]).all())

    def test_polynomials_can_extrapolate(self):
        for method in ("loglinear", "logquadratic"):
            result = MODELS.predict_quantiles(self.m, self.quantiles, [20., 1000.], method)
            self.assertTrue(np.isfinite(result).all())

    def test_unsorted_training_matches_sorted(self):
        order = [3, 1, 5, 0, 4, 2]
        for method in MODELS.METHODS:
            np.testing.assert_allclose(
                MODELS.predict_quantiles(self.m[order], self.quantiles[order], 90., method),
                MODELS.predict_quantiles(self.m, self.quantiles, 90., method), rtol=0, atol=0)

    def test_no_monotonicity_repair(self):
        nonmonotone = self.quantiles[:, [2, 0, 1]]
        predicted = MODELS.predict_quantiles(self.m, nonmonotone, 90., "pchip")
        self.assertGreater(predicted[0], predicted[1])
        self.assertLess(predicted[1], predicted[2])

    def test_left_out_values_cannot_affect_training(self):
        kept = np.arange(self.m.size) != 2
        for method in MODELS.METHODS:
            original = MODELS.predict_quantiles(self.m[kept], self.quantiles[kept], self.m[2], method)
            changed = self.quantiles.copy()
            changed[2] = [100., 200., 300.]
            recomputed = MODELS.predict_quantiles(self.m[kept], changed[kept], self.m[2], method)
            np.testing.assert_array_equal(original, recomputed)

    def test_invalid_training(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            MODELS.predict_quantiles([30., 30.], [[0.1], [0.2]], 30.)
        with self.assertRaisesRegex(ValueError, "at least 3"):
            MODELS.predict_quantiles([30., 50.], [[0.1], [0.2]], 40., "logquadratic")
        for invalid in (0., -1., np.nan, np.inf):
            values = self.quantiles.copy()
            values[0, 0] = invalid
            with self.assertRaises(ValueError):
                MODELS.predict_quantiles(self.m, values, 90.)
        with self.assertRaisesRegex(ValueError, "shape"):
            MODELS.predict_quantiles(self.m, self.quantiles.T, 90.)
        with self.assertRaisesRegex(ValueError, "greater than 1"):
            MODELS.predict_quantiles(self.m, self.quantiles, 1.)
        with self.assertRaisesRegex(ValueError, "method"):
            MODELS.predict_quantiles(self.m, self.quantiles, 90., "linear")


class GpdParameterTests(unittest.TestCase):
    def setUp(self):
        self.m = np.array([30., 50., 80., 100., 200., 500.])
        self.parameters = {
            "u": 0.7 * self.m ** -0.5,
            "scale": 0.2 * self.m ** -0.4,
            "shape": 0.03 + 0.02 * np.log(self.m),
            "tail_probability": 1 / (1 + np.exp(-(-3 + 0.1 * np.log(self.m)))),
        }

    def test_transforms_recover_synthetic_functions(self):
        for method in MODELS.METHODS:
            predicted = MODELS.predict_gpd_parameters(self.m, self.parameters, 90., method)
            self.assertTrue(all(isinstance(value, float) for value in predicted.values()))
            self.assertAlmostEqual(predicted["u"], 0.7 * 90 ** -0.5, places=13)
            self.assertAlmostEqual(predicted["scale"], 0.2 * 90 ** -0.4, places=13)
            self.assertAlmostEqual(predicted["shape"], 0.03 + 0.02 * np.log(90), places=13)
            self.assertAlmostEqual(predicted["tail_probability"],
                                   1 / (1 + np.exp(-(-3 + 0.1 * np.log(90)))), places=13)

    def test_vector_shape_and_pchip_domain(self):
        result = MODELS.predict_gpd_parameters(self.m, self.parameters, [20., 90., 1000.], "pchip")
        for array in result.values():
            self.assertEqual(array.shape, (3,))
            self.assertTrue(np.isnan(array[[0, 2]]).all())
            self.assertTrue(np.isfinite(array[1]))

    def test_invalid_parameters(self):
        for field, value in (("u", 0.), ("u", 100.), ("scale", -1.),
                             ("shape", np.nan), ("tail_probability", 0.),
                             ("tail_probability", 1.)):
            changed = {key: array.copy() for key, array in self.parameters.items()}
            changed[field][0] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                MODELS.predict_gpd_parameters(self.m, changed, 90.)
        with self.assertRaisesRegex(ValueError, "missing"):
            MODELS.predict_gpd_parameters(self.m, {}, 90.)
        changed = dict(self.parameters, shape=[0.1])
        with self.assertRaisesRegex(ValueError, "aligned"):
            MODELS.predict_gpd_parameters(self.m, changed, 90.)


class ProbabilityInterpolationTests(unittest.TestCase):
    def setUp(self):
        self.p = np.array([0.05, 0.01, 0.001, 0.0005, 0.0001, 1e-5, 1e-6, 1e-7])
        self.cutoffs = 0.02 * self.p ** -0.1

    def test_log_power_curve_recovered(self):
        queries = np.array([0.02, 0.005, 0.002, 0.00075, 0.0002, 5e-5, 5e-6, 5e-7])
        actual = MODELS.interpolate_probability(self.p, self.cutoffs, queries)
        np.testing.assert_allclose(actual, 0.02 * queries ** -0.1, rtol=1e-12)

    def test_scalar_and_multidimensional_shapes(self):
        values = np.stack((self.cutoffs, self.cutoffs * 2))
        self.assertEqual(MODELS.interpolate_probability(self.p, values, 0.002).shape, (2,))
        self.assertEqual(MODELS.interpolate_probability(self.p, values, [0.002]).shape, (2, 1))
        self.assertEqual(MODELS.interpolate_probability(self.p, values[None, ...], [0.002, 0.02]).shape, (1, 2, 2))

    def test_knots_recovered_and_monotonic_preserved_without_repair(self):
        np.testing.assert_allclose(MODELS.interpolate_probability(self.p, self.cutoffs, self.p),
                                   self.cutoffs, rtol=1e-14)
        tied = self.cutoffs.copy()
        tied[2] = tied[3]
        actual = MODELS.interpolate_probability(self.p, tied, np.geomspace(1e-7, 0.05, 500))
        self.assertTrue((np.diff(actual) <= 0).all())

    def test_invalid_values_no_extrapolation_or_repair(self):
        for query in (0., -1., 0.1, 1e-8, np.nan):
            with self.subTest(query=query), self.assertRaises(ValueError):
                MODELS.interpolate_probability(self.p, self.cutoffs, query)
        for invalid in (0., -1., np.inf, np.nan):
            cutoffs = self.cutoffs.copy()
            cutoffs[0] = invalid
            with self.assertRaises(ValueError):
                MODELS.interpolate_probability(self.p, cutoffs, 0.002)
        cutoffs = self.cutoffs.copy()
        cutoffs[[2, 3]] = cutoffs[[3, 2]]
        with self.assertRaisesRegex(ValueError, "no repair"):
            MODELS.interpolate_probability(self.p, cutoffs, 0.002)
        with self.assertRaisesRegex(ValueError, "distinct"):
            MODELS.interpolate_probability([0.01, 0.01], [0.1, 0.2], 0.01)


class GpdCutoffTests(unittest.TestCase):
    def test_shape_zero_limit(self):
        value = MODELS.gpd_cutoff(0.1, 0.02, 0., 0.005, 0.001, 100.)
        self.assertIsInstance(value, float)
        self.assertAlmostEqual(value, 0.1 + 0.02 * np.log(5), places=15)

    def test_near_zero_shape_is_numerically_stable(self):
        expected = MODELS.gpd_cutoff(0.1, 0.02, 0., 0.005, 0.001, 100.)
        for shape in (-1e-12, 1e-12):
            self.assertAlmostEqual(MODELS.gpd_cutoff(0.1, 0.02, shape, 0.005, 0.001, 100.),
                                   expected, places=12)

    def test_positive_and_negative_shapes_agree_with_scipy(self):
        for shape in (-0.2, 0., 0.2):
            actual = MODELS.gpd_cutoff(0.1, 0.02, shape, 0.005, 0.001, 100.)
            expected = 0.1 + genpareto.isf(0.001 / 0.005, shape, scale=0.02)
            self.assertAlmostEqual(actual, expected, places=15)

    def test_p_equals_tail_probability_returns_u(self):
        for shape in (-0.2, 0., 0.2):
            self.assertEqual(MODELS.gpd_cutoff(0.1, 0.02, shape, 0.005, 0.005, 100.), 0.1)

    def test_broadcasting_and_p_monotonicity(self):
        result = MODELS.gpd_cutoff(0.1, 0.02, np.array([[-0.2], [0.], [0.2]]),
                                  0.005, [0.0001, 0.001, 0.005], 100.)
        self.assertEqual(result.shape, (3, 3))
        self.assertTrue((np.diff(result, axis=1) < 0).all())

    def test_invalid_inputs_raise_without_clipping(self):
        valid = dict(u=0.1, scale=0.02, shape=0.1, tail_probability=0.005, p=0.001, m=100.)
        cases = [dict(scale=0.), dict(scale=-1.), dict(tail_probability=0.),
                 dict(tail_probability=1.), dict(p=0.), dict(p=-0.1), dict(p=0.01),
                 dict(m=1.), dict(u=-0.1), dict(u=100.), dict(shape=np.nan),
                 dict(p=np.inf), dict(scale=10.), dict(shape=1000.)]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                MODELS.gpd_cutoff(**dict(valid, **change))

    def test_negative_shape_endpoint_roundoff_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite tail endpoint"):
            MODELS.gpd_cutoff(0.1, 0.02, -1., 0.005, 1e-100, 100.)

    def test_broadcast_error_has_reason(self):
        with self.assertRaisesRegex(ValueError, "broadcast-compatible"):
            MODELS.gpd_cutoff([0.1, 0.2], [0.02, 0.03, 0.04], 0., 0.005, 0.001, 100.)


if __name__ == "__main__":
    unittest.main()
