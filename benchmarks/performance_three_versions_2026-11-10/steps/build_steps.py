#!/usr/bin/env python3
"""Rebuild the LUAD step comparison from retained measurements, without inference."""
from __future__ import annotations
import argparse
from bisect import bisect_right
from collections import defaultdict
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DEFAULT_RAW = "E:/GitHub/local_runs/sjaracne_performance_20261110/three_versions"
CASES = [
    ("LUAD517_commit_4cd8eae", "4cd8eae", "commit_4cd8eae"),
    ("LUAD517_v0_3_0", "v0.3.0", "v0.3.0"),
    ("LUAD517_v0_4_0", "v0.4.0", "v0.4.0"),
]
COLORS = ["#687b8e", "#e2923b", "#268c89"]
TRACKED = {"native_resample", "finalization", "native_consensus_dpi", "input_preparation"}

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def local_path(value):
    text = str(value)
    if text.startswith("/mnt/") and len(text) > 7:
        return Path(text[5].upper() + ":/" + text[7:])
    return Path(text)

def basename(value):
    return str(value).replace("\\", "/").rsplit("/", 1)[-1]

def classify(argv, modern):
    if not argv:
        return "unclassified"
    executable = basename(argv[0])
    if executable == "sjaracne.exe":
        return "native_consensus_dpi" if "--consensus-inputs" in argv else "native_resample"
    if executable == "create_consensus_network.py":
        return "finalization"
    if executable == "QC_input.py":
        return "input_preparation"
    python = executable.startswith("python")
    if python:
        if any(basename(x) == "create_consensus_network.py" for x in argv[1:]):
            return "finalization"
        if "-m" in argv:
            module_at = argv.index("-m") + 1
            module = argv[module_at] if module_at < len(argv) else ""
            if module == "SJARACNe.bin.create_consensus_network":
                return "finalization"
            if module == "SJARACNe.bin.wdl_workflow":
                action = argv[module_at + 1] if module_at + 1 < len(argv) else ""
                if action == "consensus":
                    return "finalization"
                if action == "prepare":
                    return "input_preparation"
            if module == "SJARACNe.bin.QC_input":
                return "input_preparation"
        if any(basename(x) == "QC_input.py" for x in argv[1:]):
            return "input_preparation"
    return "unclassified"

def option(argv, flag):
    at = argv.index(flag)
    if at + 1 == len(argv):
        raise ValueError("Missing value after " + flag)
    return argv[at + 1]

def group_events(events, modern):
    groups = defaultdict(list)
    for item in events:
        argv = item.get("argv") or []
        if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
            raise ValueError("Malformed recorded argument list")
        if not argv:
            continue
        phase = classify(argv, modern)
        if phase not in TRACKED:
            continue
        groups[(int(item["pid"]), tuple(argv))].append(item)
    result = []
    for (pid, argv), fragments in groups.items():
        phases = {classify(list(argv), modern) for _ in fragments}
        if len(phases) != 1:
            raise ValueError("Process command has inconsistent classifications")
        phase = phases.pop()
        result.append({
            "pid": pid, "argv": list(argv), "phase": phase,
            "fragments": len(fragments),
            "first": min(x["first_observed_seconds"] for x in fragments),
            "last": max(x["last_observed_seconds"] for x in fragments),
            "peak_single_pss": max(x.get("peak_sampled_pss_bytes", 0) or 0 for x in fragments),
            "peak_single_rss": max(x.get("peak_sampled_rss_bytes", 0) or 0 for x in fragments),
            "create_time_min": min(x["create_time_epoch_seconds"] for x in fragments),
            "create_time_max": max(x["create_time_epoch_seconds"] for x in fragments),
        })
    return result

def seed_calls(processes):
    native = [p for p in processes if p["phase"] == "native_resample"]
    seeds = [int(option(p["argv"], "-S")) for p in native]
    if len(native) != 100 or sorted(seeds) != list(range(1, 101)):
        raise ValueError("Expected exactly one observed native call for every seed 1-100")
    return native

