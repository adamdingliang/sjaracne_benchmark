#!/usr/bin/env python3
"""Run isolated lightweight Python tests; never launch dataset inference/downloads."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
# Engine-coupled/native compilation/R tests remain explicitly separate.
GROUPS = {
    "migration": ("scripts", ["test_verify_migration", "test_verify_engine_archive"]),
    "engine_performance": ("engine_performance/tests", ["test_rank_benchmark_generator"]),
    "dream5": ("benchmarks/dream5_network1", ["test_benchmark"]),
    "dream5_network3": ("benchmarks/dream5_network3", ["test_prepare", "test_run_benchmark", "test_metrics"]),
    "thp1": ("benchmarks/thp1_perturbseq", ["test_metrics", "test_prepare", "test_benchmark", "test_scanpy_notebook"]),
    "thp1_raw_mi": ("benchmarks/thp1_perturbseq/raw_mi", [
        "test_score", "test_run_pilot", "test_smoke", "test_report", "test_extend_pilot",
        "test_package_full100"]),
    "thp1_scoring": ("benchmarks/thp1_perturbseq/author_reconstruction", [
        "test_score_bootstrap_counts", "test_score_fixed_universe", "test_score_sampling_after",
        "test_score_three_populations", "test_plot_sampling_comparison", "test_plot_eligible_fig6a"]),
    "luad": ("benchmarks/tcga_luad_download", ["test_download_tcga_luad", "test_query_snapshot"]),
    "hub_dpi": ("benchmarks/brca100_hub_size_dpi_pilot", ["test_pilot"]),
    "kdpi": ("benchmarks/brca100_kdpi_witness_screen", ["test_screen"]),
    "threshold": ("benchmarks/brca100_pr67_threshold_sweep", [
        "test_analyze_sweep", "test_package_results", "test_run_netbid_qc", "test_run_sweep_extension"]),
    "recurrence": ("benchmarks/brca100_consensus_recurrence_sweep", [
        "test_exact_tail", "test_aggregate_recurrence", "test_generate_netbid_html"]),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", action="append", choices=GROUPS)
    parser.add_argument("--engine-repo", type=Path,
                        help="Optional external SJARACNe checkout for the existing BRCA100 fixture test")
    args = parser.parse_args()
    if args.engine_repo and not (args.engine_repo / "tests/inputs/BRCA100.exp").is_file():
        parser.error("--engine-repo must contain the original BRCA100 test inputs")
    failed = []
    for name in args.group or GROUPS:
        directory, modules = GROUPS[name]
        print(f"\n{name}: synthetic Python checks", flush=True)
        command = [sys.executable, str(ROOT / "scripts/test_worker.py"), *modules]
        if args.engine_repo:
            command += ["--engine-repo", str(args.engine_repo.resolve())]
        status = subprocess.run(command, cwd=ROOT / directory).returncode
        if status:
            failed.append(name)
    if failed:
        print("Failed groups: " + ", ".join(failed), file=sys.stderr)
    return int(bool(failed))


if __name__ == "__main__":
    sys.exit(main())
