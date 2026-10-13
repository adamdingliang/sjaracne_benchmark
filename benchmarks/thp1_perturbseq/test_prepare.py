#!/usr/bin/env python3
"""Tiny synthetic preparation checks; never load the external THP-1 dataset."""

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


SCRIPT = Path(__file__).with_name("prepare.py")
SPEC = importlib.util.spec_from_file_location("thp1_prepare", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestPreparation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.h5ad = self.root / "fixture.h5ad"
        self.sig = self.root / "SIG.txt"
        self.sig.write_text("A\nB\nABSENT\nA\n", encoding="utf-8")
        self.counts = np.asarray([
            [100, 10, 0, 1, 0], [100, 10, 20, 1, 0],
            [100, 10, 1, 1, 0], [100, 10, 40, 1, 0],
            [0, 10, 200, 1, 0], [0, 10, 100, 1, 0], [0, 10, 150, 1, 0],
            [100, 10, 0, 1, 1], [100, 10, 0, 1, 0], [100, 10, 0, 1, 0],
            [30, 10, 50, 1, 0],
        ], dtype=float)
        labels = [MODULE.NT_LABEL] * 4 + ["A"] * 3 + ["B"] * 3 + ["A--B"]
        obs = pd.DataFrame({
            "Guides_collapsed_by_gene": labels,
            "Total_number_of_guides": [1] * 10 + [2],
            "Total_RNA_count": self.counts.sum(axis=1),
            "Total_unique_genes": (self.counts > 0).sum(axis=1),
            "Percent_mitochondrial_reads": np.repeat(1.0, 11),
        }, index=[f"cell{i}" for i in range(11)])
        # Legacy-style numeric var index proves symbols come from raw.var fields.
        var = pd.DataFrame({"features": ["A", "B", "C", "D", "RARE"]}, index=[str(i) for i in range(5)])
        data = ad.AnnData(sparse.csr_matrix(self.counts), obs=obs, var=var)
        data.raw = data.copy()
        data.X = sparse.csr_matrix(np.log1p(self.counts))  # deliberately not benchmark normalization
        data.write_h5ad(self.h5ad)

    def tearDown(self):
        self.temporary.cleanup()

    def arguments(self, name="prepared", *extra):
        return MODULE.parser().parse_args([
            "--h5ad", str(self.h5ad), "--sig-list", str(self.sig),
            "--output", str(self.root / name), "--disable-qc",
            "--min-perturbed-cells", "3", "--top-targets", "1", "--chunk-size", "2", *extra,
        ])

    def read_rows(self, name, filename):
        with (self.root / name / filename).open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    def test_frozen_mean_log_effect_and_NT_only_expression(self):
        original_hash = MODULE.sha256(self.h5ad)
        manifest = MODULE.prepare(self.arguments())
        self.assertEqual(original_hash, MODULE.sha256(self.h5ad))
        self.assertEqual((self.root / "prepared" / "hubs.txt").read_text(), "A\n")
        self.assertEqual(manifest["counts"]["inference_NT_cells"], 4)
        self.assertEqual(manifest["counts"]["eligible_hubs"], 1)
        self.assertEqual(manifest["counts"]["selected_expression_genes"], 2)
        self.assertFalse(manifest["settings"]["SuperCell"])
        reference = self.read_rows("prepared", "reference.tsv")
        self.assertEqual(len(reference), 1)
        self.assertEqual((reference[0]["source"], reference[0]["target"]), ("A", "C"))
        expected = np.log2(1 + self.counts * 1e6 / self.counts.sum(axis=1)[:, None])
        effect = expected[4:7].mean(axis=0) - expected[:4].mean(axis=0)
        self.assertAlmostEqual(float(reference[0]["logFC"]), effect[2], places=9)
        self.assertEqual(int(reference[0]["label"]), int(abs(effect[2]) > 0.25))
        expression = self.read_rows("prepared", "expression.exp")
        by_gene = {row["geneSymbol"]: row for row in expression}
        self.assertEqual(set(by_gene), {"A", "C"})
        self.assertEqual(set(by_gene["A"]), {"isoformId", "geneSymbol", "cell0", "cell1", "cell2", "cell3"})
        for column in range(4):
            self.assertAlmostEqual(float(by_gene["C"][f"cell{column}"]), expected[column, 2], places=9)
        selection = {row["gene"]: row for row in self.read_rows("prepared", "gene_selection.tsv")}
        self.assertEqual(selection["RARE"]["passes_detection"], "0")
        self.assertEqual(selection["B"]["source_status"], "fails_strict_self_knockdown_cutoff")
        cells = {row["cell"]: row for row in self.read_rows("prepared", "cell_selection.tsv")}
        self.assertEqual(cells["cell10"]["role"], "excluded_not_exact_single_guide")
        self.assertEqual(manifest["counts"]["explicit_nonself_reference_pairs"], 1)
        self.assertEqual(manifest["inputs"]["h5ad"]["sha256"], original_hash)
        saved = json.loads((self.root / "prepared" / "prepare_manifest.json").read_text())
        self.assertEqual(saved["protocol"], manifest["protocol"])

    def test_all_targets_and_chunk_invariance(self):
        first = MODULE.prepare(self.arguments("a", "--top-targets", "0", "--chunk-size", "1"))
        second = MODULE.prepare(self.arguments("b", "--top-targets", "0", "--chunk-size", "11"))
        self.assertEqual(first["counts"], second["counts"])
        self.assertEqual(first["counts"]["selected_expression_genes"], 4)
        self.assertEqual(first["counts"]["explicit_nonself_reference_pairs"], 3)
        for name in ("expression.exp", "reference.tsv", "hubs.txt"):
            self.assertEqual((self.root / "a" / name).read_bytes(), (self.root / "b" / name).read_bytes())

    def test_existing_output_is_never_overwritten(self):
        args = self.arguments()
        MODULE.prepare(args)
        reference = self.root / "prepared" / "reference.tsv"
        before = reference.read_bytes()
        with self.assertRaises(FileExistsError):
            MODULE.prepare(args)
        self.assertEqual(reference.read_bytes(), before)

    def test_QC_uses_scaled_unlogged_MAD_and_upper_only_mito(self):
        obs = pd.DataFrame({"Total_RNA_count": [10, 20, 30, 40, 1000],
                            "Total_unique_genes": [10, 20, 30, 40, 50],
                            "Percent_mitochondrial_reads": [0, 1, 2, 3, 100]})
        mask, _, threshold, _ = MODULE.qc_mask(obs, 3)
        self.assertAlmostEqual(threshold["Total_RNA_count"]["scaled_MAD"], 1.4826 * 10)
        self.assertAlmostEqual(threshold["Total_RNA_count"]["upper"], 30 + 3 * 1.4826 * 10)
        self.assertIsNone(threshold["Percent_mitochondrial_reads"]["lower"])
        self.assertEqual(mask.tolist(), [True, True, True, True, False])

    def test_positive_label_cutoff_is_configurable(self):
        manifest = MODULE.prepare(self.arguments("boundary", "--response-logfc", "1000"))
        self.assertEqual(manifest["counts"]["reference_positive_pairs"], 0)
        self.assertEqual(self.read_rows("boundary", "reference.tsv")[0]["label"], "0")

    def test_effect_cutoffs_are_strict_at_equality(self):
        normalized = MODULE.log2_cpm(sparse.csr_matrix(self.counts), self.counts.sum(axis=1))
        nt_mean = np.asarray(normalized[:4].sum(axis=0)).ravel() / 4
        delta = np.asarray(normalized[4:7].sum(axis=0)).ravel() / 3 - nt_mean
        MODULE.prepare(self.arguments("equal_response", "--chunk-size", "11", "--response-logfc", str(abs(delta[2]))))
        self.assertEqual(self.read_rows("equal_response", "reference.tsv")[0]["label"], "0")
        MODULE.prepare(self.arguments("below_response", "--chunk-size", "11", "--response-logfc", str(np.nextafter(abs(delta[2]), -np.inf))))
        self.assertEqual(self.read_rows("below_response", "reference.tsv")[0]["label"], "1")
        with self.assertRaisesRegex(ValueError, "strict self-knockdown"):
            MODULE.prepare(self.arguments("equal_self", "--chunk-size", "11", "--self-logfc", str(delta[0])))
        self.assertFalse((self.root / "equal_self").exists())

    def test_reject_missing_raw_and_library_mismatch_before_writing(self):
        data = ad.read_h5ad(self.h5ad)
        data.raw = None
        data.write_h5ad(self.root / "no_raw.h5ad")
        args = self.arguments("no_raw_output", "--h5ad", str(self.root / "no_raw.h5ad"))
        with self.assertRaisesRegex(ValueError, "raw.X"):
            MODULE.prepare(args)
        self.assertFalse(args.output.exists())
        data = ad.read_h5ad(self.h5ad)
        data.obs.loc["cell0", "Total_RNA_count"] += 1
        data.write_h5ad(self.root / "bad_library.h5ad")
        args = self.arguments("bad_output", "--h5ad", str(self.root / "bad_library.h5ad"))
        with self.assertRaisesRegex(ValueError, "library totals"):
            MODULE.prepare(args)
        self.assertFalse(args.output.exists())


if __name__ == "__main__":
    unittest.main()
