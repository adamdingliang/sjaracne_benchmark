#!/usr/bin/env python3
"""Package already-completed broad-grid results; never fit or open raw draws.

This presentation-only module is deliberately outside the frozen statistical
pipeline. It requires a completed summary/status before reading score tables.
It cannot select candidates, change cutoffs, or retry a failed primary.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil


HERE = Path(__file__).resolve().parent
CORE_P = (0.05, 0.01, 0.001, 0.0005)
COARSE_P = CORE_P + (0.0001, 0.00001, 0.000001, 0.0000001)
METHODS = ("quadratic", "pchip", "exact_m_empirical", "legacy_affine")
LABELS = {
    "quadratic": "Quadratic",
    "pchip": "PCHIP",
    "exact_m_empirical": "Exact-m empirical diagnostic",
    "legacy_affine": "Untouched legacy-affine comparator",
}
LOCKS = (
    "request", "access_initial", "initial_models", "selection", "access_selected",
    "refit_models", "primary", "access_final", "summary", "training_index",
    "development_index", "refit_index", "validation_index", "test_fit_index", "recovery_request",
)
REQUIRED_LOCKS = ("request", "selection", "refit_models", "primary", "access_final", "summary")


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def read_locked(path):
    path = Path(path)
    expected = path.with_suffix(".sha256").read_text(encoding="ascii").strip()
    if expected != digest(path):
        raise ValueError("compact record hash mismatch: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _float(value):
    if value in (None, "", "None"):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite number in final score table")
    return result


def read_scores(path):
    """Read compact completed score rows only, never a raw distribution."""
    numeric = ("m", "p", "cutoff", "n", "count", "gt", "ties", "minus_ulp_ge", "plus_ulp_ge",
               "actual", "ratio", "relative_error", "signed_relative_error", "point_lower", "point_upper",
               "simultaneous_lower", "simultaneous_upper")
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for name in numeric:
            if name in row:
                row[name] = _float(row[name])
        if row.get("available") not in ("True", "False"):
            raise ValueError("score table has an invalid available declaration")
        row["available"] = row["available"] == "True"
        if row.get("classification") in (None, "", "None"):
            row["classification"] = None
    return rows


def _core_classes(rows, winner, probabilities):
    selected = [row for row in rows if row["method"] == winner and row["phase"] == "final_validation"
                and row["p"] in probabilities]
    expected = {(m, p) for m in range(50, 10001, 50) for p in probabilities}
    keys = [(row["m"], row["p"]) for row in selected]
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError("primary classification table does not contain exactly the full planned grid")
    counts = Counter(row["classification"] or "invalid" for row in selected)
    if any(label not in {"confirmed", "inconsistent", "unresolved", "invalid"} for label in counts):
        raise ValueError("unexpected primary interval classification")
    return dict(counts)


def _percent(value):
    return "unavailable" if value is None else f"{100 * value:.3f}%"


def _primary_case_notes(rows, winner):
    """Explain unresolved core cases and tied cutoffs from completed rows only."""
    core_rows = [row for row in rows if row["method"] == winner
                 and row["phase"] == "final_validation" and row["p"] in CORE_P]
    unresolved = [row for row in core_rows if row["classification"] == "unresolved"]
    notes = []
    if unresolved:
        by_p = Counter(row["p"] for row in unresolved)
        breakdown = ", ".join(f"{count} at p={p:g}" for p, count in sorted(by_p.items()))
        notes.append(f"The {len(unresolved)} unresolved core cases comprise {breakdown}. "
                     "Unresolved means the interval crosses a target-band boundary; "
                     "it is neither confirmation nor a demonstrated disjoint-interval violation.")
    for row in core_rows:
        if row["available"] and row["relative_error"] > 0.1 and row.get("ties", 0) > 0:
            notes.append(f"At m={int(row['m'])}, p={row['p']:g}, the observed rate is {row['actual']:.7g} "
                         f"({_percent(row['relative_error'])} relative error). The cutoff is an MI atom: "
                         f"{int(row['ties']):,} validation values equal it exactly. One upward binary64 "
                         f"step would change the exceedance count from {int(row['count']):,} to "
                         f"{int(row['plus_ulp_ge']):,}. This is a discreteness/comparator diagnostic, "
                         "**not** a post-hoc change to the frozen threshold.")
    return "\n\n".join(notes)


def _summary_table(summaries, scope, group="all"):
    lines = ["| Method | Within 10% / planned evaluation cases | Available | Median error | Worst error |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for method in METHODS:
        matches = [row for row in summaries if row["method"] == method and row["phase"] == "final_validation"
                   and row["pscope"] == scope and row["m_group"] == group]
        if len(matches) != 1:
            raise ValueError("missing or duplicate frozen summary entry")
        row = matches[0]
        lines.append(f"| {LABELS[method]} | {row['within10_count']}/{row['total']} | "
                     f"{row['available']}/{row['total']} | {_percent(row['median_absolute_relative_error'])} | "
                     f"{_percent(row['worst_absolute_relative_error'])} |")
    return "\n".join(lines)


def rate_plot(rows, winner, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    colors = {"quadratic": "#8c510a", "pchip": "#01665e"}
    for axis, p in zip(axes.flat, CORE_P):
        axis.axhspan(0.9, 1.1, color="#d9e8d1", alpha=0.7, label="10% target band")
        axis.axhline(1, color="#555555", lw=0.8, ls="--")
        for method in ("quadratic", "pchip"):
            cells = sorted((row for row in rows if row["method"] == method and row["p"] == p
                            and row["phase"] == "final_validation"), key=lambda row: row["m"])
            label = LABELS[method] + (" (selected primary)" if method == winner else " (fixed comparator)")
            axis.plot([row["m"] for row in cells], [row["ratio"] if row["available"] else math.nan for row in cells],
                      color=colors[method], lw=1.6 if method == winner else 1.1, label=label)
            test = [row for row in cells if row["available"] and int(row["m"]) % 500 == 350]
            axis.scatter([row["m"] for row in test], [row["ratio"] for row in test],
                         s=24, facecolors="none", edgecolors=colors[method], linewidths=0.9, zorder=3)
            invalid = sum(not row["available"] for row in cells)
            if invalid:
                axis.text(0.02, 0.03 + 0.05 * (method == "pchip"), f"{LABELS[method]}: {invalid} unavailable (line gaps)",
                          transform=axis.transAxes, fontsize=8, color=colors[method])
        axis.set_xscale("log")
        axis.set_title(f"p = {p:g}")
        axis.set_xlabel("Sample size m (log scale)")
        axis.set_ylabel("Actual null rate / nominal p")
        axis.grid(alpha=0.18)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, frameon=False)
    fig.suptitle("Broad-grid final validation: quadratic and PCHIP empirical cutoff surfaces\n"
                 "Open circles: 20 untouched interpolation-test sizes; no y-axis clipping", fontsize=12)
    for suffix in ("png", "svg"):
        fig.savefig(out / ("null_rate_vs_m." + suffix), dpi=160)
    plt.close(fig)


def render_results(summary, selection, primary, rows, artifact_records):
    winner = selection["selected_model"]
    if winner not in {"quadratic", "pchip"} or primary["selected_model"] != winner:
        raise ValueError("selected and frozen-primary identities disagree")
    core = _core_classes(rows, winner, CORE_P)
    full = _core_classes(rows, winner, COARSE_P)
    accepted = core.get("confirmed", 0) == 800
    verdict = ("All 800 tested core evaluation cases are confirmed under the planned simultaneous interval criterion."
               if accepted else "The proposed core grid is **not confirmed**: not all 800 evaluation cases meet the planned simultaneous interval criterion.")
    candidates = selection["candidates"]
    selection_lines = ["| Candidate | Eligible | Development selection score (loss; lower is better) | Median absolute rate error | Worst error |",
                       "| --- | --- | ---: | ---: | ---: |"]
    for candidate in candidates:
        loss = "unavailable" if candidate["loss"] is None else f"{candidate['loss']:.12g}"
        selection_lines.append(f"| {LABELS[candidate['method']]} | {candidate['eligible']} | {loss} | "
                               f"{_percent(candidate.get('median_absolute_relative_error'))} | "
                               f"{_percent(candidate.get('worst_absolute_relative_error'))} |")
    interval_lines = ["| Primary domain | Planned evaluation cases | Confirmed | Inconsistent | Unresolved | Invalid |",
                      "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for label, expected, counts in (("Four core p levels", 800, core), ("All eight primary p levels", 1600, full)):
        interval_lines.append(f"| {label} | {expected} | {counts.get('confirmed', 0)} | "
                              f"{counts.get('inconsistent', 0)} | {counts.get('unresolved', 0)} | {counts.get('invalid', 0)} |")
    worst = sorted((row for row in rows if row["method"] == winner and row["p"] >= 0.0005 and row["available"]),
                   key=lambda row: row["relative_error"], reverse=True)[:10]
    worst_lines = ["| m | p | Actual / nominal | Absolute relative error | m role |",
                   "| ---: | ---: | ---: | ---: | --- |"]
    for row in worst:
        worst_lines.append(f"| {int(row['m'])} | {row['p']:.8g} | {row['ratio']:.6g} | "
                           f"{_percent(row['relative_error'])} | {row.get('m_group', 'unspecified')} |")
    summaries = summary["final_summary"]
    recovery_note = ("Final scoring was completed by a separately hash-frozen continuation after a Windows "
                     "progress-file replacement failure. It reused the same cached validation data and frozen "
                     "models, without extraction, fitting or selection. See the "
                     "[continuation declaration](../CORRECTION_STATUS_IO_2026-10-17.md) and "
                     "[continuation request](recovery_request.json). Both failed-run records remain "
                     "preserved locally; this is the same evaluation, not a new independent study. "
                     "The complete test suite passed 175/175 tests before continuation. An independent "
                     "read-only audit verified all 39,200 score rows, all 1600 primary interval "
                     "calculations/classifications, all 64 summary records and all 430 continuation input pins."
                     if any(record["name"] == "recovery_request.json" for record in artifact_records) else "")
    artifacts = "\n".join(f"- [{record['name']}]({record['name']}) ({record['bytes']:,} bytes; SHA256 in [manifest.json](manifest.json))."
                          for record in artifact_records if record["name"].endswith(".csv"))
    return f"""# Broad-grid quadratic/PCHIP fitting and final evaluation

