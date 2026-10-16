"""Synthetic checks of the preregistered probability grids; no null-data access."""
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_UP, localcontext
import json
import math
import unittest

import grid


class GridTests(unittest.TestCase):
    def test_frozen_counts(self):
        self.assertEqual(len(grid.COARSE_P), 8)
        self.assertEqual(len(grid.OLD_PROBE_P), 8)
        self.assertEqual(len(grid.OLD_QUERY_P), 16)
        self.assertEqual(len(grid.DENSE_P), 25)
        self.assertEqual(sum(p >= 1e-4 for p in grid.DENSE_P), 22)
        self.assertEqual(len(grid.NEW_PROBE_P), 21)
        self.assertEqual(len(grid.ALL_P), 49)
        self.assertEqual(len(grid.GRIDM), 19)

    def test_probabilities_ordered_valid_unique(self):
        for name in ("COARSE_P", "OLD_PROBE_P", "OLD_QUERY_P", "DENSE_P",
                     "NEW_PROBE_P", "ALL_P"):
            values = getattr(grid, name)
            with self.subTest(grid=name):
                self.assertTrue(all(math.isfinite(p) and 0 < p < 1 for p in values))
                self.assertEqual(tuple(sorted(set(values), reverse=True)), values)

    def test_coarse_and_old_queries_preserved(self):
        self.assertTrue(set(grid.COARSE_P) <= set(grid.DENSE_P))
        self.assertTrue(set(grid.OLD_QUERY_P) <= set(grid.ALL_P))
        self.assertEqual(set(grid.OLD_QUERY_P), set(grid.COARSE_P) | set(grid.OLD_PROBE_P))
        self.assertEqual(set(grid.ALL_P), set(grid.DENSE_P) | set(grid.NEW_PROBE_P)
                         | set(grid.OLD_QUERY_P))

    def test_new_probes_disjoint(self):
        self.assertFalse(set(grid.NEW_PROBE_P) & set(grid.DENSE_P))
        self.assertFalse(set(grid.NEW_PROBE_P) & set(grid.COARSE_P))
        self.assertFalse(set(grid.NEW_PROBE_P) & set(grid.OLD_QUERY_P))

    def test_dense_knots_exact_decimal_construction(self):
        expected = {Decimal(a) * Decimal(10) ** exponent
                    for exponent in (-4, -3, -2)
                    for a in ("1", "1.5", "2", "3", "4", "5", "6", "7.5")
                    if Decimal(a) * Decimal(10) ** exponent <= Decimal("0.05")}
        expected.update(map(Decimal, ("0.00001", "0.000001", "0.0000001")))
        self.assertEqual(set(map(float, expected)), set(grid.DENSE_P))

    def test_probes_are_rounded_geometric_midpoints(self):
        knots = [Decimal(str(p)) for p in grid.DENSE_P if p >= 1e-4]
        for upper, lower, actual in zip(knots, knots[1:], grid.NEW_PROBE_P):
            with self.subTest(upper=str(upper), lower=str(lower)):
                with localcontext() as context:
                    context.prec = 50
                    context.rounding = ROUND_HALF_EVEN
                    exact = (upper * lower).sqrt()
                    context.prec = 14
                    rounded = +exact
                self.assertEqual(float(rounded), actual)
                self.assertLess(float(lower), actual)
                self.assertLess(actual, float(upper))
                self.assertLess(abs(float(exact) / actual - 1), 5e-14)

    def test_rounding_is_independent_of_global_decimal_context(self):
        upper, lower = Decimal("0.05"), Decimal("0.04")
        expected = grid._midpoint_decimal(upper, lower)
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_UP
            self.assertEqual(grid._midpoint_decimal(upper, lower), expected)

    def test_roles_overlap_and_partition_diagnostics(self):
        old_probe_now_knot = grid.probability_roles(0.005)
        self.assertTrue(old_probe_now_knot["old_probe"])
        self.assertTrue(old_probe_now_knot["old_query"])
        self.assertTrue(old_probe_now_knot["dense_knot"])
        self.assertFalse(old_probe_now_knot["new_probe"])
        for p in grid.ALL_P:
            roles = grid.probability_roles(p)
            self.assertEqual(sum(roles[k] for k in ("moderate", "lower_diagnostic", "rare")), 1)
            self.assertEqual(roles["primary"], p in (0.001, 0.0005))
        self.assertTrue(grid.probability_roles(0.0005)["moderate"])
        self.assertFalse(grid.probability_roles(0.0005)["lower_diagnostic"])
        self.assertTrue(grid.probability_roles(0.0001)["lower_diagnostic"])
        self.assertFalse(grid.probability_roles(0.0001)["rare"])

    def test_roles_reject_non_grid_values(self):
        for value in (True, False, float("nan"), float("inf"), None, "no", 0, 1, 0.0045):
            with self.subTest(value=value), self.assertRaises(ValueError):
                grid.probability_roles(value)

    def test_manifest_json_roundtrip_and_independence(self):
        manifest = grid.grid_manifest()
        self.assertEqual(json.loads(json.dumps(manifest, allow_nan=False)), manifest)
        self.assertEqual([row["p"] for row in manifest["roles"]], list(grid.ALL_P))
        for row in manifest["roles"]:
            self.assertEqual(float(Decimal(row["decimal_p"])), row["p"])
        manifest["dense_p"].clear()
        manifest["roles"][0]["dense_knot"] = False
        self.assertEqual(len(grid.grid_manifest()["dense_p"]), 25)
        self.assertTrue(grid.grid_manifest()["roles"][0]["dense_knot"])


if __name__ == "__main__":
    unittest.main()
