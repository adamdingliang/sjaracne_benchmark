#!/usr/bin/env python3
"""Prepare a frozen, public-data THP-1 sampling pilot (not exact Figure 6a).

Counts are streamed from read-only ``raw.X``. Response labels follow the active
author code's mean-input-log-expression effect definition, but the reconstructed
QC, SIG annotation, target panel and absence of SuperCell are explicit deviations.
The FR-Perturb effect-size table is deliberately not used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import platform
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse
import scipy


NT_LABEL = "non-targeting"
PAPER_URL = "https://www.nature.com/articles/s41467-025-59620-6"
AUTHOR_CODE_URL = (
    "https://github.com/jyyulab/scMINER_analysis/blob/"
    "c39f0aaffc22be81ae425adf9e7617504ae9ee33/"
    "network_inference/CROP_Seq_GRN_evaluation/Yao_Regev_Cleary/DE_plot_ROC.Rmd"
)
QC_FIELDS = ("Total_RNA_count", "Total_unique_genes", "Percent_mitochondrial_reads")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gene_names(var: pd.DataFrame) -> np.ndarray:
    """Resolve legacy H5AD symbols, never silently map duplicate names."""
    field = next((name for name in ("features", "_index") if name in var), None)
    names = np.asarray(var[field] if field else var.index, dtype=str)
    if any(not name or "\t" in name or "\n" in name for name in names):
        raise ValueError("Gene symbols must be nonempty and contain no tabs/newlines")
    if len(set(names)) != len(names):
        raise ValueError("Raw gene symbols are not unique; explicit mapping is required")
    return names


def qc_mask(obs: pd.DataFrame, multiplier: float, enabled: bool = True):
    """Unlogged metrics; scaled MAD=1.4826*median(abs(x-median(x)))."""
    missing = set(QC_FIELDS) - set(obs.columns)
    if missing:
        raise ValueError(f"Missing required cell QC metadata: {sorted(missing)}")
    values = obs.loc[:, QC_FIELDS].apply(pd.to_numeric, errors="coerce")
    valid = np.isfinite(values.to_numpy()).all(axis=1)
    valid &= values["Total_RNA_count"].to_numpy() > 0
    valid &= values["Total_unique_genes"].to_numpy() >= 0
    valid &= values["Percent_mitochondrial_reads"].to_numpy() >= 0
    if not valid.any():
        raise ValueError("No cells have finite, valid library/feature/mitochondrial metadata")
    mask = valid.copy()
    thresholds = {}
    passes = {}
    for key in QC_FIELDS:
        data = values.loc[valid, key].to_numpy(dtype=float)
        median = float(np.median(data))
        mad = float(1.4826 * np.median(np.abs(data - median)))
        lower, upper = median - multiplier * mad, median + multiplier * mad
        field_values = values[key].to_numpy(dtype=float)
        field_pass = valid & (field_values <= upper)
        upper_only = key == "Percent_mitochondrial_reads"
        if not upper_only:
            field_pass &= field_values >= lower
        if enabled:
            mask &= field_pass
        passes[key] = field_pass
        thresholds[key] = {
            "median": median,
            "scaled_MAD": mad,
            "lower": None if upper_only else lower,
            "upper": upper,
            "rule": "upper_only" if upper_only else "both_sides",
        }
    return mask, values, thresholds, passes


def read_counts(raw_x, row_indices: np.ndarray, chunk_size: int):
    for start in range(0, len(row_indices), chunk_size):
        indices = row_indices[start : start + chunk_size]
        counts = raw_x[indices, :]
        counts = sparse.csr_matrix(counts, dtype=np.float64)
        counts.eliminate_zeros()
        if not np.isfinite(counts.data).all() or np.any(counts.data < 0):
            raise ValueError("raw.X contains negative or nonfinite values")
        if not np.allclose(counts.data, np.rint(counts.data), rtol=0, atol=1e-8):
            raise ValueError("raw.X is not untransformed integer-valued counts")
        library = np.asarray(counts.sum(axis=1)).ravel()
        if np.any(library <= 0):
            raise ValueError("A retained cell has an empty raw-count library")
        yield indices, counts, library


def log2_cpm(counts, library):
    transformed = counts.copy()
    row_scale = np.repeat(1e6 / library, np.diff(transformed.indptr))
    transformed.data = np.log2(1 + transformed.data * row_scale)
    return transformed


def write_tsv(path: Path, columns, rows):
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def prepare(args) -> dict:
    h5ad_path = Path(args.h5ad).resolve(strict=True)
    sig_path = Path(args.sig_list).resolve(strict=True)
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"Output must be fresh; refusing existing path: {output}")
    if args.top_targets < 0 or args.chunk_size < 1:
        raise ValueError("top-targets must be >=0 and chunk-size must be positive")
    if args.min_detected_cells < 1 or args.min_perturbed_cells < 1:
        raise ValueError("Cell-count thresholds must be positive")
    if not math.isfinite(args.qc_mad) or args.qc_mad < 0:
        raise ValueError("qc-mad must be finite and nonnegative")
    if not math.isfinite(args.self_logfc) or not math.isfinite(args.response_logfc):
        raise ValueError("Effect thresholds must be finite")
    if args.response_logfc < 0:
        raise ValueError("response-logfc must be nonnegative")
    sig_genes = set(sig_path.read_text(encoding="utf-8-sig").split())
    if not sig_genes:
        raise ValueError("SIG list is empty")

    data = ad.read_h5ad(h5ad_path, backed="r")
    try:
        if data.raw is None:
            raise ValueError("H5AD must contain untransformed counts in raw.X")
        obs = data.obs.copy()
        genes = gene_names(data.raw.var)
        if not obs.index.is_unique:
            raise ValueError("Cell identifiers are not unique")
        if any("\t" in str(cell) or "\n" in str(cell) for cell in obs.index):
            raise ValueError("Cell identifiers contain tabs/newlines")
        missing = {"Guides_collapsed_by_gene", "Total_number_of_guides"} - set(obs)
        if missing:
            raise ValueError(f"Missing guide metadata: {sorted(missing)}")
        labels = obs["Guides_collapsed_by_gene"].astype("string").fillna("").to_numpy(dtype=str)
        guides = pd.to_numeric(obs["Total_number_of_guides"], errors="coerce").to_numpy()
        strict_single = (guides == 1) & (labels != "")
        strict_single &= np.asarray(["--" not in label for label in labels])
        retained, values, thresholds, metric_pass = qc_mask(obs, args.qc_mad, not args.disable_qc)
        nt_mask = retained & strict_single & (labels == NT_LABEL)
        n_nt = int(nt_mask.sum())
        if n_nt < 2:
            raise ValueError(f"Need >=2 retained exact-label, one-guide NT cells; got {n_nt}")
        group_counts = pd.Series(labels[retained & strict_single]).value_counts().to_dict()
        gene_positions = {gene: index for index, gene in enumerate(genes)}
        candidates = sorted(
            gene for gene in sig_genes & set(genes)
            if group_counts.get(gene, 0) >= args.min_perturbed_cells
        )
        if not candidates:
            raise ValueError("No expressed SIG perturbation has enough retained one-guide cells")
        group_index = {gene: index for index, gene in enumerate(candidates)}
        cell_group = np.asarray([group_index.get(label, -1) for label in labels])
        n_genes = len(genes)
        detection = np.zeros(n_genes, dtype=np.int64)
        group_sums = np.zeros((len(candidates), n_genes), dtype=np.float64)
        nt_sum = np.zeros(n_genes, dtype=np.float64)
        nt_sum_sq = np.zeros(n_genes, dtype=np.float64)
        max_library_difference = 0.0
        for indices, counts, library in read_counts(data.raw.X, np.flatnonzero(retained), args.chunk_size):
            declared = values.iloc[indices]["Total_RNA_count"].to_numpy(dtype=float)
            difference = np.abs(declared - library)
            max_library_difference = max(max_library_difference, float(difference.max()))
            if not np.allclose(declared, library, rtol=1e-6, atol=1e-6):
                raise ValueError("Total_RNA_count does not match raw.X library totals")
            detection += np.asarray((counts > 0).sum(axis=0)).ravel().astype(np.int64)
            expression = log2_cpm(counts, library)
            chunk_nt = nt_mask[indices]
            if chunk_nt.any():
                nt_values = expression[chunk_nt]
                nt_sum += np.asarray(nt_values.sum(axis=0)).ravel()
                squared = nt_values.copy()
                squared.data **= 2
                nt_sum_sq += np.asarray(squared.sum(axis=0)).ravel()
            chunk_group = cell_group[indices]
            chunk_single = strict_single[indices]
            for group in np.unique(chunk_group[chunk_single & (chunk_group >= 0)]):
                group_rows = chunk_single & (chunk_group == group)
                group_sums[group] += np.asarray(expression[group_rows].sum(axis=0)).ravel()
        gene_pass = detection >= args.min_detected_cells
        nt_mean = nt_sum / n_nt
        nt_variance = np.maximum(0, nt_sum_sq / n_nt - nt_mean**2)
        response = {}
        self_effect = {}
        for gene in candidates:
            delta = group_sums[group_index[gene]] / group_counts[gene] - nt_mean
            self_effect[gene] = float(delta[gene_positions[gene]])
            if gene_pass[gene_positions[gene]] and self_effect[gene] < args.self_logfc:
                response[gene] = delta
        hubs = sorted(response)
        if not hubs:
            raise ValueError("No SIG sources pass detection and the strict self-knockdown cutoff")
        eligible_positions = np.flatnonzero(gene_pass)
        # Stable secondary key is gene symbol, not H5AD input order.
        variance_rank = sorted(eligible_positions, key=lambda i: (-nt_variance[i], genes[i]))
        top_positions = variance_rank if args.top_targets == 0 else variance_rank[: args.top_targets]
        selected_positions = sorted(set(top_positions) | {gene_positions[hub] for hub in hubs}, key=lambda i: genes[i])
        selected_genes = genes[selected_positions]
        selected_set = set(selected_genes)
        top_set = set(genes[top_positions])
        nt_indices = np.flatnonzero(nt_mask)
        nt_column = {index: column for column, index in enumerate(nt_indices)}
        input_matrix = np.empty((len(selected_positions), n_nt), dtype=np.float64)
        for indices, counts, library in read_counts(data.raw.X, nt_indices, args.chunk_size):
            chunk_expression = log2_cpm(counts, library)[:, selected_positions].toarray()
            columns = [nt_column[index] for index in indices]
            input_matrix[:, columns] = chunk_expression.T

        output.mkdir(parents=True, exist_ok=False)
        expression_path = output / "expression.exp"
        write_tsv(
            expression_path,
            ["isoformId", "geneSymbol", *obs.index[nt_indices].astype(str)],
            ([gene, gene, *(format(value, ".12g") for value in row)]
             for gene, row in zip(selected_genes, input_matrix)),
        )
        with (output / "hubs.txt").open("x", encoding="utf-8") as handle:
            handle.write("\n".join(hubs) + "\n")
        n_positive = 0
        with (output / "reference.tsv").open("x", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["source", "target", "logFC", "label"])
            for hub in hubs:
                for target, position in zip(selected_genes, selected_positions):
                    if target == hub:
                        continue
                    effect = float(response[hub][position])
                    positive = int(abs(effect) > args.response_logfc)
                    n_positive += positive
                    writer.writerow([hub, target, format(effect, ".12g"), positive])

        hub_set = set(hubs)
        def cell_rows():
            for i, cell in enumerate(obs.index):
                if not retained[i]:
                    role = "excluded_QC"
                elif not strict_single[i]:
                    role = "excluded_not_exact_single_guide"
                elif nt_mask[i]:
                    role = "inference_NT_and_response_control"
                elif labels[i] in hub_set:
                    role = "response_KD"
                else:
                    role = "detection_only_not_eligible_SIG_source"
                yield [str(cell), labels[i], guides[i], int(retained[i]), int(strict_single[i]),
                       *(int(metric_pass[key][i]) for key in QC_FIELDS), role]
        write_tsv(output / "cell_selection.tsv", ["cell", "guide_label", "guide_count", "QC_retained", "strict_single_guide",
                  *[f"passes_{key}" for key in QC_FIELDS], "role"], cell_rows())

        def gene_rows():
            for i, gene in enumerate(genes):
                if gene not in sig_genes:
                    reason = "not_in_SIG_list"
                elif group_counts.get(gene, 0) < args.min_perturbed_cells:
                    reason = "too_few_retained_single_guide_cells"
                elif not gene_pass[i]:
                    reason = "fails_gene_detection"
                elif gene not in hub_set:
                    reason = "fails_strict_self_knockdown_cutoff"
                else:
                    reason = "eligible_SIG_source"
                selection = "NT_variance" if gene in top_set else "eligible_hub_union" if gene in selected_set else "not_selected"
                yield [gene, detection[i], int(gene_pass[i]), format(nt_mean[i], ".12g"),
                       format(nt_variance[i], ".12g"), int(gene in sig_genes), group_counts.get(gene, 0),
                       format(self_effect[gene], ".12g") if gene in self_effect else "", int(gene in hub_set),
                       reason, int(gene in selected_set), selection]
        write_tsv(output / "gene_selection.tsv", ["gene", "detected_QC_cells", "passes_detection", "NT_mean_log2_CPM_plus1",
                  "NT_variance_population", "in_repo_SIG_list", "retained_single_guide_KD_cells", "self_logFC",
                  "eligible_hub", "source_status", "selected", "selection_reason"], gene_rows())

        n_pairs = len(hubs) * (len(selected_genes) - 1)
        manifest = {
            "schema_version": 1,
            "protocol": "public_data_single_cell_sampling_pilot_not_exact_scMINER_Figure_6a",
            "implementation": {"prepare_script_sha256": sha256(Path(__file__).resolve()),
                               "Python": platform.python_version(), "anndata": importlib.metadata.version("anndata"),
                               "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__},
            "inputs": {"h5ad": {"path": str(h5ad_path), "sha256": sha256(h5ad_path)},
                       "SIG_list": {"path": str(sig_path), "sha256": sha256(sig_path)}},
            "settings": {"normalization": "log2(1 + 1e6 * raw_count / raw_library_total)",
                         "QC_enabled": not args.disable_qc, "QC_scale": "unlogged_metadata",
                         "QC_MAD_definition": "1.4826 * median(abs(x - median(x)))",
                         "QC_MAD_multiplier": args.qc_mad, "QC_thresholds": thresholds,
                         "min_detected_QC_cells": args.min_detected_cells,
                         "min_retained_single_guide_KD_cells": args.min_perturbed_cells,
                         "self_KD_logFC_strictly_less_than": args.self_logfc,
                         "positive_abs_logFC_strictly_greater_than": args.response_logfc,
                         "FDR_filter": None, "top_NT_variance_targets": args.top_targets,
                         "target_selection": "NT variance only, then union all eligible hubs",
                         "variance_definition": "population variance of NT log2(CPM+1)",
                         "guide_rule": "exact one-guide target label; no splitting single hyphens",
                         "inference_cells": "QC-retained exact non-targeting one-guide cells only",
                         "SuperCell": False, "chunk_size": args.chunk_size},
            "counts": {"input_cells": int(data.n_obs), "input_raw_genes": n_genes,
                       "QC_retained_cells": int(retained.sum()), "QC_excluded_cells": int((~retained).sum()),
                       "retained_exact_single_guide_cells": int((retained & strict_single).sum()),
                       "inference_NT_cells": n_nt, "SIG_list_unique_genes": len(sig_genes),
                       "SIG_not_in_raw_expression": len(sig_genes - set(genes)),
                       "candidate_SIG_sources_with_enough_cells": len(candidates),
                       "candidate_sources_failing_detection": int(sum(not gene_pass[gene_positions[g]] for g in candidates)),
                       "candidate_sources_failing_self_KD": int(sum(gene_pass[gene_positions[g]] and g not in hub_set for g in candidates)),
                       "eligible_hubs": len(hubs), "genes_passing_detection": int(gene_pass.sum()),
                       "selected_expression_genes": len(selected_genes), "explicit_nonself_reference_pairs": n_pairs,
                       "reference_positive_pairs": n_positive, "reference_negative_pairs": n_pairs - n_positive},
            "diagnostics": {"max_declared_vs_raw_library_difference": max_library_difference},
            "limitations": [
                "Reconstructed mean-log2CPM response labels, not author-prepared scran RData or FR-Perturb labels.",
                "QC transformation/scaling and exact author eligibility inputs are not recoverable from available scripts.",
                "Uses repo SIG list, not missing author strict SIG annotation.",
                "Uses individual NT cells, not published SuperCell gamma20/n.pc10 aggregates.",
                "Restricts inference and evaluation to eligible assayed SIG hubs; this changes original DPI hub context.",
                "Default NT-variance target panel is a pilot subset, not the published whole-expression panel.",
                "Perturbation responses can be indirect; reference-negative means below response cutoff, not proven no regulation.",
            ],
            "sources": {"paper": PAPER_URL, "pinned_author_active_label_code": AUTHOR_CODE_URL},
            "files": {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
                      for path in sorted(output.iterdir())},
        }
        with (output / "prepare_manifest.json").open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, allow_nan=False)
            handle.write("\n")
        return manifest
    finally:
        data.file.close()


def parser():
    command = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    command.add_argument("--h5ad", required=True, type=Path)
    command.add_argument("--sig-list", required=True, type=Path)
    command.add_argument("--output", required=True, type=Path, help="Fresh output directory; existing paths are refused")
    command.add_argument("--top-targets", type=int, default=2000, help="Top NT-variance detected genes; 0=all; always union eligible hubs")
    command.add_argument("--min-detected-cells", type=int, default=2)
    command.add_argument("--min-perturbed-cells", type=int, default=20)
    command.add_argument("--self-logfc", type=float, default=-0.1, help="Strict upper bound for source's own mean-log-expression effect")
    command.add_argument("--response-logfc", type=float, default=0.25, help="Strict absolute effect threshold; no FDR filter")
    command.add_argument("--qc-mad", type=float, default=3)
    command.add_argument("--disable-qc", action="store_true", help="Disable MAD cutoffs; still reject invalid metadata")
    command.add_argument("--chunk-size", type=int, default=1024)
    return command


def main(argv=None):
    arguments = parser().parse_args(argv)
    try:
        manifest = prepare(arguments)
    except (ValueError, OSError) as error:
        print(f"Preparation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(arguments.output.resolve()), "protocol": manifest["protocol"], "counts": manifest["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
