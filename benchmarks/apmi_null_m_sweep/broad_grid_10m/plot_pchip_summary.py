#!/usr/bin/env python3
"""Plot archived PCHIP final-validation rates without fitting or raw-data access.

Only the completed final_scores.csv is read. No null distributions, model
artifacts, extraction code, fitting code or selection implementation is opened.
Outputs are presentation assets; this script makes no acceptance decision.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


CORE_P = (0.05, 0.01, 0.001, 0.0005)
GRID_M = tuple(range(50, 10001, 50))
N_DRAWS = 10_000_000
STEM = "pchip_null_rate_vs_m"


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _finite(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("invalid archived " + name) from error
    if not math.isfinite(result):
        raise ValueError("nonfinite archived " + name)
    return result


def _role(m):
    return ("final_interpolation_test" if m % 500 == 350 else
            "development" if m % 500 == 450 else "training")


def _coverage(rows):
    expected = {(m, p) for m in GRID_M for p in CORE_P}
    actual = [(row["m"], row["p"]) for row in rows]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("exactly 800 unique planned PCHIP core evaluation cases required")


def read_core_rows(path):
    """Validate and return all 800 PCHIP core cases, including unavailable ones."""
    selected = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"method", "phase", "m", "p", "available", "n", "count", "actual", "ratio"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("archived score table lacks required presentation columns")
        for record in reader:
            if record["method"] != "pchip" or record["phase"] != "final_validation":
                continue
            p = _finite(record["p"], "probability")
            if p not in CORE_P:
                continue
            m = _finite(record["m"], "sample count")
            if not m.is_integer() or int(m) not in GRID_M:
                raise ValueError("archived PCHIP sample count is outside the frozen grid")
            m = int(m)
            n = _finite(record["n"], "draw count")
            if n != N_DRAWS:
                raise ValueError("PCHIP final validation requires exactly 10M draws per case")
            if record["available"] not in {"True", "False"}:
                raise ValueError("invalid archived availability flag")
            available = record["available"] == "True"
            if record.get("m_group") not in (None, "", _role(m)):
                raise ValueError("archived sample-count role contradicts the frozen split")
            row = {"m": m, "p": p, "n": N_DRAWS, "available": available,
                   "m_group": _role(m), "count": None, "actual": None, "ratio": None,
                   "reason": record.get("reason") or None}
            if available:
                count = _finite(record["count"], "exceedance count")
                if not count.is_integer() or not 0 <= count <= N_DRAWS:
                    raise ValueError("invalid archived exceedance count")
                actual = int(count) / N_DRAWS
                ratio = actual / p
                if _finite(record["actual"], "actual rate") != actual or _finite(record["ratio"], "rate ratio") != ratio:
                    raise ValueError("archived actual rate/ratio does not match the literal count")
                row.update(count=int(count), actual=actual, ratio=ratio)
            selected.append(row)
    _coverage(selected)
    return sorted(selected, key=lambda row: (CORE_P.index(row["p"]), row["m"]))


def make_figure(rows):
    """Create four core-p panels; unavailable predictions break the curves."""
    _coverage(rows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    curve_color, test_color = "#2166ac", "#b35806"
    for axis, p in zip(axes.flat, CORE_P):
        selected = sorted((row for row in rows if row["p"] == p), key=lambda row: row["m"])
        axis.axhspan(0.9, 1.1, color="#deebd8", alpha=0.85, label="+/-10% observed-rate band", zorder=0)
        axis.axhline(1, color="#555555", lw=0.9, ls="--", label="Ideal ratio = 1", zorder=1)
        axis.plot([row["m"] for row in selected],
                  [row["ratio"] if row["available"] else math.nan for row in selected],
                  color=curve_color, lw=1.5, label="PCHIP (selected primary)", zorder=2)
        test = [row for row in selected if row["available"] and row["m_group"] == "final_interpolation_test"]
        axis.scatter([row["m"] for row in test], [row["ratio"] for row in test], s=28,
                     facecolors="none", edgecolors=test_color, linewidths=1.05,
                     label="Untouched interpolation-test m", zorder=3)
        unavailable = sum(not row["available"] for row in selected)
        if unavailable:
            axis.text(0.02, 0.04, f"{unavailable} unavailable cases (line gaps)", transform=axis.transAxes,
                      fontsize=8, color="#7f2704")
        axis.set_xscale("log")
        axis.set_xticks((50, 100, 200, 500, 1000, 2000, 5000, 10000),
                        labels=("50", "100", "200", "500", "1k", "2k", "5k", "10k"))
        axis.tick_params(axis="x", labelsize=8)
        axis.set_title(f"Requested p = {p:g}", fontsize=11)
        axis.set_xlabel("Sample count m (log scale)")
        axis.set_ylabel("Actual / requested null rate")
        axis.grid(alpha=0.16)
        # Deliberately retain autoscaled y limits: no failures are clipped.
    handles, labels = axes.flat[0].get_legend_handles_labels()
    order = (2, 3, 0, 1)
    fig.legend([handles[i] for i in order], [labels[i] for i in order], loc="outside lower center",
               ncol=2, frameon=False, fontsize=9)
    fig.suptitle("PCHIP empirical cutoff surface: final null-rate trajectories\n"
                 "200 sample counts; shading is a rate tolerance, not a confidence interval", fontsize=12)
    return fig, axes


def render(csv_path, out):
    """Write deterministic static assets to a fresh output directory only."""
    csv_path = Path(csv_path).resolve(strict=True)
    out = Path(out).absolute()
    if out.exists():
        raise ValueError("plot output directory must be fresh; archived assets are never overwritten")
    input_hash = sha256(csv_path)
    rows = read_core_rows(csv_path)
    import matplotlib
    import matplotlib.pyplot as plt
    with matplotlib.rc_context({"svg.hashsalt": "sjaracne-apmi-pchip-summary-v1", "font.family": "DejaVu Sans"}):
        fig, _ = make_figure(rows)
        out.mkdir(parents=True, exist_ok=False)
        try:
            fig.savefig(out / (STEM + ".png"), dpi=170,
                        metadata={"Software": "SJARACNe benchmark PCHIP presentation"})
            fig.savefig(out / (STEM + ".svg"), metadata={"Date": None, "Creator": "SJARACNe benchmark PCHIP presentation"})
        finally:
            plt.close(fig)
    if sha256(csv_path) != input_hash:
        raise ValueError("archived CSV changed while rendering presentation")
    return {"input": str(csv_path), "input_sha256": input_hash,
            "evaluation_cases": len(rows), "sample_counts": len(GRID_M), "core_p": list(CORE_P),
            "outputs": [{"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
                        for path in sorted(out.iterdir())],
            "no_raw_draws_fitting_or_selection": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="Archived final_scores.csv only")
    parser.add_argument("--out", required=True, type=Path, help="Fresh presentation-assets directory")
    args = parser.parse_args()
    print(json.dumps(render(args.csv, args.out), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
