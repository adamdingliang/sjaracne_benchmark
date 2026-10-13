#!/usr/bin/env python3
"""Read-only H5AD metadata bridge for author-style THP-1 R reconstruction.

Counts remain in the original H5AD: R opens /raw/X with HDF5Array. This exports
cell/gene names and guide groups without converting 1 GB of counts or changing
the source file. The source hash binds the Python metadata to R's count input.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import anndata as ad
import h5py
import numpy as np
import pandas as pd


QC_FIELDS = ("Total_RNA_count", "Total_unique_genes", "Percent_mitochondrial_reads")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collapse_label(value: str) -> tuple[str, int, int]:
    """Collapse repeated guides to ONE target, never collapse distinct targets.

    The delimiter is literal '--', not '-', which is part of real gene symbols.
    The reconstruction accepts CEBPB--CEBPB, rejects CEBPB--STAT1 and rejects
    control+target mixed labels. The author's missing preprocessing cannot be
    assumed to have used exactly this representation; it is recorded explicitly.
    """
    if not value:
        return "", 0, 0
    tokens = value.split("--")
    if any(not token for token in tokens):
        raise ValueError(f"Malformed guide label: {value!r}")
    distinct = set(tokens)
    return (tokens[0] if len(distinct) == 1 else "", len(distinct), len(tokens))


def resolve_genes(var: pd.DataFrame) -> np.ndarray:
    field = next((name for name in ("features", "_index") if name in var), None)
    names = np.asarray(var[field] if field else var.index, dtype=str)
    if len(set(names)) != len(names):
        raise ValueError("Raw gene symbols are duplicated; explicit mapping is required")
    if any(not name or any(char in name for char in "\t\r\n") for name in names):
        raise ValueError("Invalid empty/tab/newline gene symbol")
    return names


def export(h5ad: Path, output: Path) -> dict:
    h5ad = h5ad.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Output must be fresh: {output}")
    data = ad.read_h5ad(h5ad, backed="r")
    try:
        if data.raw is None:
            raise ValueError("Untransformed raw.X counts are required")
        obs = data.obs.copy()
        required = set(QC_FIELDS) | {"Guides_collapsed_by_gene", "Total_number_of_guides"}
        if required - set(obs):
            raise ValueError(f"Missing metadata fields: {sorted(required - set(obs))}")
        if not obs.index.is_unique:
            raise ValueError("Cell identifiers must be unique")
        cell_ids = obs.index.astype(str)
        if any(not cell or any(char in cell for char in "\t\r\n") for cell in cell_ids):
            raise ValueError("Invalid cell identifier")
        genes = resolve_genes(data.raw.var)
        labels = obs["Guides_collapsed_by_gene"].astype("string").fillna("").to_numpy(dtype=str)
        collapsed = [collapse_label(label) for label in labels]
        cells = pd.DataFrame({
            "cell_index": np.arange(len(obs)),
            "cell_id": cell_ids,
            "original_guide_label": labels,
            "single_gene_group": [item[0] for item in collapsed],
            "n_distinct_targets": [item[1] for item in collapsed],
            "n_guide_label_tokens": [item[2] for item in collapsed],
            "Total_number_of_guides": pd.to_numeric(obs["Total_number_of_guides"], errors="coerce").to_numpy(),
        })
        for field in QC_FIELDS:
            cells[field] = pd.to_numeric(obs[field], errors="coerce").to_numpy()
        if "Biological_replicate" in obs:
            cells["Biological_replicate"] = obs["Biological_replicate"].astype("string").fillna("").to_numpy(dtype=str)
        gene_table = pd.DataFrame({"gene_index": np.arange(len(genes)), "gene": genes})
        if data.raw.shape != (len(cells), len(genes)):
            raise ValueError("Metadata/raw count dimensions do not agree")
        with h5py.File(h5ad, "r") as handle:
            raw = handle["raw/X"]
            encoding = raw.attrs.get("encoding-type", raw.attrs.get("h5sparse_format", ""))
            if isinstance(encoding, bytes):
                encoding = encoding.decode()
            if str(encoding) not in {"csr_matrix", "csr"}:
                raise ValueError(f"Expected raw.X CSR storage, got {encoding!r}")
            nnz = int(raw["data"].shape[0])
        declared = cells["Total_number_of_guides"].to_numpy()
        token_counts = cells["n_guide_label_tokens"].to_numpy()
        mismatch = np.isfinite(declared) & (declared != token_counts)
        manifest = {
            "schema_version": 1,
            "scope": "author-style reconstruction metadata, not recovered author intermediate objects",
            "h5ad": {"path": str(h5ad), "size_bytes": h5ad.stat().st_size, "sha256": sha256(h5ad)},
            "raw_counts": {"group": "/raw/X", "stored_order": "cells_by_genes", "shape": list(data.raw.shape),
                           "encoding": str(encoding), "stored_nnz": nnz},
            "guide_policy": "one distinct collapsed target; repeat same-target labels accepted; mixed labels excluded",
            "guide_label_delimiter": "--",
            "reported_guide_count_vs_label_tokens_mismatches": int(mismatch.sum()),
            "single_gene_group_cells": int((cells.n_distinct_targets == 1).sum()),
            "pure_NT_cells_before_QC": int((cells.single_gene_group == "non-targeting").sum()),
            "python": platform.python_version(),
            "packages": {package: importlib.metadata.version(package) for package in ("anndata", "numpy", "pandas", "h5py")},
            "code_sha256": sha256(Path(__file__)),
        }
        output.mkdir(parents=True, exist_ok=False)
        cells.to_csv(output / "cells.tsv", sep="\t", index=False, lineterminator="\n")
        gene_table.to_csv(output / "genes.tsv", sep="\t", index=False, lineterminator="\n")
        manifest["metadata_files"] = {
            name: {"sha256": sha256(output / name), "size_bytes": (output / name).stat().st_size}
            for name in ("cells.tsv", "genes.tsv")
        }
        with (output / "export_metadata_manifest.json").open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return manifest
    finally:
        data.file.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h5ad", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Fresh metadata directory")
    args = parser.parse_args()
    print(json.dumps(export(args.h5ad, args.output), indent=2))


if __name__ == "__main__":
    main()
