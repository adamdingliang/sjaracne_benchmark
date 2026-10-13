"""Lightweight notebook checks; never import Scanpy or execute analysis cells.

Run with the notebook environment's Python and ``-B`` to avoid bytecode files.
Only the pure label-parser, published-label validator and row-selection helpers
are executed.
"""

import ast
from pathlib import Path
import tempfile
import unittest

import anndata as ad
import nbformat
import numpy as np
import pandas as pd
from scipy import sparse


NOTEBOOK = Path(__file__).with_name("02_scanpy_exploration.ipynb")
HELPERS = {"parse_targets", "assignment_class", "choose_rows", "prepare_figure6gh_labels"}


class ScanpyNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = nbformat.read(NOTEBOOK, as_version=4)
        namespace = {"np": np, "pd": pd}
        found = set()
        for index, cell in enumerate(cls.notebook.cells):
            if cell.cell_type != "code":
                continue
            tree = ast.parse(cell.source, filename=f"{NOTEBOOK.name}:cell{index}")
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name in HELPERS:
                    helper = ast.Module(body=[node], type_ignores=[])
                    exec(compile(helper, str(NOTEBOOK), "exec"), namespace)
                    found.add(node.name)
        if found != HELPERS:
            raise AssertionError(f"Missing pure notebook helpers: {HELPERS - found}")
        cls.helpers = namespace

    def test_notebook_format_and_python_syntax(self):
        nbformat.validate(self.notebook)
        for index, cell in enumerate(self.notebook.cells):
            if cell.cell_type == "code":
                ast.parse(cell.source, filename=f"{NOTEBOOK.name}:cell{index}")

    def test_assignment_classes_keep_controls_separate(self):
        cases = [
            (None, "unassigned"),
            (np.nan, "unassigned"),
            (pd.NA, "unassigned"),
            ("", "unassigned"),
            ("MYD88", "single_target"),
            ("MYD88--MYD88", "single_target"),
            ("MYD88--IRAK4", "multiple_targets"),
            ("ARPC4-TTLL3", "single_target"),
            ("non-targeting", "NT"),
            ("non-targeting--non-targeting", "NT"),
            ("safe-targeting", "safe_control"),
            ("safe-targeting--safe-targeting", "safe_control"),
            ("non-targeting--safe-targeting", "mixed_controls"),
            ("MYD88--non-targeting", "control_plus_target"),
            ("MYD88--safe-targeting", "control_plus_target"),
            ("non-targeting--MYD88--MYD88", "control_plus_target"),
        ]
        for label, expected in cases:
            with self.subTest(label=label):
                tokens = self.helpers["parse_targets"](label)
                self.assertEqual(self.helpers["assignment_class"](tokens), expected)

    def test_parser_preserves_single_hyphens_and_distinct_target_order(self):
        parse = self.helpers["parse_targets"]
        self.assertEqual(parse("DUSP1--ARPC4-TTLL3"), ("DUSP1", "ARPC4-TTLL3"))
        self.assertEqual(parse(" MYD88 --IRAK4--MYD88 "), ("MYD88", "IRAK4"))

    def test_row_selection_is_seeded_sorted_without_replacement(self):
        obs = pd.DataFrame({"assignment_class": pd.Categorical([
            "NT", "safe_control", "single_target", "NT",
            "mixed_controls", "NT", "NT", "single_target",
        ])})
        choose = self.helpers["choose_rows"]
        np.testing.assert_array_equal(choose(obs, None, False, 42), np.arange(8))
        nt_rows = choose(obs, None, True, 42)
        np.testing.assert_array_equal(nt_rows, np.array([0, 3, 5, 6]))
        first = choose(obs, 3, False, 42)
        np.testing.assert_array_equal(first, choose(obs, 3, False, 42))
        self.assertEqual(len(first), 3)
        self.assertEqual(len(np.unique(first)), 3)
        self.assertTrue(np.all(np.diff(first) > 0))
        limited_nt = choose(obs, 2, True, 42)
        self.assertEqual(len(limited_nt), 2)
        self.assertTrue(set(limited_nt) <= set(nt_rows))
        self.assertEqual(len(choose(obs.iloc[:0], None, False, 42)), 0)

    @staticmethod
    def published_fixture():
        return pd.DataFrame({
            "Cell_Barcode": [None, "AAACCTGAGATCGATA", "AAACCTGAGGTGCTAG"],
            "Cell_Type": [None, "CD4T", "NK"],
            "UMAP_1": [None, 11.75, 4.13],
            "UMAP_2": [None, -4.94, 2.15],
            "CD19": ["Protein", 9.2, 10.2],
        })

    def test_published_labels_drop_second_header_and_preserve_input(self):
        frame = self.published_fixture()
        before = frame.copy(deep=True)
        labels = self.helpers["prepare_figure6gh_labels"](frame)
        pd.testing.assert_frame_equal(frame, before)
        self.assertEqual(labels.index.tolist(), ["AAACCTGAGATCGATA", "AAACCTGAGGTGCTAG"])
        self.assertEqual(labels.columns.tolist(), ["Cell_Type", "UMAP_1", "UMAP_2"])
        self.assertEqual(labels["Cell_Type"].tolist(), ["CD4T", "NK"])

    def test_published_labels_reject_ambiguous_or_invalid_records(self):
        validate = self.helpers["prepare_figure6gh_labels"]
        bad = []
        bad.append(self.published_fixture().drop(columns="Cell_Type"))
        bad.append(self.published_fixture().iloc[:1])
        incomplete = self.published_fixture()
        incomplete.loc[1, ["Cell_Barcode", "Cell_Type"]] = None
        bad.append(incomplete)
        for column, value in [("Cell_Barcode", None), ("Cell_Barcode", " "),
                              ("Cell_Type", None), ("Cell_Type", " "),
                              ("UMAP_1", np.inf), ("UMAP_2", np.nan),
                              ("UMAP_1", "invalid")]:
            frame = self.published_fixture()
            frame[column] = frame[column].astype(object)
            frame.loc[1, column] = value
            bad.append(frame)
        duplicates = self.published_fixture()
        duplicates.loc[2, "Cell_Barcode"] = duplicates.loc[1, "Cell_Barcode"]
        bad.append(duplicates)
        for index, frame in enumerate(bad):
            with self.subTest(case=index), self.assertRaises(ValueError):
                validate(frame)

    def test_published_section_never_transfers_pbmc_labels_to_thp1(self):
        # Even an accidental identical barcode must not authorize label transfer.
        for cell_id in ("published-labels-audit", "published-pbmc-umap"):
            cell = next(cell for cell in self.notebook.cells if cell.id == cell_id)
            for node in ast.walk(ast.parse(cell.source)):
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        self.assertNotIn("adata", {name.id for name in ast.walk(target)
                                                   if isinstance(name, ast.Name)})
        note = next(cell for cell in self.notebook.cells if cell.id == "published-labels-note")
        self.assertIn("GSE213282", note.source)
        self.assertIn("GSM6858449", note.source)
        self.assertIn("PBMC UMAP only", note.source)

    def test_legacy_symbol_table_can_be_exported_with_modern_anndata(self):
        cell = next(cell for cell in self.notebook.cells if cell.id == "load-counts")
        assignments = []
        for node in ast.parse(cell.source).body:
            if not isinstance(node, ast.Assign):
                continue
            target = node.targets[0]
            is_var = isinstance(target, ast.Name) and target.id == "var"
            is_var_member = isinstance(target, (ast.Attribute, ast.Subscript)) and isinstance(target.value, ast.Name) and target.value.id == "var"
            if is_var or is_var_member:
                assignments.append(node)
        namespace = {
            "pd": pd,
            "raw_var": pd.DataFrame({"_index": ["MYD88", "LYZ"]}, index=["0", "1"]),
            "symbols": pd.Index(["MYD88", "LYZ"]),
        }
        exec(compile(ast.Module(body=assignments, type_ignores=[]), str(NOTEBOOK), "exec"), namespace)
        self.assertNotIn("_index", namespace["var"].columns)
        self.assertEqual(namespace["var"]["source_gene_symbol"].tolist(), ["MYD88", "LYZ"])
        sample = ad.AnnData(X=sparse.csr_matrix(np.array([[1, 2], [0, 3]], dtype=np.float32)), var=namespace["var"])
        sample.layers["counts"] = sample.X.copy()
        with tempfile.TemporaryDirectory(prefix="scanpy-export-smoke-") as directory:
            path = Path(directory) / "exploration.h5ad"
            sample.write_h5ad(path, compression="gzip")
            restored = ad.read_h5ad(path)
            self.assertEqual(restored.var_names.tolist(), ["MYD88", "LYZ"])
            np.testing.assert_array_equal(restored.layers["counts"].toarray(), sample.X.toarray())


if __name__ == "__main__":
    unittest.main(verbosity=2)
