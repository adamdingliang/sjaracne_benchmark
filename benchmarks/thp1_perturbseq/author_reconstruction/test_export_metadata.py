"""Small fabricated-fixture tests; never read the live THP-1 dataset."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


HERE = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metadata = load_module("export_metadata")
resources = load_module("fetch_resources")


class MetadataTests(unittest.TestCase):
    def test_distinct_target_policy_preserves_hyphenated_gene(self):
        self.assertEqual(metadata.collapse_label("ARPC4-TTLL3"), ("ARPC4-TTLL3", 1, 1))
        self.assertEqual(metadata.collapse_label("CEBPB--CEBPB"), ("CEBPB", 1, 2))
        self.assertEqual(metadata.collapse_label("CEBPB--STAT1"), ("", 2, 2))
        self.assertEqual(metadata.collapse_label("non-targeting--CEBPB"), ("", 2, 2))
        self.assertEqual(metadata.collapse_label("non-targeting--non-targeting"), ("non-targeting", 1, 2))
        self.assertEqual(metadata.collapse_label(""), ("", 0, 0))
        with self.assertRaises(ValueError):
            metadata.collapse_label("CEBPB--")

    def test_export_readonly_categorical_h5ad_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            counts = sparse.csr_matrix(np.array([[4, 2, 0], [1, 4, 0], [0, 1, 3],
                                                 [0, 0, 2], [2, 2, 3], [1, 0, 0]], dtype=float))
            labels = ["non-targeting", "non-targeting--non-targeting", "CEBPB--CEBPB",
                      "CEBPB--STAT1", "ARPC4-TTLL3", ""]
            obs = pd.DataFrame({
                "Guides_collapsed_by_gene": pd.Categorical(labels),
                "Total_number_of_guides": [1, 2, 2, 2, 1, 0],
                "Total_RNA_count": np.asarray(counts.sum(axis=1)).ravel(),
                "Total_unique_genes": np.asarray((counts > 0).sum(axis=1)).ravel(),
                "Percent_mitochondrial_reads": [0, 1, 0, 2, 0, 0],
                "Biological_replicate": pd.Categorical(["R1"] * 3 + ["R2"] * 3),
            }, index=[f"cell{i}" for i in range(6)])
            var = pd.DataFrame({"features": ["CEBPB", "STAT1", "ARPC4-TTLL3"]}, index=["0", "1", "2"])
            data = ad.AnnData(counts, obs=obs, var=var)
            data.raw = data.copy()
            path = root / "fixture.h5ad"
            data.write_h5ad(path)
            before = metadata.sha256(path)
            manifest = metadata.export(path, root / "export")
            self.assertEqual(before, metadata.sha256(path))
            self.assertEqual(manifest["h5ad"]["sha256"], before)
            self.assertEqual(manifest["raw_counts"]["shape"], [6, 3])
            self.assertEqual(manifest["pure_NT_cells_before_QC"], 2)
            self.assertEqual(manifest["reported_guide_count_vs_label_tokens_mismatches"], 0)
            cells = pd.read_csv(root / "export/cells.tsv", sep="\t", keep_default_na=False)
            self.assertEqual(list(cells.cell_index), list(range(6)))
            self.assertEqual(list(cells.single_gene_group), ["non-targeting", "non-targeting", "CEBPB", "", "ARPC4-TTLL3", ""])
            genes = pd.read_csv(root / "export/genes.tsv", sep="\t")
            self.assertEqual(list(genes.gene), ["CEBPB", "STAT1", "ARPC4-TTLL3"])
            for name in ("cells.tsv", "genes.tsv"):
                self.assertEqual(manifest["metadata_files"][name]["sha256"], metadata.sha256(root / "export" / name))
            with self.assertRaises(FileExistsError):
                metadata.export(path, root / "export")

    def test_duplicate_symbols_fail(self):
        with self.assertRaises(ValueError):
            metadata.resolve_genes(pd.DataFrame({"features": ["A", "A"]}))

    def test_pinned_resources_fail_closed_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pin_path = root / "pins.json"
            pin_path.write_text(json.dumps({"resources": [{"filename": "a.R", "url": "https://example.invalid/a.R", "sha256": "0" * 64}]}))
            class FakeResponse:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self): return b"unexpected content"
            with patch.object(resources, "urlopen", return_value=FakeResponse()):
                with self.assertRaises(ValueError):
                    resources.fetch(root / "resources", pin_path)
            self.assertFalse((root / "resources").exists())


if __name__ == "__main__":
    unittest.main()