def merge_intervals(intervals):
    result = []
    for first, last in sorted(intervals):
        if not math.isfinite(first) or not math.isfinite(last) or last < first:
            raise ValueError("Invalid observation interval")
        if result and first <= result[-1][1]:
            result[-1][1] = max(result[-1][1], last)
        else:
            result.append([first, last])
    return result

def read_samples(path):
    result = []
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            result.append({
                "time": float(row["elapsed_seconds"]),
                "pss": int(row["total_pss_bytes"]) if row["total_pss_bytes"] else None,
                "rss": int(row["total_rss_bytes"]) if row["total_rss_bytes"] else None,
                "complete": row["pss_complete"] == "1",
            })
    if not result:
        raise ValueError("No memory samples")
    return result

def window_memory(samples, intervals):
    intervals = merge_intervals(intervals)
    starts = [x[0] for x in intervals]
    selected = []
    for sample in samples:
        i = bisect_right(starts, sample["time"]) - 1
        if i >= 0 and sample["time"] <= intervals[i][1]:
            selected.append(sample)
    complete = [s for s in selected if s["complete"] and s["pss"] is not None]
    return {
        "samples": len(selected), "complete_pss_samples": len(complete),
        "incomplete_pss_samples": len(selected) - len(complete),
        "peak_tree_pss_bytes": max((s["pss"] for s in complete), default=None),
        "peak_tree_rss_bytes": max((s["rss"] for s in selected if s["rss"] is not None), default=None),
    }

def extract_timers(text, expected_mi, expected_dpi):
    mi = [int(x) for x in re.findall(r"Gene:\s*1929\s+Time:\s*(\d+)", text)]
    dpi = [int(x) for x in re.findall(r"DPI running time is:\s*(\d+)", text)]
    if len(mi) != expected_mi or len(dpi) != expected_dpi:
        raise ValueError(f"Expected MI/DPI counts {expected_mi}/{expected_dpi}, found {len(mi)}/{len(dpi)}")
    return mi, dpi

def write_tsv(path, rows):
    fields = list(rows[0]) if rows else []
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

def fingerprint(path):
    path = Path(path)
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

def self_test():
    assert classify(["python3", "-m", "SJARACNe.bin.create_consensus_network", "-a", "x"], False) == "finalization"
    assert classify(["python", "/x/create_consensus_network.py"], False) == "finalization"
    assert classify(["python3", "-m", "SJARACNe.bin.wdl_workflow", "consensus"], True) == "finalization"
    assert classify(["python", "-B", "/src/create_consensus_network.py", "-a", "x"], False) == "finalization"
    assert classify(["python", "-B", "/src/QC_input.py", "-e", "x"], False) == "input_preparation"
    assert classify(["create_consensus_network.py", "-a", "x"], False) == "finalization"
    assert classify([], False) == "unclassified"
    assert merge_intervals([(0, 2), (1, 3), (4, 5)]) == [[0, 3], [4, 5]]
    memory = window_memory([{"time": 0, "pss": 10, "rss": 15, "complete": True},
                            {"time": 1, "pss": 30, "rss": 35, "complete": False},
                            {"time": 2, "pss": 20, "rss": 25, "complete": True}], [(0, 2)])
    assert memory["peak_tree_pss_bytes"] == 20 and memory["incomplete_pss_samples"] == 1
    try:
        extract_timers("Gene: 1929 Time: 3", 100, 100)
    except ValueError:
        pass
    else:
        raise AssertionError("Incomplete logs were accepted")
    try:
        seed_calls([])
    except ValueError:
        pass
    else:
        raise AssertionError("Missing seeds were accepted")
    # Clock-derived create times can drift while the same command/PID persists.
    base = {"pid": 7, "argv": ["sjaracne.exe", "-S", "1"], "first_observed_seconds": 0,
            "last_observed_seconds": 1, "create_time_epoch_seconds": 100}
    other = {**base, "first_observed_seconds": 1.5, "last_observed_seconds": 2,
             "create_time_epoch_seconds": 102}
    groups = group_events([base, other, {**base, "argv": []}], False)
    assert len(groups) == 1 and groups[0]["last"] == 2
    print("Focused evidence parsing and memory-window checks passed")