The selected primary is **{LABELS[winner]}**, chosen using development fitting
streams before final data were opened. {verdict}

This is the focused two-empirical-surface pass authorized in the
[October 17 amendment](../AMENDMENT_2026-10-17.md), not completion of the original
104-candidate GPD/hybrid/spline study. No SJARACNe engine code or defaults changed.

## Design, numerical policy and opening order

- 200 sizes: m=50,100,...,10000; 10M fitting plus 10M independent validation draws per size.
- Initial construction: 160 training sizes, first 8M fitting draws. Their last 2M draws are diagnostics only.
- Selection: 20 development sample counts (m=450,950,...,9950), crossed with four p levels {{0.05,0.01,0.001,0.0005}}: all 80 equally weighted evaluation cases. Each case is one sample-count/probability pair, not a biological cell.
- The 20 final interpolation-test sizes (m=350,850,...,9850) did not train either final surface. Their fitting distributions and every validation distribution stayed sealed until primary freeze.
- Both procedures were refitted once on full 10M fitting draws at the same 180 non-test sizes. The nonwinner is descriptive, never a fallback.
- Both use the frozen 25 empirical `higher` quantile knots. Quadratic fits log-cutoff on {{1,x,x²}} globally across m; PCHIP interpolates log-cutoff locally across x, where x is normalized log(m).
- Probability interpolation is a separately scoped log-p/log-cutoff PCHIP above and below p=0.0001, with one shared literal boundary cutoff. No rounding, crossing repair, clipping or extrapolation is used.
- Exact binary64 cutoffs are scored with MI>=T. Strict counts, ties and adjacent-ULP counts remain in the CSVs.
- Under the [explicit numerical-zero correction](../CORRECTION_2026-10-17.md), only raw MI in [-64 binary64 epsilon,0) is treated as positive zero. Every positive MI bit is preserved; material negatives remain errors. Original raw files and the failed pre-selection run were not overwritten. Fresh corrected code was frozen before selection or final-data access.
- All 4000 initial quantile hex values and both initial-model files were identical before and after this normalization.
- Cache provenance records original full-stream negative counts/minima. CSV `source_stream_corrected_negative_count` and `source_stream_raw_minimum` expose that provenance; `roundoff_negative_count` describes any additional corrections to the already-normalized scoring input, not the original raw stream. Zero/unique-count diagnostics use normalized values.
- The analysis used at most 12 workers with one numerical thread per worker; no new null draws were generated during fitting.

