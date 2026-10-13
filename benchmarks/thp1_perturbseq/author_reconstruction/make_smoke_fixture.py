#!/usr/bin/env python3
"""Create a tiny explicitly synthetic H5AD and metadata for R integration smoke.

Not a scientific benchmark. Requires a fresh --output directory; no live input
is used. Suggested R smoke uses the pinned real resources and default settings.
"""

import argparse
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

from export_metadata import export


def create(output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"Output must be fresh: {output}")
    rng = np.random.default_rng(17)
    genes = ["MYD88", "IFNGR2"] + [f"synthetic_{i:03d}" for i in range(118)]
    labels = (["non-targeting"] * 56 + ["non-targeting--non-targeting"] * 4 +
              ["MYD88"] * 30 + ["MYD88--MYD88"] * 10 + ["IFNGR2"] * 40 + ["MYD88--IFNGR2"] * 20)
    counts = rng.poisson(rng.uniform(1, 5, size=len(genes)), size=(len(labels), len(genes))).astype(float)
    counts[:, :2] = rng.poisson(30, size=(len(labels), 2)) + 1
    counts[60:100, 0] = 1
    counts[100:140, 1] = 1
    raw = sparse.csr_matrix(counts)
    obs = pd.DataFrame({
        "Guides_collapsed_by_gene": pd.Categorical(labels),
        "Total_number_of_guides": [2 if "--" in label else 1 for label in labels],
        "Total_RNA_count": counts.sum(axis=1),
        "Total_unique_genes": (counts > 0).sum(axis=1),
        "Percent_mitochondrial_reads": rng.uniform(0, 2, size=len(labels)),
        "Biological_replicate": pd.Categorical(["synthetic_R1"] * len(labels)),
    }, index=[f"synthetic_cell_{i:04d}" for i in range(len(labels))])
    var = pd.DataFrame({"features": genes}, index=[str(i) for i in range(len(genes))])
    data = ad.AnnData(raw, obs=obs, var=var)
    data.raw = data.copy()
    output.mkdir(parents=True, exist_ok=False)
    h5ad = output / "synthetic.h5ad"
    data.write_h5ad(h5ad)
    export(h5ad, output / "metadata")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    create(args.output.resolve())
