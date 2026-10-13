"""Source-column and reconciliation tests; never modify a publication workbook."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import extract_publication as module


HEADER = (
    "# Top_Ranked_Edges", "# True_Postive_Edges", "Method",
    "# Top_Ranked_Edges", "Early_Precision_Ratio", "1-Specificity",
    "Sensitivity", "Method",
)


def fixture():
    # The independent column blocks deliberately do not share record meanings.
    return [
        ("Figure 6a", None, None, None, None, None, None, None),
        HEADER,
        (1000, 10, "scMINER", 1000, 2, 0.10, 0.15, "scMINER"),
        (2000, 20, "scMINER", 2000, 4, 0.20, 0.30, "scMINER"),
        (1000, 5, "Random", None, None, None, None, None),
        (2000, 5, "Random", None, None, None, None, None),
    ]


class FakeSheet:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def iter_rows(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.rows)


class FakeWorkbook:
    def __init__(self, sheet):
        self.sheet = sheet
        self.closed = False

    def __getitem__(self, key):
        if key != "Figure_6a":
            raise KeyError(key)
        return self.sheet

    def close(self):
        self.closed = True


class ExtractPublicationTests(unittest.TestCase):
    def extract_rows(self, rows):
        return module.extract(FakeSheet(rows))

    def altered(self, row, col, value):
        rows = copy.deepcopy(fixture())
        changed = list(rows[row])
        changed[col] = value
        rows[row] = tuple(changed)
        return rows

    def test_independent_blocks_and_original_worksheet_rows(self):
        sheet = FakeSheet(fixture())
        tp, epr, roc = module.extract(sheet)
        self.assertEqual(tp, [(1000, 10, "scMINER", 3), (2000, 20, "scMINER", 4),
                              (1000, 5, "Random", 5), (2000, 5, "Random", 6)])
        self.assertEqual(epr, [(1000, 2.0, 3), (2000, 4.0, 4)])
        self.assertEqual(roc, [(0.10, 0.15, "scMINER", 3),
                               (0.20, 0.30, "scMINER", 4)])
        self.assertEqual(sheet.calls, [{"min_col": 1, "max_col": 8,
                                       "values_only": True}])

    def test_exact_header_required(self):
        rows = fixture()
        rows[1] = ("wrong", *HEADER[1:])
        with self.assertRaisesRegex(ValueError, "headers"):
            self.extract_rows(rows)

    def test_tp_integer_positive_and_supported_method(self):
        for col, value in ((0, 1000.5), (0, 0), (0, -1), (2, "other")):
            with self.subTest(col=col, value=value):
                with self.assertRaises(ValueError):
                    self.extract_rows(self.altered(2, col, value))

    def test_tp_count_cannot_be_missing_negative_fractional_or_above_k(self):
        for value in (None, -1, 1.5, 1001):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.extract_rows(self.altered(2, 1, value))

    def test_duplicate_tp_points_rejected(self):
        rows = fixture()
        rows.append((1000, 10, "scMINER", None, None, None, None, None))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.extract_rows(rows)

    def test_epr_reconciles_across_different_source_rows(self):
        with self.assertRaisesRegex(ValueError, "reconcile"):
            self.extract_rows(self.altered(2, 4, 2.01))

    def test_epr_missing_or_zero_random_denominator_rejected(self):
        for value in (0, None):
            rows = fixture()
            if value is None:
                rows[4] = (None,) * 8
            else:
                rows[4] = (1000, value, "Random", None, None, None, None, None)
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "denominator"):
                    self.extract_rows(rows)

    def test_nonfinite_negative_or_missing_epr_rejected(self):
        for value in (float("nan"), float("inf"), -1, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "EPR"):
                    self.extract_rows(self.altered(2, 4, value))

    def test_fractional_epr_k_cannot_be_silently_truncated(self):
        with self.assertRaises(ValueError):
            self.extract_rows(self.altered(2, 3, 1000.5))

    def test_roc_bounds_and_missing_sensitivity_rejected(self):
        for col, value in ((5, -0.1), (5, 1.1), (5, float("nan")),
                           (6, None), (6, -0.1), (6, 1.1)):
            with self.subTest(col=col, value=value):
                with self.assertRaisesRegex(ValueError, "ROC"):
                    self.extract_rows(self.altered(2, col, value))

    def test_unknown_or_missing_roc_method_rejected(self):
        for value in ("other", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.extract_rows(self.altered(2, 7, value))

    def test_missing_roc_block_rejected_without_fabrication(self):
        rows = fixture()
        rows[2] = (*rows[2][:5], None, None, None)
        rows[3] = (*rows[3][:5], None, None, None)
        with self.assertRaisesRegex(ValueError, "Missing"):
            self.extract_rows(rows)

    def test_cli_manifest_preserves_partial_roc_and_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.xlsx"
            # No Excel authoring: the fake loader supplies the independent rows.
            source.write_bytes(b"immutable synthetic workbook payload")
            initial_hash = module.sha256(source)
            out = root / "published"
            fake_workbook = FakeWorkbook(FakeSheet(fixture()))
            arguments = ["extract_publication.py", "--workbook", str(source),
                         "--out", str(out)]
            with mock.patch.object(sys, "argv", arguments), \
                    mock.patch.object(module.openpyxl, "load_workbook", return_value=fake_workbook) as loader, \
                    contextlib.redirect_stdout(io.StringIO()):
                module.main()
            loader.assert_called_once_with(source, read_only=True, data_only=True)
            self.assertTrue(fake_workbook.closed)
            self.assertEqual(module.sha256(source), initial_hash)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["tp_counts"], {"scMINER": 2, "Random": 2})
            self.assertEqual(manifest["epr_points"], 2)
            self.assertEqual(manifest["roc_points"], 2)
            self.assertEqual(manifest["roc_FPR_range"], [0.1, 0.2])
            self.assertEqual(manifest["roc_TPR_range"], [0.15, 0.3])
            self.assertEqual(manifest["roc_methods"], ["scMINER"])
            self.assertFalse(manifest["full_ROC_available"])
            self.assertEqual(manifest["published_AUROC_rounded"], 0.75)
            self.assertIn("NOT calculated", manifest["AUROC_source"])
            self.assertEqual(set(manifest["outputs_sha256"]),
                             {"tp.tsv", "epr.tsv", "roc_segment.tsv"})
            for name, value in manifest["outputs_sha256"].items():
                self.assertEqual(value, module.sha256(out / name))
            self.assertFalse((out / "full_roc.tsv").exists())


if __name__ == "__main__":
    unittest.main()