Opening/selection records are preserved byte-for-byte: [request](request.json),
[selection](selection.json), [frozen primary](primary.json),
[final access lock](access_final.json), and [both refitted models](refit_models.json).
The implementation and original raw distributions are identified by their pinned hashes.

{recovery_note}

## Development selection

The **80 development evaluation cases** are 20 development sample counts
m=450,950,...,9950 (held out from initial fitting), crossed with four nominal
probabilities p={{0.05,0.01,0.001,0.0005}}. An evaluation case is one (m,p)
setting, **not a biological cell or an 80-sample dataset**.

For each evaluation case, c counts MI>=T among n=10,000,000 development null
draws. Define the regularized actual rate `r_tilde=(c+0.5)/(10,000,000+1)`.
The **development loss** is the equally weighted mean of
`[log(r_tilde/p)]^2` across all 80 evaluation cases, using the natural logarithm.
Lower is better; zero is ideal. This is a dimensionless score, **not a
percentage**. The pseudocount is only for this loss; reported actual rates are
c/n. An invalid evaluation case makes a candidate ineligible. Ties within
absolute 1e-12 prefer quadratic. Final validation did not select or revise the
winner.

{chr(10).join(selection_lines)}

## Final observed null-rate errors

“Within 10%” means the observed c/n is within 10% of nominal p. This is **not**
the simultaneous interval acceptance criterion below. Denominators include
every planned evaluation case; unavailable cases are not passes. Median/worst
errors describe available evaluation cases only; full available/invalid/missing counts are retained
in [summary.json](summary.json).

