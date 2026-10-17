"""Synthetic archived-score fixtures; no raw draws or model fitting."""
from __future__ import annotations

import csv
import math
from pathlib import Path
import tempfile
import unittest

import plot_pchip_summary as plot


FIELDS = ("method", "phase", "m", "p", "available", "n", "count", "actual", "ratio", "m_group", "reason")


def fixture():
    rows = []
    for p in plot.CORE_P:
        for m in plot.GRID_M:
            count = int(plot.N_DRAWS * p)
            rows.append({"method": "pchip", "phase": "final_validation", "m": m, "p": p,
                         "available": True, "n": plot.N_DRAWS, "count": count,
                         "actual": count / plot.N_DRAWS, "ratio": (count / plot.N_DRAWS) / p,
                         "m_group": plot._role(m), "reason": ""})
    return rows


def save(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class PchipPlotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.csv_path = self.root / "scores.csv"

    def tearDown(self):
        self.temporary.cleanup()

    def read(self, rows):
        save(self.csv_path, rows)
        return plot.read_core_rows(self.csv_path)

    def test_exact800_and20_test_sizes_per_probability(self):
        rows = self.read(fixture())
        self.assertEqual(len(rows), 800)
        for p in plot.CORE_P:
            self.assertEqual(sum(row["p"] == p and row["m_group"] == "final_interpolation_test" for row in rows), 20)

    def test_other_methods_phases_and_probabilities_are_not_plotted(self):
        rows = fixture()
        rows.extend((dict(rows[0], method="quadratic"), dict(rows[0], phase="development"),
                     dict(rows[0], p=0.0001)))
        self.assertEqual(len(self.read(rows)), 800)

    def test_missing_and_duplicate_cases_rejected(self):
        rows = fixture()
        for bad in (rows[:-1], rows + [dict(rows[0])]):
            with self.assertRaisesRegex(ValueError, "800 unique"):
                self.read(bad)

    def test_invalid_archived_rates_draws_and_roles_rejected(self):
        for field, value in (("count", -1), ("count", 1.5), ("n", 1000), ("ratio", 1.1),
                             ("actual", float("nan")), ("available", "yes"), ("m", 51),
                             ("m_group", "final_interpolation_test")):
            rows = fixture()
            rows[0][field] = value
            with self.assertRaises(ValueError, msg=field):
                self.read(rows)

    def test_unavailable_case_is_retained(self):
        rows = fixture()
        rows[0].update(available=False, count="", actual="", ratio="", reason="synthetic_unavailable")
        recovered = self.read(rows)
        self.assertFalse(recovered[0]["available"])
        self.assertIsNone(recovered[0]["ratio"])
        self.assertEqual(recovered[0]["reason"], "synthetic_unavailable")

    def test_figure_four_panels_logm_unclipped_and_marked(self):
        rows = self.read(fixture())
        rows[0]["ratio"] = 1.8
        fig, axes = plot.make_figure(rows)
        import matplotlib.pyplot as plt
        try:
            self.assertEqual(axes.shape, (2, 2))
            for axis in axes.flat:
                self.assertEqual(axis.get_xscale(), "log")
                self.assertEqual(len(axis.collections[0].get_offsets()), 20)
                self.assertLess(axis.get_ylim()[0], 0.9)
                self.assertGreater(axis.get_ylim()[1], 1.1)
            self.assertGreater(axes.flat[0].get_ylim()[1], 1.8)
            self.assertIn("not a confidence interval", fig._suptitle.get_text())
        finally:
            plt.close(fig)

    def test_unavailable_prediction_breaks_line_without_dropping_m(self):
        rows = self.read(fixture())
        rows[4].update(available=False, ratio=None)
        fig, axes = plot.make_figure(rows)
        import matplotlib.pyplot as plt
        try:
            curve = next(line for line in axes.flat[0].lines if line.get_label() == "PCHIP (selected primary)")
            self.assertEqual(len(curve.get_xdata()), 200)
            self.assertTrue(math.isnan(curve.get_ydata()[4]))
            self.assertIn("1 unavailable", axes.flat[0].texts[0].get_text())
        finally:
            plt.close(fig)

    def test_deterministic_assets_and_input_unchanged(self):
        save(self.csv_path, fixture())
        initial = plot.sha256(self.csv_path)
        first = plot.render(self.csv_path, self.root / "first")
        second = plot.render(self.csv_path, self.root / "second")
        self.assertEqual(first["evaluation_cases"], 800)
        self.assertEqual(initial, plot.sha256(self.csv_path))
        self.assertEqual([row["sha256"] for row in first["outputs"]], [row["sha256"] for row in second["outputs"]])
        self.assertTrue(all(row["bytes"] > 1000 for row in first["outputs"]))

    def test_existing_output_refused(self):
        save(self.csv_path, fixture())
        out = self.root / "existing"
        out.mkdir()
        with self.assertRaisesRegex(ValueError, "fresh"):
            plot.render(self.csv_path, out)

    def test_missing_required_columns_refused(self):
        self.csv_path.write_text("m,p\n50,0.05\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "required presentation columns"):
            plot.read_core_rows(self.csv_path)


if __name__ == "__main__":
    unittest.main()
