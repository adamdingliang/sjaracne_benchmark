#!/usr/bin/env python3
"""Read-only scoring of saved post-DPI bootstraps; never launch inference.

TP/FP are operational perturbation-response labels within eligible sources.
Outputs must be fresh; the frozen reference, native runs and prior scorers stay
unchanged. Per-bootstrap counts are not consensus counts or independent edges.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import platform
import sys
import time

import numpy as np

import complete_baseline as completion
import run_legacy as legacy
import run_sampling_backport as sampling
import score_fixed_universe as fixed
import score_sampling_after as after


CODE = Path(__file__).resolve().parent
NUMERIC_HEADERS = {"MI threshold", "MI P-value", "DPI tolerance",
                   "Eligible observations", "Sampled observations"}
HEADERS = NUMERIC_HEADERS | {"Sampling method", "Sampling request"}
SUMMARY_KEYS = ("full_edges", "eligible_edges", "TP", "FP", "precision", "sensitivity", "specificity")
MATCHED = ("bootstrap_count", "seeds", "bootstrap_p", "consensus_p", "npar",
           "dpi_tolerance", "algorithm", "explicit_mi_override")


def pair_counts(pairs: set[int], universe: fixed.Universe) -> dict:
    tp = len(pairs & universe.positives)
    fp = len(pairs) - tp
    positives, negatives = len(universe.positives), universe.size - len(universe.positives)
    return {"eligible_edges": len(pairs), "TP": tp, "FP": fp,
            "FN": positives - tp, "TN": negatives - fp,
            "precision": tp / len(pairs) if pairs else None,
            "sensitivity": tp / positives, "specificity": 1 - fp / negatives}


def score_adjacency(path: Path, universe: fixed.Universe, hubs: set[str],
                    expected_header: dict) -> tuple[dict, set[int]]:
    """Validate all native rows, but label only the frozen eligible population."""
    if not {"MI threshold", "MI P-value", "DPI tolerance"} <= expected_header.keys():
        raise ValueError("Expected protocol must declare threshold, p-value and DPI")
    targets, eligible = set(universe.targets), set(universe.sources)
    seen_sources, pairs, eligible_with_edges = set(), set(), set()
    header, full_edges = {}, 0
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            line = line.rstrip("\r\n")
            if not line:
                continue
            if line.startswith(">"):
                if seen_sources:
                    raise ValueError(f"Header after data at {path}:{number}")
                text = line[1:].strip()
                for name in sorted(HEADERS, key=len, reverse=True):
                    if text.startswith(name) and (len(text) == len(name) or text[len(name)].isspace()):
                        if name in header:
                            raise ValueError(f"Duplicate header {name}")
                        value = text[len(name):].strip()
                        header[name] = float(value) if name in NUMERIC_HEADERS else value
                        break
                continue
            fields = line.split("\t")
            source = fields[0]
            if source not in hubs or source not in targets or source in seen_sources:
                raise ValueError(f"Unknown/duplicate source at {path}:{number}")
            if len(fields) % 2 != 1:
                raise ValueError(f"Malformed adjacency width at {path}:{number}")
            if "MI threshold" not in header:
                raise ValueError("Missing MI threshold before data")
            seen_sources.add(source)
            seen_targets = set()
            for index in range(1, len(fields), 2):
                target, mi = fields[index], float(fields[index + 1])
                if target not in targets or target == source or target in seen_targets:
                    raise ValueError(f"Unknown/self/duplicate target at {path}:{number}")
                if not math.isfinite(mi) or mi < 0 or mi < header["MI threshold"] - 1e-6:
                    raise ValueError(f"Invalid/below-cutoff MI at {path}:{number}")
                seen_targets.add(target)
                full_edges += 1
                if source in eligible:
                    pairs.add(universe.key(source, target))
                    eligible_with_edges.add(source)
    if set(header) != set(expected_header):
        raise ValueError(f"Missing/unexpected protocol header: {path}")
    for name, expected in expected_header.items():
        value = header[name]
        if name in NUMERIC_HEADERS:
            if not math.isfinite(value) or not math.isclose(value, expected, rel_tol=1e-5, abs_tol=1e-12):
                raise ValueError(f"Header differs from frozen protocol: {name}")
        elif value != expected:
            raise ValueError(f"Header differs from frozen protocol: {name}")
    return {"full_edges": full_edges, "source_rows": len(seen_sources),
            "eligible_sources_with_edges": len(eligible_with_edges), "header": header,
            **pair_counts(pairs, universe)}, pairs


def summarize_runs(rows: list[dict]) -> dict:
    result = {}
    for key in SUMMARY_KEYS:
        values = [row[key] for row in rows if row[key] is not None]
        if not values:
            result[key] = {"n": 0, "mean": None, "median": None, "q1": None,
                           "q3": None, "min": None, "max": None}
            continue
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Nonfinite summary input")
        q1, median, q3 = np.quantile(values, [.25, .5, .75], method="linear")
        result[key] = {"n": len(values), "mean": float(np.mean(values)), "median": float(median),
                       "q1": float(q1), "q3": float(q3), "min": min(values), "max": max(values)}
    return result


def validate_run(manifest: Path, run: dict, prepared_dir: Path, arm: str,
                 baseline_manifest: Path | None = None) -> dict:
    if run.get("status") != "complete" or (manifest.parent / ".runner.lock").exists():
        raise ValueError("Require a completed, unlocked run")
    for job in run.get("bootstraps", {}).values():
        if job.get("returncode") != 0:
            raise ValueError("Failed bootstrap checkpoint")
    if arm == "before":
        args = argparse.Namespace(run_manifest=manifest, prepared_dir=prepared_dir)
        networks = completion.validate_native(args, run)
        if any(job.get("returncode") != 0 for job in run["consensus"].values()):
            raise ValueError("Failed baseline consensus checkpoint")
        return networks
    if arm != "after" or baseline_manifest is None:
        raise ValueError("Unknown arm or missing baseline binding")
    frozen = run["frozen"]
    if frozen.get("profile") != sampling.PROFILE:
        raise ValueError("Require sampling-only after profile")
    completion.check_record(frozen["baseline_binding"]["records"]["run_manifest"], baseline_manifest)
    native_args = after.native_arguments(manifest, frozen)
    reconstructed, _, _ = sampling.make_frozen(native_args)
    if reconstructed != frozen:
        raise ValueError("After frozen protocol differs from verified inputs")
    sampling.verify_frozen(frozen)
    return after.verify_checkpoints(manifest, run)


def protocol_header(frozen: dict, arm: str) -> dict:
    p = frozen["parameters"]
    header = {"MI threshold": p["affine_mi_cutoff"], "MI P-value": p["bootstrap_p"],
              "DPI tolerance": p["dpi_tolerance"]}
    if arm == "after":
        header.update({"Sampling method": "fixed-size without replacement", "Sampling request": "80%",
                       "Eligible observations": frozen["observations"], "Sampled observations": p["sampling_draws"]})
    return header


def collect_records(value, records: dict) -> None:
    """Collect hash-bound runtime/preparation artifacts recursively, deduplicated."""
    if isinstance(value, dict):
        if {"path", "sha256"} <= value.keys():
            path = str(completion.local_path(value["path"]))
            if path in records and records[path] != value["sha256"]:
                raise ValueError("Conflicting artifact bindings")
            records[path] = value["sha256"]
        else:
            for child in value.values():
                collect_records(child, records)
    elif isinstance(value, list):
        for child in value:
            collect_records(child, records)


def verify_records(records: dict) -> None:
    for value, sha in records.items():
        if fixed.digest(completion.local_path(value)) != sha:
            raise ValueError(f"Frozen artifact changed: {value}")


def score_consensus(path: Path, universe: fixed.Universe, hubs: set[str]) -> tuple[dict, set[int]]:
    # Keep the frozen existing parser as the validation/counting authority.
    groups, full_count, full_tp = fixed.read_network(path, universe, hubs)
    sources = set(universe.sources)
    pairs = {universe.key(row["source"], row["target"]) for row in fixed.rows(path)
             if row["source"] in sources}
    counts = pair_counts(pairs, universe)
    if counts["TP"] != sum(p for _, p, _ in groups) or counts["FP"] != sum(n for _, _, n in groups):
        raise ValueError("Consensus labels/counts disagree with frozen scorer")
    if full_tp != counts["TP"]:
        raise ValueError("Positive labels outside eligible population")
    return {"full_edges": full_count, **counts}, pairs


def recurrence_summary(counter: Counter, universe: fixed.Universe) -> list[dict]:
    histogram = {k: {"recurrence": k, "TP": 0, "FP": 0} for k in range(1, 101)}
    for pair, count in counter.items():
        if count not in histogram:
            raise ValueError("Invalid bootstrap recurrence")
        histogram[count]["TP" if pair in universe.positives else "FP"] += 1
    return list(histogram.values())


def write_table(path: Path, rows: list[dict], names: tuple[str, ...]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def report(metrics: dict) -> str:
    lines = ["# Saved THP-1 post-DPI bootstrap TP/FP audit", "",
             "Primary population: predictions from the same 272 eligible perturbed sources; full SIG inference used 6,951 hubs. No inference was rerun.", "",
             "## Per-bootstrap distribution (100 runs per arm)", "",
             "Each cell is median [Q1, Q3]. Precision is summarized per run, not calculated from median counts.", "",
             "| Metric | Before | After (80%) | Change in medians |", "| --- | ---: | ---: | ---: |"]
    for key in ("eligible_edges", "TP", "FP", "precision"):
        a, b = (metrics["arms"][arm]["distribution"][key] for arm in ("before", "after"))
        formatter = (lambda value: f"{value:.2%}") if key == "precision" else (lambda value: f"{value:,.1f}")
        cells = [f"{formatter(x['median'])} [{formatter(x['q1'])}, {formatter(x['q3'])}]" for x in (a, b)]
        delta = b["median"] - a["median"]
        change = f"{delta * 100:+.2f} percentage points" if key == "precision" else f"{delta / a['median']:+.2%}"
        lines.append(f"| {key} | {cells[0]} | {cells[1]} | {change} |")
    lines += ["", "These are separate post-DPI graphs. Median changes above are not the median of matched seed differences; the latter are saved separately. Matching seed numbers do not imply matching cells or RNG streams.", "",
              "## Union and existing consensus", "",
              "The union contains distinct eligible pairs appearing in at least one bootstrap. It is not a final network. Consensus rows contain distinct pairs surviving the original probability-based consensus, not a new K-edge rule.", "",
              "| Stage | Before TP | After TP | Before FP | After FP |", "| --- | ---: | ---: | ---: | ---: |"]
    for name in ("bootstrap_union", "consensus_pc1e-02", "consensus_pc1e-03"):
        a, b = (metrics["arms"][arm][name] for arm in ("before", "after"))
        lines.append(f"| {name} | {a['TP']:,} | {b['TP']:,} | {a['FP']:,} | {b['FP']:,} |")
    a, b = (metrics["arms"][arm]["distribution"] for arm in ("before", "after"))
    if b["TP"]["max"] < a["TP"]["min"]:
        lines += ["", "All 100 after runs have fewer TPs than every before run: the TP deficit is already present in the saved post-DPI bootstraps. Consensus is therefore not the sole origin of the deficit."]
    lines += ["", "## Boundaries", "",
              "- This compares operational sampling protocols: 121 replacement draws versus 97 distinct metacells; the affine MI cutoff rises from 0.1369870641 to 0.1559020640 at the same nominal bootstrap p=1e-7. RNG consumption also changes.",
              "- Existing files are post-DPI only. This audit cannot separate sampling, MI filtering and DPI contributions, or determine whether lowering the cutoff would rescue the lost TPs.",
              "- TP means a match to the unchanged reconstructed perturbation-response reference; FP means no positive label within the eligible tested population. These are not established direct-edge biological truth labels.",
              "- The 100 runs share data and are not independent biological replicates. Changes are descriptive; no significance claim is made.",
              "- Fixed reference: 4,887,840 non-self pairs, 1,177,495 response-positive labels, 3,710,345 operational negative labels. Per-run FN/TN and sensitivity/specificity use those frozen denominators.",
              "", "Per-run counts, matched seed differences and eligible-pair recurrence histograms are in the accompanying TSV files. Hashes of all native checkpoints, prepared inputs, helpers and outputs are recorded in manifest.json.", ""]
    return "\n".join(lines)


def execute(args) -> dict:
    root, out = args.result_root.resolve(), args.out.resolve()
    if out.exists():
        raise FileExistsError("Require a fresh output directory; no saved results are overwritten")
    prepared = root / "prepared"
    paths = {"before": root / "legacy" / "run_manifest.json",
             "after": root / "sampling_after_80pct_20261012" / "run_manifest.json"}
    runs = {arm: completion.read_json(path) for arm, path in paths.items()}
    networks = {arm: validate_run(paths[arm], runs[arm], prepared, arm, paths["before"])
                for arm in paths}
    a, b = (runs[arm]["frozen"] for arm in ("before", "after"))
    if any(a["parameters"][key] != b["parameters"][key] for key in MATCHED):
        raise ValueError("Matched native parameters differ")
    if any(a["inputs"][key] != b["inputs"][key] for key in ("expression", "hubs", "prepare_manifest")):
        raise ValueError("Matched prepared input records differ")
    prep = completion.read_json(prepared / "prepare_manifest.json")
    if prep.get("status") != "complete":
        raise ValueError("Incomplete frozen preparation")
    records = {}
    for run in runs.values():
        collect_records(run["frozen"], records)
        collect_records(run["bootstraps"], records)
        collect_records(run["consensus"], records)
    for path in paths.values():
        records[str(path)] = fixed.digest(path)
    for filename in ("gene_selection.tsv", "reference_eligible_sources.tsv", "reference_positive_edges.tsv",
                     "hubs.txt", "expression.exp"):
        path = prepared / filename
        sha = prep["outputs"][filename]["sha256"]
        if str(path) in records and records[str(path)] != sha:
            raise ValueError("Prepared input binding differs")
        records[str(path)] = sha
    for filename in (Path(__file__).name, "complete_baseline.py", "run_legacy.py", "run_sampling_backport.py",
                     "score_sampling_after.py", "score_fixed_universe.py"):
        records[str(CODE / filename)] = fixed.digest(CODE / filename)
    verify_records(records)
    universe = fixed.make_universe(prepared)
    hubs = set((prepared / "hubs.txt").read_text(encoding="utf-8").splitlines())
    if (len(universe.sources), len(universe.targets), universe.size, len(universe.positives), len(hubs)) != (272, 17971, 4887840, 1177495, 6951):
        raise ValueError("Universe differs from the frozen completed comparison")
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    state = {"status": "scoring", "started": started, "completed_bootstraps": 0}
    legacy.json_write(out / "status.json", state)
    metrics = {"schema": 1, "status": "complete", "primary_population": "eligible_emitted",
               "scope": "existing individual post-DPI bootstrap networks; no inference rerun",
               "universe": {"n_sources": len(universe.sources), "n_targets": len(universe.targets),
                            "candidate_pairs": universe.size, "reference_positive_pairs": len(universe.positives),
                            "sources": list(universe.sources), "targets": list(universe.targets)}, "arms": {}}
    all_rows, counters = [], {}
    try:
        for arm, run in runs.items():
            counter, rows = Counter(), []
            for seed in range(1, 101):
                job = run["bootstraps"][str(seed)]
                path = completion.local_path(job["artifacts"]["adjacency"]["path"])
                counts, pairs = score_adjacency(path, universe, hubs, protocol_header(run["frozen"], arm))
                if (counts["full_edges"], counts["source_rows"], counts["header"]) != (job["validation"]["edges"], job["validation"]["source_rows"], job["validation"]["header"]):
                    raise ValueError("Parsed adjacency differs from native checkpoint validation")
                rows.append({"arm": arm, "seed": seed, **counts})
                counter.update(pairs)
                state["completed_bootstraps"] += 1
                if seed % 10 == 0:
                    print(f"{arm}: scored {seed}/100", file=sys.stderr, flush=True)
                    legacy.json_write(out / "status.json", state, replace=True)
            union = pair_counts(set(counter), universe)
            result = {"protocol": run["frozen"]["parameters"], "distribution": summarize_runs(rows),
                      "rows": rows, "bootstrap_union": union,
                      "edge_occurrences": {key: sum(row[key] for row in rows) for key in ("TP", "FP", "eligible_edges")},
                      "recurrence_histogram": recurrence_summary(counter, universe)}
            for p, path in networks[arm].items():
                counts, pairs = score_consensus(path, universe, hubs)
                if not pairs <= counter.keys():
                    raise ValueError("Consensus contains pair absent from all bootstraps")
                counts["fraction_bootstrap_union_TP_retained"] = counts["TP"] / union["TP"]
                counts["fraction_bootstrap_union_FP_retained"] = counts["FP"] / union["FP"]
                result[legacy.consensus_name(p)] = counts
            metrics["arms"][arm] = result
            counters[arm] = counter
            all_rows.extend(rows)
        paired = [{"seed": seed, **{key: metrics["arms"]["after"]["rows"][seed - 1][key] - metrics["arms"]["before"]["rows"][seed - 1][key]
                   for key in SUMMARY_KEYS}} for seed in range(1, 101)]
        metrics["matched_seed_difference_distribution"] = summarize_runs(paired)
        before_pairs, after_pairs = (set(counters[arm]) for arm in ("before", "after"))
        metrics["union_overlap"] = {name: pair_counts(pairs, universe) for name, pairs in (
            ("shared", before_pairs & after_pairs), ("before_only", before_pairs - after_pairs),
            ("after_only", after_pairs - before_pairs))}
        verify_records(records)
        legacy.json_write(out / "metrics.json", metrics)
        write_table(out / "per_bootstrap_counts.tsv", all_rows,
                    ("arm", "seed", "full_edges", "source_rows", "eligible_sources_with_edges", "eligible_edges",
                     "TP", "FP", "FN", "TN", "precision", "sensitivity", "specificity"))
        write_table(out / "paired_seed_differences.tsv", paired, ("seed", *SUMMARY_KEYS))
        histogram = [{"arm": arm, **row} for arm in runs for row in metrics["arms"][arm]["recurrence_histogram"]]
        write_table(out / "eligible_recurrence_counts.tsv", histogram, ("arm", "recurrence", "TP", "FP"))
        with (out / "REPORT.md").open("x", encoding="utf-8") as stream:
            stream.write(report(metrics))
        manifest = {"status": "complete", "primary_population": "eligible_emitted", "input_sha256": records,
                    "output_sha256": {path.name: fixed.digest(path) for path in out.iterdir() if path.name != "status.json"},
                    "python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
                    "elapsed_seconds": time.time() - started, "quantiles": "numpy linear, per bootstrap",
                    "inference_rerun": False}
        legacy.json_write(out / "manifest.json", manifest)
        state.update(status="complete", elapsed_seconds=time.time() - started)
        legacy.json_write(out / "status.json", state, replace=True)
        return metrics
    except BaseException as error:
        state.update(status="failed", error=str(error))
        legacy.json_write(out / "status.json", state, replace=True)
        raise


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--result-root", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


if __name__ == "__main__":
    result = execute(parser().parse_args())
    print(json.dumps({"status": result["status"], "primary_population": result["primary_population"]}))