def save_figure(fig, folder, name):
    folder.mkdir(exist_ok=True)
    for extension in ["png", "pdf", "svg"]:
        fig.savefig(folder / (name + "." + extension), dpi=180, bbox_inches="tight")
    plt.close(fig)

def plots(output, rows, timers):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    names = ["4cd8eae*", "v0.3.0", "v0.4.0"]
    figure, axes = plt.subplots(1, 2, figsize=(10.8, 4.5))
    for axis, phase, title in zip(axes, ["native_resample", "finalization"],
                                  ["100 bootstraps, four workers", "Final network construction"]):
        selected = [next(r for r in rows if r["version"] == label and r["step"] == phase) for _, label, _ in CASES]
        values = [r["observed_union_seconds"] / 60 for r in selected]
        bars = axis.bar(names, values, color=COLORS)
        bars[0].set_hatch("//")
        axis.set_title(title)
        axis.set_ylabel("Approximate step time (minutes)")
        if phase == "native_resample":
            axis.set_yscale("log")
            axis.set_ylim(min(values) * .65, max(values) * 2)
        else:
            axis.set_ylim(0, max(values) * 1.25)
        for bar, value in zip(bars, values):
            axis.annotate(f"{value:,.1f}", (bar.get_x() + bar.get_width()/2, value),
                          xytext=(0, 5), textcoords="offset points", ha="center")
    figure.suptitle("LUAD517: time by step")
    figure.text(.5, -.015, "Older bootstraps include DPI; v0.4.0 applies DPI after consensus. Step times are approximate. *Concurrent load.", ha="center", fontsize=9)
    figure.tight_layout(rect=(0, .02, 1, .94))
    save_figure(figure, output / "figures", "step_durations")

    figure, axis = plt.subplots(figsize=(8.8, 4.8))
    positions = np.arange(2)
    width = .24
    for j, (_, label, _) in enumerate(CASES):
        values = [next(r for r in rows if r["version"] == label and r["step"] == phase)["peak_tree_pss_bytes"] / 1024**3 for phase in ["native_resample", "finalization"]]
        bars = axis.bar(positions + (j-1)*width, values, width, label=names[j], color=COLORS[j], hatch="//" if j == 0 else None)
        for bar, value in zip(bars, values):
            axis.annotate(f"{value:.2f}", (bar.get_x()+bar.get_width()/2, value), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9)
    axis.set_xticks(positions, ["100 bootstraps", "Final network construction"])
    axis.set_ylabel("Peak memory (GiB)")
    axis.set_title("LUAD517: peak memory by step")
    axis.set_ylim(0, max(r["peak_tree_pss_bytes"] or 0 for r in rows) / 1024**3 * 1.23)
    axis.legend(frameon=False)
    figure.text(.5, -.01, "Memory includes the workflow and its workers. *Concurrent load.", ha="center", fontsize=9)
    figure.tight_layout()
    save_figure(figure, output / "figures", "step_peak_pss")

    figure, axes = plt.subplots(1, 2, figsize=(10.8, 4.8))
    for axis, timer, title in zip(axes, ["MI", "DPI"], ["MI time per bootstrap", "DPI time"]):
        for j, (_, label, _) in enumerate(CASES):
            values = [x["seconds"] for x in timers if x["version"] == label and x["timer"] == timer]
            if len(values) == 1:
                axis.scatter([j + 1], values, marker="D", color=COLORS[j], s=55, zorder=4)
            else:
                box = axis.boxplot([values], positions=[j + 1], widths=.5, patch_artist=True,
                                   medianprops={"color": "#18242b", "linewidth": 1.5})
                box["boxes"][0].set_facecolor(COLORS[j])
            axis.text(j + 1, 1.015, f"n={len(values)}", transform=axis.get_xaxis_transform(), ha="center", fontsize=9)
        axis.set_xticks([1, 2, 3], names)
        axis.set_title(title, pad=26)
        axis.set_ylabel("Elapsed calculation time (seconds)")
        axis.set_xlim(.4, 3.6)
        if timer == "MI":
            axis.set_yscale("log")
    figure.suptitle("LUAD517: MI and DPI calculation times", y=1.02)
    figure.text(.5, -.015, "DPI: 100 bootstrap passes in older versions; one consensus pass in v0.4.0. *Concurrent load.", ha="center", fontsize=9)
    figure.tight_layout()
    save_figure(figure, output / "figures", "native_internal_timers")

