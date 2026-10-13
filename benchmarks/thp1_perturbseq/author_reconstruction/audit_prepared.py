#!/usr/bin/env python3
"""Independent bounded, read-only audit of completed author-style preparation.

Re-derive QC/group membership and log2(CPM+1) directly from original raw.X;
never import the preparation's calculation helpers or load the whole count
matrix. All NT cells and three deterministic sampled KD groups are streamed.
Only a fresh JSON report outside the prepared-input directory is written.

The pinned annotation is read by base R to stdout, not rewritten or converted
on disk. Windows can use the existing isolated WSL R environment via
--wsl-r-env; Linux can use --rscript. These are read-only diagnostics, not a
package installation or a biological correctness test.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


QC_FIELDS = ("Total_RNA_count", "Total_unique_genes", "Percent_mitochondrial_reads")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def truth_array(series: pd.Series) -> np.ndarray:
    values = series.astype(str).str.lower()
    check(values.isin(["true", "false", "1", "0"]).all(), f"Invalid boolean column {series.name}")
    return values.isin(["true", "1"]).to_numpy()


def collapsed_groups(obs: pd.DataFrame) -> np.ndarray:
    labels = obs["Guides_collapsed_by_gene"].astype("string").fillna("").to_numpy(dtype=str)
    groups = []
    for label in labels:
        parts = label.split("--") if label else []
        check(all(parts), f"Malformed raw guide label: {label}")
        distinct = set(parts)
        groups.append(next(iter(distinct)) if len(distinct) == 1 else "")
    return np.asarray(groups)


def independent_qc(obs: pd.DataFrame, nmads: float) -> tuple[np.ndarray, dict]:
    values = obs.loc[:, QC_FIELDS].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(values).all(axis=1) & (values[:, 0] > 0) & (values[:, 1] >= 0) & (values[:, 2] >= 0)
    check(valid.any(), "No valid QC metadata")
    keep = valid.copy()
    thresholds = {}
    for i, field in enumerate(QC_FIELDS):
        median = float(np.median(values[valid, i]))
        mad = float(1.4826 * np.median(np.abs(values[valid, i] - median)))
        lower, upper = median - nmads * mad, median + nmads * mad
        passed = valid & (values[:, i] <= upper)
        if i < 2:
            passed &= values[:, i] >= lower
        keep &= passed
        thresholds[field] = {"median": median, "scaled_MAD": mad, "lower": lower if i < 2 else None, "upper": upper}
    return keep, thresholds


def wsl_path(path: Path) -> str:
    windows = PureWindowsPath(str(path))
    if windows.drive:
        return "/mnt/" + windows.drive[0].lower() + "/" + "/".join(windows.parts[1:])
    return str(path)


def read_annotation(path: Path, args) -> pd.DataFrame:
    # Avoid quote-sensitive column selection and disk files: send original data
    # frame to stdout, and select its three relevant fields independently here.
    expression = "load(commandArgs(TRUE)[1]);write.table(tf_sigs,stdout(),sep=intToUtf8(9),row.names=FALSE,quote=FALSE)"
    if args.wsl_r_env:
        environment = Path(args.wsl_r_env).resolve(strict=True)
        micromamba = Path(args.wsl_micromamba).resolve(strict=True) if args.wsl_micromamba else environment.parent / "micromamba"
        command = ["wsl", "--exec", wsl_path(micromamba), "run", "-p", wsl_path(environment),
                   "Rscript", "--vanilla", "-e", expression, wsl_path(path)]
    else:
        executable = args.rscript or shutil.which("Rscript")
        check(bool(executable), "Annotation requires --rscript or --wsl-r-env (no package installation needed)")
        command = [str(executable), "--vanilla", "-e", expression, str(path)]
    result = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", timeout=120)
    table = pd.read_csv(io.StringIO(result.stdout), sep="\t", dtype=str, keep_default_na=False)
    check({"geneSymbol", "isSIG", "funcType"} <= set(table), "Unexpected pinned annotation schema")
    return table


def stream_means(raw_x, indices: np.ndarray, obs: pd.DataFrame, chunk_size: int, *,
                 memberships: dict[int, str] | None = None, sampled_metacells: list[str] | None = None,
                 sampled_genes: list[int] | None = None) -> dict:
    total = np.zeros(raw_x.shape[1], dtype=float)
    detected = np.zeros(raw_x.shape[1], dtype=np.int64)
    sampled_metacells = sampled_metacells or []
    sampled_genes = sampled_genes or []
    sums = {name: np.zeros(len(sampled_genes), dtype=float) for name in sampled_metacells}
    sizes = {name: 0 for name in sampled_metacells}
    max_library_error = 0.0
    max_feature_error = 0.0
    peak_cells = 0
    for start in range(0, len(indices), chunk_size):
        rows = indices[start : start + chunk_size]
        block = sparse.csr_matrix(raw_x[rows, :], dtype=float)
        block.eliminate_zeros()
        check(np.isfinite(block.data).all() and (block.data >= 0).all(), "Invalid raw counts")
        check(np.allclose(block.data, np.rint(block.data), rtol=0, atol=1e-8), "raw.X not integer-valued counts")
        library = np.asarray(block.sum(axis=1)).ravel()
        features = np.asarray((block > 0).sum(axis=1)).ravel()
        library_error = np.abs(library - pd.to_numeric(obs.iloc[rows].Total_RNA_count).to_numpy())
        feature_error = np.abs(features - pd.to_numeric(obs.iloc[rows].Total_unique_genes).to_numpy())
        max_library_error = max(max_library_error, float(library_error.max()))
        max_feature_error = max(max_feature_error, float(feature_error.max()))
        check(np.all(library > 0) and np.all(library_error <= 1e-6 + library * 1e-6), "Raw libraries/metadata mismatch")
        check(np.all(feature_error == 0), "Raw features/metadata mismatch")
        detected += np.asarray((block > 0).sum(axis=0)).ravel().astype(np.int64)
        # Independent row-wise transformation; denominators include every raw
        # gene BEFORE detection filtering, exactly the frozen primary protocol.
        block.data = np.log2(1 + block.data * np.repeat(1e6 / library, np.diff(block.indptr)))
        total += np.asarray(block.sum(axis=0)).ravel()
        if memberships is not None:
            names = np.asarray([memberships[int(row)] for row in rows])
            for name in sampled_metacells:
                selected = names == name
                if selected.any():
                    values = block[selected, :][:, sampled_genes]
                    sums[name] += np.asarray(values.sum(axis=0)).ravel()
                    sizes[name] += int(selected.sum())
        peak_cells = max(peak_cells, len(rows))
    check(len(indices) > 0, "Cannot average empty group")
    return {"means": total / len(indices), "detected": detected,
            "metacell_means": {name: sums[name] / sizes[name] for name in sampled_metacells},
            "metacell_sizes": sizes, "max_library_error": max_library_error,
            "max_feature_error": max_feature_error, "peak_count_chunk_cells": peak_cells}


def expression_subset(path: Path, sampled_genes: list[str]) -> tuple[list[str], list[str], dict]:
    genes = []
    values = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        check(header[:2] == ["isoformId", "geneSymbol"], "Unexpected expression header")
        check(len(set(header[2:])) == len(header[2:]), "Duplicate expression metacells")
        for row in reader:
            check(len(row) == len(header) and row[0] == row[1], "Expression row names/shape mismatch")
            genes.append(row[0])
            if row[0] in sampled_genes:
                values[row[0]] = np.asarray(row[2:], dtype=float)
    check(len(set(genes)) == len(genes), "Duplicate expression genes")
    check(set(values) == set(sampled_genes), "Missing sampled expression genes")
    return genes, header[2:], values


def positive_rows(path: Path, selected_sources: list[str]) -> dict[str, dict[str, float]]:
    selected = set(selected_sources)
    result = {source: {} for source in selected_sources}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        check({"source", "target", "effect"} <= set(reader.fieldnames or []), "Positive reference schema mismatch")
        for row in reader:
            if row["source"] in selected:
                source, target = row["source"], row["target"]
                check(target not in result[source], f"Duplicate reference target: {source}/{target}")
                result[source][target] = float(row["effect"])
    return result


def audit(args) -> dict:
    prepared = Path(args.prepared_dir).resolve(strict=True)
    resources = Path(args.resources_dir).resolve(strict=True)
    h5ad = Path(args.h5ad).resolve(strict=True)
    manifest_path = prepared / "prepare_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    check(manifest.get("status") == "complete", "Preparation not complete")
    parameters = manifest["parameters"]
    check(parameters["cpm_library"] == "raw" and not parameters["qc_log_counts"], "Audit is frozen to unlogged QC/raw-library primary protocol")
    check(args.chunk_cells >= 1 and args.tolerance > 0, "Invalid chunk size/tolerance")
    relevant = ["cell_selection.tsv", "gene_selection.tsv", "metacell_membership.tsv", "expression.exp", "hubs.txt",
                "reference_eligible_sources.tsv", "reference_positive_edges.tsv", "strict_SIG_genes.txt"]
    hashes = {name: sha256(prepared / name) for name in relevant}
    for name in relevant:
        check(hashes[name] == manifest["outputs"][name]["sha256"], f"Prepared artifact hash changed: {name}")
    check(sha256(h5ad) == manifest["input_h5ad"]["sha256"], "Original H5AD hash mismatch")
    pins = json.loads(Path(__file__).with_name("source_pins.json").read_text(encoding="utf-8"))
    annotation_pin = next(record for record in pins["resources"] if record["filename"] == "tf_sigs_hg.RData")
    annotation_path = resources / annotation_pin["filename"]
    annotation_hash = sha256(annotation_path)
    check(annotation_hash == annotation_pin["sha256"], "Annotation hash differs from fixed pin")
    manifest_annotation = next(record for record in manifest["resources"] if record["filename"] == annotation_pin["filename"])
    check(manifest_annotation["sha256"] == annotation_hash, "Preparation annotation pin differs")
    annotation = read_annotation(annotation_path, args)
    full_sig = set(annotation.loc[truth_array(annotation.isSIG), "geneSymbol"])
    strict_sig = set(annotation.loc[annotation.funcType == "SIG", "geneSymbol"])
    strict_file = set((prepared / "strict_SIG_genes.txt").read_text(encoding="utf-8").splitlines())
    check(strict_file == strict_sig, "Strict SIG list differs from pinned annotation")
    cells = pd.read_csv(prepared / "cell_selection.tsv", sep="\t", keep_default_na=False)
    genes = pd.read_csv(prepared / "gene_selection.tsv", sep="\t", keep_default_na=False)
    memberships = pd.read_csv(prepared / "metacell_membership.tsv", sep="\t", keep_default_na=False)
    eligibility = pd.read_csv(prepared / "reference_eligible_sources.tsv", sep="\t", keep_default_na=False)
    check(len(eligibility) >= 1, "No reference sources")
    check(not eligibility.source.duplicated().any(), "Duplicate eligible sources")
    rng = np.random.default_rng(args.seed)
    selected_sources = rng.choice(sorted(eligibility.source), size=min(3, len(eligibility)), replace=False).tolist()
    recorded_positive = positive_rows(prepared / "reference_positive_edges.tsv", selected_sources)
    selected_genes = rng.choice(genes.loc[truth_array(genes.used_for_network), "gene"].to_numpy(),
                                size=min(5, int(truth_array(genes.used_for_network).sum())), replace=False).tolist()
    selected_mc = rng.choice(sorted(set(memberships.metacell_name)), size=min(3, memberships.metacell_name.nunique()), replace=False).tolist()
    expression_genes, expression_mc, expression_values = expression_subset(prepared / "expression.exp", selected_genes)
    check(set(expression_mc) == set(memberships.metacell_name), "Expression/membership metacell sets differ")
    data = ad.read_h5ad(h5ad, backed="r")
    try:
        check(data.raw is not None, "Original H5AD lacks raw.X")
        raw_symbols = np.asarray(data.raw.var["features"] if "features" in data.raw.var else
                                 data.raw.var["_index"] if "_index" in data.raw.var else data.raw.var.index, dtype=str)
        check(list(raw_symbols) == list(genes.gene), "Gene indexing differs from original raw.X")
        check(list(data.obs.index.astype(str)) == list(cells.cell_id), "Cell indexing differs from original H5AD")
        check(np.array_equal(cells.cell_index.to_numpy(), np.arange(data.n_obs)), "Shifted cell indices")
        check(np.array_equal(genes.gene_index.to_numpy(), np.arange(len(raw_symbols))), "Shifted gene indices")
        obs = data.obs.copy()
        for field in QC_FIELDS:
            check(np.allclose(pd.to_numeric(cells[field]), pd.to_numeric(obs[field]), rtol=0, atol=1e-12, equal_nan=True), f"QC metadata differs: {field}")
        groups = collapsed_groups(obs)
        qc, qc_thresholds = independent_qc(obs, float(parameters["qc_mad"]))
        check(np.array_equal(qc, truth_array(cells.pass_QC)), "Independent raw-metadata QC mask differs")
        check(np.array_equal(groups, cells.single_gene_group.to_numpy()), "Guide collapsing differs from original labels")
        nt = np.flatnonzero(qc & (groups == "non-targeting"))
        nt_ids = set(obs.index[nt].astype(str))
        check(not memberships.cell_id.duplicated().any(), "NT cell assigned more than once")
        check(set(memberships.cell_id) == nt_ids, "Metacell membership is not exactly all pure NT/QCed cells")
        check(np.array_equal(truth_array(cells.used_for_NT_network), np.isin(np.arange(len(cells)), nt)), "Network-use flag differs from pure NT selection")
        check(len(nt) == manifest["QC"]["n_NT_cells"], "NT count/manifest mismatch")
        cell_positions = {name: i for i, name in enumerate(obs.index.astype(str))}
        mc_by_row = {cell_positions[row.cell_id]: row.metacell_name for row in memberships.itertuples()}
        gene_positions = {gene: i for i, gene in enumerate(raw_symbols)}
        nt_stats = stream_means(data.raw.X, nt, obs, args.chunk_cells, memberships=mc_by_row,
                                sampled_metacells=selected_mc, sampled_genes=[gene_positions[gene] for gene in selected_genes])
        detected_pass = pd.to_numeric(genes.detected_QC_cells).to_numpy() >= int(parameters["min_detected_cells"])
        check(np.array_equal(detected_pass, truth_array(genes.pass_detection_filter)), "Detection threshold/table inconsistency")
        inference_mask = detected_pass & (nt_stats["detected"] > 0)
        expected_expression_genes = raw_symbols[inference_mask].tolist()
        check(expression_genes == expected_expression_genes, "Expression is not exactly detection-passing/nonzero-NT genes in raw order")
        check(np.array_equal(inference_mask, truth_array(genes.used_for_network)), "Network gene flags differ from independently observed NT expression")
        check(np.array_equal(inference_mask, truth_array(genes.has_NT_expression)), "NT-expression flags differ")
        check(np.array_equal(np.isin(raw_symbols, list(full_sig)), truth_array(genes.isSIG_inference_annotation)), "Full-isSIG flags differ from pinned annotation")
        check(np.array_equal(np.isin(raw_symbols, list(strict_sig)), truth_array(genes.strict_SIG_reference_annotation)), "Strict-SIG flags differ from pinned annotation")
        expected_hubs = [gene for gene in expected_expression_genes if gene in full_sig]
        hubs = (prepared / "hubs.txt").read_text(encoding="utf-8").splitlines()
        check(hubs == expected_hubs, "Hubs are not exactly expressed full-isSIG genes in expression order")
        expression_checks = []
        for gene_index, gene in enumerate(selected_genes):
            for mc in selected_mc:
                expected = float(nt_stats["metacell_means"][mc][gene_index])
                observed = float(expression_values[gene][expression_mc.index(mc)])
                error = abs(expected - observed)
                check(error <= args.tolerance, f"Metacell mean mismatch {gene}/{mc}: {error}")
                expression_checks.append({"gene": gene, "metacell": mc, "n_cells": nt_stats["metacell_sizes"][mc],
                                          "raw_recomputed": expected, "expression_exp": observed, "absolute_error": error})
        effect_checks = []
        source_checks = []
        for source in selected_sources:
            kd = np.flatnonzero(qc & (groups == source))
            row = eligibility.loc[eligibility.source == source].iloc[0]
            check(source in strict_sig, f"Reference source not strict SIG: {source}")
            check(len(kd) >= int(parameters["min_perturbed_cells"]) and len(kd) == int(row.n_cells), f"KD count/eligibility mismatch: {source}")
            kd_stats = stream_means(data.raw.X, kd, obs, args.chunk_cells)
            effects = kd_stats["means"] - nt_stats["means"]
            self_effect = float(effects[gene_positions[source]])
            check(self_effect < float(parameters["self_logfc"]), f"Self knockdown ineligible: {source}")
            check(abs(self_effect - float(row.self_logFC)) <= args.tolerance, f"Self effect differs: {source}")
            expected_positive = set(raw_symbols[detected_pass & (np.abs(effects) > float(parameters["response_logfc"]))])
            observed_positive = recorded_positive[source]
            check(set(observed_positive) == expected_positive, f"Positive target membership differs for sampled source: {source}")
            positives = sorted(expected_positive)
            nonpositives = sorted(set(raw_symbols[detected_pass]) - expected_positive)
            sampled_targets = []
            for candidates, label in ((positives, True), (nonpositives, False)):
                count = min(10, len(candidates))
                sampled_targets.extend((target, label) for target in rng.choice(candidates, size=count, replace=False).tolist())
            for target, label in sampled_targets:
                expected = float(effects[gene_positions[target]])
                observed = observed_positive.get(target)
                if label:
                    check(math.isfinite(observed) and abs(expected - observed) <= args.tolerance, f"Positive effect mismatch: {source}/{target}")
                else:
                    check(abs(expected) <= float(parameters["response_logfc"]), f"Nonpositive target exceeds strict threshold: {source}/{target}")
                effect_checks.append({"source": source, "target": target, "positive": label,
                                      "raw_recomputed_effect": expected, "recorded_positive_effect": observed,
                                      "absolute_error": abs(expected - observed) if observed is not None else None})
            source_checks.append({"source": source, "n_KD_cells": len(kd), "n_NT_cells": len(nt),
                                  "self_logFC_recomputed": self_effect, "self_logFC_recorded": float(row.self_logFC),
                                  "all_positive_target_membership_matches": True, "n_positive_targets": len(expected_positive),
                                  "n_nonpositive_targets": len(nonpositives), "max_library_error": kd_stats["max_library_error"],
                                  "max_feature_error": kd_stats["max_feature_error"]})
        check({name: sha256(prepared / name) for name in relevant} == hashes, "Prepared inputs changed during audit")
        return {
            "status": "pass", "scope": "independent bounded technical spot-check; not biological validation or exact-author-input proof",
            "seed": args.seed, "tolerance": args.tolerance, "python": platform.python_version(),
            "audit_code_sha256": sha256(Path(__file__)), "prepare_manifest_sha256": sha256(manifest_path),
            "h5ad_sha256": manifest["input_h5ad"]["sha256"], "annotation_sha256": annotation_hash,
            "prepared_files_sha256": hashes, "n_NT_cells": len(nt), "n_expression_genes": len(expression_genes),
            "n_full_isSIG_hubs": len(hubs), "n_metacells": len(expression_mc), "QC_thresholds_recomputed": qc_thresholds,
            "all_membership_exactly_QCed_pure_NT": True, "all_hubs_match_pinned_isSIG_annotation": True,
            "all_expression_genes_match_nonzero_NT_and_detection_filter": True,
            "raw_prefilter_library_denominator_verified": True, "peak_sparse_count_chunk_cells": args.chunk_cells,
            "n_cells_with_raw_count_reads": len(nt) + sum(source["n_KD_cells"] for source in source_checks),
            "NT_max_library_error": nt_stats["max_library_error"], "NT_max_feature_error": nt_stats["max_feature_error"],
            "metacell_expression_checks": expression_checks, "source_eligibility_checks": source_checks,
            "sampled_response_effect_checks": effect_checks,
            "nonpositive_meaning": "Absent from thresholded response reference; not a proven biologically negative edge",
            "untested": ["Exact original upstream author preparation", "Correctness of every raw-cell QC/detection count",
                         "DE effect vectors for unsampled KD sources", "Biological/direct-edge correctness", "Native network inference"]
        }
    finally:
        data.file.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h5ad", required=True)
    parser.add_argument("--prepared-dir", required=True)
    parser.add_argument("--resources-dir", required=True)
    parser.add_argument("--output", required=True, type=Path, help="Fresh report JSON outside prepared directory")
    parser.add_argument("--rscript", help="Rscript executable for read-only annotation load")
    parser.add_argument("--wsl-r-env", help="Existing isolated WSL micromamba environment (Windows path)")
    parser.add_argument("--wsl-micromamba", help="Micromamba executable (default: sibling of --wsl-r-env)")
    parser.add_argument("--seed", type=int, default=271828)
    parser.add_argument("--chunk-cells", type=int, default=256)
    parser.add_argument("--tolerance", type=float, default=1e-8)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(Path(args.prepared_dir).resolve()):
        raise ValueError("Audit report must be fresh and outside immutable prepared inputs")
    report = audit(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"status": report["status"], "report": str(output), "n_NT_cells": report["n_NT_cells"],
                      "n_hubs": report["n_full_isSIG_hubs"], "sources": [record["source"] for record in report["source_eligibility_checks"]]}, indent=2))


if __name__ == "__main__":
    main()
