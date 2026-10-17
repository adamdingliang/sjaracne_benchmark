"""Synthetic presentation fixtures only; never open a production result."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fit_report

SPEC = importlib.util.spec_from_file_location("broad_fit_present", Path(__file__).with_name("fit_present.py"))
present = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(present)


def fixture():
    rows = []
    for method in present.METHODS:
        for m in range(50, 10001, 50):
            group = ("final_interpolation_test" if m % 500 == 350 else
                     "development" if m % 500 == 450 else "training")
            for p in fit_report.ALL_P:
                classification = None
                if method == "pchip" and p in present.COARSE_P:
                    classification = "confirmed" if p in present.CORE_P else "unresolved"
                rows.append({"m": m, "p": p, "phase": "final_validation", "method": method,
                             "m_group": group, "available": True, "cutoff": 0.1,
                             "n": 10000000, "count": int(p * 10000000), "ratio": 1.01,
                             "relative_error": 0.01, "classification": classification})
    selection = {"selected_model": "pchip", "candidates": [
        {"method": "quadratic", "eligible": True, "loss": 0.01,
         "median_absolute_relative_error": 0.03, "worst_absolute_relative_error": 0.1},
        {"method": "pchip", "eligible": True, "loss": 0.001,
         "median_absolute_relative_error": 0.01, "worst_absolute_relative_error": 0.04}]}
    return rows, selection, {"selected_model": "pchip"}


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.selection, cls.primary = fixture()
        cls.summary = {"final_summary": fit_report.summarize(cls.rows)}

    def test_render_matches_actual_summary_schema(self):
        text = present.render_results(self.summary, self.selection, self.primary, self.rows, [])
        self.assertIn("selected primary is **PCHIP**", text)
        self.assertIn("All 800 tested core evaluation cases are confirmed", text)
        self.assertIn("| Four core p levels | 800 | 800 | 0 | 0 | 0 |", text)
        self.assertIn("| All eight primary p levels | 1600 | 800 | 0 | 800 | 0 |", text)
        self.assertIn("9800/9800", text)
        self.assertIn("20 untouched interpolation-test", text)
        self.assertIn("not completion of the original", text)
        self.assertIn("No fully\ngeneral runtime replacement is promoted", text)

    def test_800_and_1600_classification_counts(self):
        self.assertEqual(present._core_classes(self.rows, "pchip", present.CORE_P), {"confirmed": 800})
        self.assertEqual(present._core_classes(self.rows, "pchip", present.COARSE_P),
                         {"confirmed": 800, "unresolved": 800})

    def test_one_unresolved_core_prevents_acceptance(self):
        rows = [dict(row) for row in self.rows]
        index = next(i for i, row in enumerate(rows) if row["method"] == "pchip" and row["p"] == 0.05)
        rows[index]["classification"] = "unresolved"
        text = present.render_results({"final_summary": fit_report.summarize(rows)}, self.selection, self.primary, rows, [])
        self.assertIn("core grid is **not confirmed**", text)
        self.assertIn("| Four core p levels | 800 | 799 | 0 | 1 | 0 |", text)

    def test_missing_or_duplicate_primary_cells_rejected(self):
        primary_index = next(i for i, row in enumerate(self.rows) if row["method"] == "pchip" and row["p"] == 0.05)
        missing = self.rows[:primary_index] + self.rows[primary_index + 1:]
        duplicate = self.rows + [self.rows[primary_index]]
        for rows in (missing, duplicate):
            with self.assertRaisesRegex(ValueError, "full planned grid"):
                present._core_classes(rows, "pchip", present.CORE_P)

    def test_primary_identity_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "identities disagree"):
            present.render_results(self.summary, self.selection, {"selected_model": "quadratic"}, self.rows, [])

    def test_case_notes_use_supplied_rows_without_revising_thresholds(self):
        row = {"method": "pchip", "phase": "final_validation", "m": 50, "p": 0.05,
               "classification": "unresolved", "available": True, "relative_error": 0.11,
               "actual": 0.0555, "ties": 90, "count": 555, "plus_ulp_ge": 465}
        before = dict(row)
        text = present._primary_case_notes([row], "pchip")
        self.assertIn("1 unresolved core cases", text)
        self.assertIn("1 at p=0.05", text)
        self.assertIn("90 validation values", text)
        self.assertIn("from 555 to 465", text)
        self.assertIn("not** a post-hoc change", text)
        self.assertEqual(row, before)
        self.assertEqual(present._primary_case_notes([row], "quadratic"), "")

    def test_missing_summary_group_rejected(self):
        broken = {"final_summary": [row for row in self.summary["final_summary"]
                                    if not (row["method"] == "pchip" and row["m_group"] == "all"
                                            and row["pscope"] == "core_four")]}
        with self.assertRaisesRegex(ValueError, "summary entry"):
            present.render_results(broken, self.selection, self.primary, self.rows, [])

    def test_evaluation_case_and_development_loss_wording(self):
        text = present.render_results(self.summary, self.selection, self.primary, self.rows, [])
        self.assertIn("80 development evaluation cases", text)
        self.assertIn("20 development sample counts", text)
        self.assertIn("p={0.05,0.01,0.001,0.0005}", text)
        self.assertIn("not a biological cell or an 80-sample dataset", text)
        self.assertIn("r_tilde=(c+0.5)/(10,000,000+1)", text)
        self.assertIn("equally weighted mean", text)
        self.assertIn("[log(r_tilde/p)]^2", text)
        self.assertIn("using the natural logarithm", text)
        self.assertIn("Lower is better; zero is ideal", text)
        self.assertIn("not a\npercentage", text)
        self.assertIn("pseudocount is only for this loss", text)
        self.assertIn("Planned evaluation cases", text)
        for ambiguous in ("development cells", "planned cells", "grid cells", "core cells", "9800 cells"):
            self.assertNotIn(ambiguous, text)

    def test_package_refuses_missing_completion_before_csv_read(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            here, analysis = base / "code", base / "analysis"
            here.mkdir()
            analysis.mkdir()
            with patch.object(present, "HERE", here), patch.object(present, "read_scores", side_effect=AssertionError("CSV opened")):
                with self.assertRaisesRegex(ValueError, "not complete"):
                    present.package(analysis, here / "results_2026-10-17")

    def test_package_refuses_noncomplete_status_before_csv_read(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            here, analysis = base / "code", base / "analysis"
            here.mkdir()
            analysis.mkdir()
            (analysis / "summary.json").write_text("{}", encoding="utf-8")
            (analysis / "status.json").write_text(json.dumps({"phase": "training"}), encoding="utf-8")
            with patch.object(present, "HERE", here), patch.object(present, "read_scores", side_effect=AssertionError("CSV opened")):
                with self.assertRaisesRegex(ValueError, "not complete"):
                    present.package(analysis, here / "results_2026-10-17")

    def test_locked_compact_record_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text("{}", encoding="utf-8")
            path.with_suffix(".sha256").write_text(present.digest(path), encoding="ascii")
            self.assertEqual(present.read_locked(path), {})
            path.write_text('{"changed":true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                present.read_locked(path)

    def test_csv_bool_numeric_conversion_and_bad_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("m", "p", "cutoff", "available", "classification"))
                writer.writeheader()
                writer.writerow({"m": 450, "p": 0.001, "cutoff": 0.1, "available": True})
            row = present.read_scores(path)[0]
            self.assertEqual(row["m"], 450.0)
            self.assertTrue(row["available"])
            self.assertIsNone(row["classification"])
            path.write_text("m,p,cutoff,available\n450,0.001,nan,True\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                present.read_scores(path)

    def test_four_panel_plot_renders_synthetic_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            present.rate_plot(self.rows, "pchip", out)
            for suffix in ("png", "svg"):
                path = out / ("null_rate_vs_m." + suffix)
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