### Four core p levels, all 200 sizes

{_summary_table(summaries, 'core_four')}

### All fixed diagnostic probabilities at p>=0.0005, all 200 sizes

{_summary_table(summaries, 'all_moderate')}

### All 49 probabilities, including weakly measured rare tails

{_summary_table(summaries, 'all_49')}

### The 20 untouched interpolation-test sizes: four core p levels

{_summary_table(summaries, 'core_four', 'final_interpolation_test')}

### The 20 untouched interpolation-test sizes: all moderate probabilities

{_summary_table(summaries, 'all_moderate', 'final_interpolation_test')}

## Primary simultaneous interval assessment

Only the selected frozen primary receives the prospective 99% Bonferroni
study-family intervals across 200x8=1600 evaluation cases. An evaluation case is confirmed when
its entire interval is inside [0.9p,1.1p], inconsistent when disjoint, and
otherwise unresolved. Invalid or unresolved evaluation cases are not passes. The other
models and all extra p probes have descriptive 99.9% pointwise intervals only.

{chr(10).join(interval_lines)}

{verdict} Even universal success on these grid evaluation cases would not establish every
off-grid integer m or arbitrary p. The proposed m range [50,10000] and p range
[0.0005,0.05] were not narrowed after evaluation to hide failures. No fully
general runtime replacement is promoted by this presentation.

{_primary_case_notes(rows, winner)}

## Rate trajectories and largest moderate-domain discrepancies

![Actual/nominal null rates versus sample size](null_rate_vs_m.png)

The shaded band is the +/-10% observed-rate target, not a confidence interval.
Open circles mark the 20 untouched interpolation-test sizes. Both fixed
surfaces are shown, with primary identity stated; y limits do not hide failures.

{chr(10).join(worst_lines)}

## Comparators and limitations