def whole_workflow_plots(output, overall):
    """Plot GNU wall time and sampled workflow-tree PSS from the overall table."""
    names = [row["version"] + ("*" if row["concurrent"] else "") for row in overall]
    definitions = [
        ("whole_cli_wall_time", [row["seconds"] / 3600 for row in overall],
         "LUAD517: total wall time", "Total wall time (hours)", "h"),
        ("whole_workflow_peak_memory", [row["pss"] / 1024**3 for row in overall],
         "LUAD517: peak memory", "Peak memory (GiB)", "GiB"),
    ]
    for name, values, title, ylabel, unit in definitions:
        figure, axis = plt.subplots(figsize=(8.8, 4.8))
        bars = axis.bar(names, values, color=COLORS, width=.64)
        for bar, row, value in zip(bars, overall, values):
            if row["concurrent"]:
                bar.set_hatch("//")
            axis.annotate(f"{value:.2f} {unit}",
                          (bar.get_x() + bar.get_width()/2, value),
                          xytext=(0, 6), textcoords="offset points", ha="center")
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.set_ylim(0, max(values) * 1.2)
        axis.set_axisbelow(True)
        axis.grid(axis="y", alpha=.18)
        figure.text(.5, .015,
                    "100 MI resamples; up to four concurrent workers on logical CPUs 0-3.\n"
                    "*4cd8eae ran partly alongside MIBC372; scientific defaults differ.",
                    ha="center", va="bottom", fontsize=9)
        figure.tight_layout(rect=(0, .13, 1, 1))
        save_figure(figure, output / "figures", name)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", default=DEFAULT_RAW)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    self_test()
    if args.self_test:
        return
    raw = Path(args.raw_root)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    rows, timers, observed, overall, sources = [], [], [], [], []
    concurrency = read_json(raw / "concurrent_workloads.json")
    sources.append(raw / "concurrent_workloads.json")
    affected = {e["affected_case_id"] for e in concurrency["events"]}
    for case, label, source_key in CASES:
        modern = label == "v0.4.0"
        attempt = raw / "results/cases" / case / "attempt_001"
        result_path, events_path, samples_path = [attempt / n for n in ["result.json", "process_events.json", "timeseries.tsv"]]
        result = read_json(result_path)
        if result["status"] != "complete" or result["exit_code"] != 0 or not result["validation"]["passed"]:
            raise ValueError("Case is not validated: " + case)
        event_doc = read_json(events_path)
        processes = group_events(event_doc["events"], modern)
        native = seed_calls(processes)
        samples = read_samples(samples_path)
        interval = float(event_doc["sample_interval_seconds"])
        sources.extend([result_path, events_path, samples_path])
        overall.append({"version": label, "seconds": result["gnu_time"]["elapsed_seconds"],
                        "pss": result["memory"]["peak_descendant_pss_bytes"], "concurrent": case in affected})
        for p in processes:
            observed.append({"version": label, "case_id": case, "phase": p["phase"], "pid": p["pid"],
                             "argument_json": json.dumps(p["argv"]), "observed_fragments": p["fragments"],
                             "first_sampler_seconds": p["first"], "last_sampler_seconds": p["last"],
                             "recorded_create_time_min": p["create_time_min"], "recorded_create_time_max": p["create_time_max"],
                             "peak_single_pss_bytes": p["peak_single_pss"], "peak_single_rss_bytes": p["peak_single_rss"]})
        for phase in ["input_preparation", "native_resample", "finalization", "native_consensus_dpi"]:
            selected = [p for p in processes if p["phase"] == phase]
            if not selected:
                if phase in {"native_resample", "finalization"}:
                    raise ValueError("Required stage not observed: " + case + "/" + phase)
                continue
            intervals = merge_intervals([(p["first"], p["last"] + interval) for p in selected])
            memory = window_memory(samples, intervals)
            rows.append({"version": label, "case_id": case, "step": phase,
                         "native_operation": ("MI only" if modern else "MI + DPI") if phase == "native_resample" else
                            ("consensus + DPI + export + enhancement + checks" if modern else "Python consensus + enhancement") if phase == "finalization" else phase,
                         "concurrent_load": case in affected, "unique_pid_argument_calls": len(selected),
                         "observed_first_sampler_seconds": min(x[0] for x in intervals),
                         "observed_last_sampler_seconds": max(x[1] for x in intervals),
                         "observed_span_seconds": max(x[1] for x in intervals) - min(x[0] for x in intervals),
                         "observed_union_seconds": sum(b-a for a,b in intervals),
                         **memory})
        if modern:
            manifest = read_json(raw / "outputs" / case / "sjaracne_run.json")
            sources.append(raw / "outputs" / case / "sjaracne_run.json")
            engine = local_path(manifest["engine_output_dir"])
            run = local_path(manifest["engine_outputs_json"]).parent
            for seed in range(1, 101):
                p = run / "calls" / ("resample_and_estimate_mi-" + str(seed-1)) / "attempts/0/work/native.stdout.txt"
                mi, dpi = extract_timers(p.read_text(), 1, 0)
                sources.append(p)
                timers.append({"version": label, "timer": "MI", "seed": seed, "ordinal": seed,
                               "seconds": mi[0], "graph": "individual resample", "source": str(p), "concurrent_load": case in affected})
            p = run / "calls/build_consensus_network/attempts/0/work/consensus.native.stdout.txt"
            mi, dpi = extract_timers(p.read_text(), 0, 1)
            sources.append(p)
            timers.append({"version": label, "timer": "DPI", "seed": "", "ordinal": 1,
                           "seconds": dpi[0], "graph": "K20 mean-MI consensus graph", "source": str(p), "concurrent_load": case in affected})
        else:
            p = attempt / "stderr.log"
            sources.append(p)
            mi, dpi = extract_timers(p.read_text(errors="replace"), 100, 100)
            for timer_name, values in [("MI", mi), ("DPI", dpi)]:
                for i, value in enumerate(values, 1):
                    timers.append({"version": label, "timer": timer_name, "seed": "", "ordinal": i,
                                   "seconds": value, "graph": "individual resample; merged log order, seed unavailable",
                                   "source": str(p), "concurrent_load": case in affected})
        # Record the actual timer definition rather than inferring CPU time.
        sources.append(raw / "sources_lf" / source_key / "SJARACNe/src/matrix.cpp")
    assert len(timers) == 501
    write_tsv(output / "steps.tsv", rows)
    write_tsv(output / "native_timers.tsv", timers)
    write_tsv(output / "observed_processes.tsv", observed)
    plots(output, rows, timers)
    whole_workflow_plots(output, overall)
    write_tsv(output / "whole_workflows.tsv", [
        {"version": row["version"], "wall_seconds": row["seconds"],
         "wall_hours": row["seconds"] / 3600,
         "peak_tree_pss_bytes": row["pss"], "peak_tree_pss_gib": row["pss"] / 1024**3,
         "concurrent_load": row["concurrent"], "wall_time_source": "GNU time"}
        for row in overall
    ])
    def markdown_table(headers, values):
        return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"] + ["| " + " | ".join(map(str, row)) + " |" for row in values])
    overall_table = markdown_table(["Version", "Total wall time", "Peak memory"],
        [[x["version"] + ("*" if x["concurrent"] else ""), f"{int(x['seconds'])//3600}:{(int(x['seconds'])%3600)//60:02d}:{int(x['seconds'])%60:02d}", f"{x['pss']/1024**3:.3f} GiB"] for x in overall])
    step_table = markdown_table(["Version", "Observed step", "Approx. active minutes", "Peak memory in step window"],
        [[r["version"] + ("*" if r["concurrent_load"] else ""), r["native_operation"], f"{r['observed_union_seconds']/60:,.2f}", f"{r['peak_tree_pss_bytes']/1024**3:.3f} GiB"] for r in rows if r["step"] in ["native_resample", "finalization"]])
    timer_values = []
    for _, label, _ in CASES:
        for timer in ["MI", "DPI"]:
            values = [x["seconds"] for x in timers if x["version"] == label and x["timer"] == timer]
            timer_values.append([label + ("*" if label == "4cd8eae" else ""), timer, len(values), f"{statistics.median(values):g}", f"{min(values)}-{max(values)}"])
    timer_table = markdown_table(["Version", "Native timer", "Count", "Median seconds", "Range seconds"], timer_values)
    missing = sum(r["incomplete_pss_samples"] for r in rows if r["step"] in ["native_resample", "finalization"])
    readme = f"""# LUAD517 step comparison: three SJARACNe versions

All numbers below reuse the completed four-worker LUAD517 TF runs: 29,841 genes, 517 profiles and 1,929 requested hubs. No inference was rerun. This analysis supplements the [overall report](../README.md).

## Whole workflows

{overall_table}

![Total wall time](figures/whole_cli_wall_time.png)

![Peak memory](figures/whole_workflow_peak_memory.png)

The bar plots use the values in the table; both axes start at zero. Exact plotted values are in [whole_workflows.tsv](whole_workflows.tsv).

`*` The original-commit workflow ran partly alongside MIBC372 on disjoint CPU allocations. Cache, memory bandwidth, package power and SSD remained shared. Its observations are retained without claiming an isolated cross-version speedup. Scientific defaults differ between releases, including sampling, MI calibration and consensus/DPI order.

## Step comparison

The plots compare **100 bootstraps** and **final network construction**. In `4cd8eae` and v0.3.0, each bootstrap computes MI and applies DPI; consensus and annotation follow. In v0.4.0, bootstraps compute MI only. The final step keeps edges supported by at least 20 bootstraps, averages MI over the supporting bootstraps, applies DPI and adds annotations.

Step times are approximate and may overlap. The DPI plot contains 100 bootstrap-level measurements for each older version and one consensus-level measurement for v0.4.0.

![Time by step](figures/step_durations.png)

![Peak memory by step](figures/step_peak_pss.png)

![MI and DPI calculation times](figures/native_internal_timers.png)

## Data and reproduction

[Overall values](whole_workflows.tsv), [Step measurements](steps.tsv), [MI/DPI timings](native_timers.tsv), [Measurement provenance](provenance.json), [Analysis script](build_steps.py)

Plots are available as PNG, PDF and SVG in [figures/](figures/).

```powershell
python build_steps.py --raw-root E:/GitHub/local_runs/sjaracne_performance_20261110/three_versions
```

"""
    (output / "README.md").write_text(readme.rstrip() + "\n", encoding="utf-8")
    unique_sources = sorted(set(sources), key=str)
    provenance = {
        "schema": "sjaracne-luad-step-comparison-v1",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "builder": fingerprint(Path(__file__)),
        "inputs": [fingerprint(p) for p in unique_sources],
        "versions": [x[1] for x in CASES], "native_calls_required_per_version": 100,
        "native_timer_observations": len(timers), "step_rows": len(rows),
        "process_grouping": "PID plus exact argument list; create-time fragments retained in process TSV",
        "step_time_definition": "Union of first-to-last observation intervals, with one sample interval appended; unchanged sampler elapsed clock",
        "step_wall_clock_rescaled": False,
        "whole_workflow_plot_definitions": {
            "wall_time": "GNU-time elapsed seconds divided by 3600; linear zero-baseline hours",
            "peak_memory": "Sampled peak_descendant_pss_bytes divided by 1024**3; linear zero-baseline GiB",
            "data_table": "whole_workflows.tsv", "raw_result_values_modified": False,
        },
        "memory_definition": "Maximum complete-sample whole-tree PSS inside merged step intervals; peaks are not summed",
        "native_timer_definition": "Rounded std::time/std::difftime elapsed seconds; logs do not identify seeds for interleaved older timers",
        "raw_graphs_read": False, "inference_rerun": False,
        "concurrent_case_ids": sorted(affected), "sampling_interval_seconds": .5,
    }
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": "complete", "steps": len(rows), "native_timers": len(timers),
                      "observed_process_groups": len(observed), "output": str(output)}))

if __name__ == "__main__":
    main()