- **Exact-m empirical diagnostic:** each of all 49 cutoffs is calculated directly from the corresponding fitting stream, then scored on independent validation. It is not an interpolated function and is not a selected fallback. Final-test fitting streams supplied this diagnostic only after primary freeze.
- **Untouched legacy-affine comparator:** original coefficients and formula were pinned without tuning. Its nominal p label is not itself a probability guarantee.
- The 49-query summaries are diagnostics, not an additional simultaneous-coverage claim over 9800 evaluation cases. The unselected surface cannot inherit the winner's primary claim.
- At 10M validation draws, expected exceedances at p=1e-5,1e-6,1e-7 are only 100,10,1. In particular, a fitted cutoff at 1e-7 is not evidence for +/-10% tail accuracy. Interpolation does not create missing tail information.
- The experiment calibrates SJARACNe's independent-rank AP-MI null, not biological false-positive rates, direct regulatory edges or downstream network quality.
- This pass does not evaluate the deferred GPD/hybrid/spline model families, off-grid sample sizes, or every probability in a continuous interval.

## Reproducible compact evidence

{artifacts}

The package contains compact tables, fitted models, immutable access/provenance
locks and plots only. The 32GB raw draws and larger analysis caches remain local,
Git-ignored, and are neither copied nor needed to inspect this report.
The [manifest](manifest.json) records source hashes and byte sizes; this
presentation code never reopens raw distributions or refits any model.
"""


def package(analysis, out):
    analysis = Path(analysis).resolve(strict=True)
    out = Path(out).absolute()
    if out.exists() or out.parent.resolve(strict=True) != HERE or out.name != "results_2026-10-17":
        raise ValueError("output must be the fresh broad_grid_10m/results_2026-10-17 directory")
    # Do not read a single score/statistical record before completion is explicit.
    if not (analysis / "summary.json").is_file() or not (analysis / "status.json").is_file():
        raise ValueError("analysis is not complete")
    status = json.loads((analysis / "status.json").read_text(encoding="utf-8"))
    if status.get("phase") != "complete":
        raise ValueError("analysis status is not complete")
    for name in REQUIRED_LOCKS:
        if not (analysis / (name + ".json")).is_file():
            raise ValueError("completed analysis lacks required compact lock: " + name)
    values = {name: read_locked(analysis / (name + ".json")) for name in REQUIRED_LOCKS}
    rows = read_scores(analysis / "final_scores.csv")
    winner = values["selection"]["selected_model"]
    if status.get("primary") != winner:
        raise ValueError("completed status and frozen selection differ")
    _core_classes(rows, winner, CORE_P)
    _core_classes(rows, winner, COARSE_P)
    sources = []
    for stem in LOCKS:
        path = analysis / (stem + ".json")
        if path.is_file():
            read_locked(path)
            sources.extend((path, path.with_suffix(".sha256")))
    for name in ("final_scores.csv", "development_scores.csv", "internal_scores.csv"):
        path = analysis / name
        if path.is_file():
            sources.append(path)
    if not (analysis / "final_scores.csv").is_file():
        raise ValueError("completed final score table is missing")
    source_records = [{"name": path.name, "source": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}
                      for path in sources]
    out.mkdir(exist_ok=False)
    for path, record in zip(sources, source_records):
        shutil.copy2(path, out / path.name)
        if digest(path) != record["sha256"] or digest(out / path.name) != record["sha256"]:
            raise ValueError("compact artifact changed while packaging: " + str(path))
    rate_plot(rows, winner, out)
    text = render_results(values["summary"], values["selection"], values["primary"], rows, source_records)
    with (out / "RESULTS.md").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    manifest = {"format": "apmi-broad-grid-completed-presentation-v1", "analysis_root": str(analysis),
                "selected_primary": winner, "source_artifacts": source_records,
                "presentation_code": {"path": str(Path(__file__).resolve()), "sha256": digest(__file__)},
                "generated_artifacts": [{"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
                                        for path in sorted(out.iterdir()) if path.is_file()],
                "no_raw_draws_read_or_copied": True, "no_model_fits_or_selection": True}
    with (out / "manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"package": str(out), "primary": winner, "source_files": len(source_records)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    package(args.analysis, args.out)


if __name__ == "__main__":
    main()
