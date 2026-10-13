#!/usr/bin/env python3
"""Freeze the available Fig. 6a source points without inventing its missing ROC."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import openpyxl


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def extract(sheet):
    """The workbook has independent TP, EPR and truncated ROC column blocks."""
    tp, epr, roc = [], [], []
    expected = (
        "# Top_Ranked_Edges", "# True_Postive_Edges", "Method",
        "# Top_Ranked_Edges", "Early_Precision_Ratio", "1-Specificity",
        "Sensitivity", "Method",
    )
    rows = sheet.iter_rows(min_col=1, max_col=8, values_only=True)
    next(rows)
    if tuple(next(rows)) != expected:
        raise ValueError("Unrecognized Figure_6a headers; do not silently remap columns")
    for index, row in enumerate(rows, start=3):
        k, hits, method, ek, ratio, fpr, tpr, roc_method = row
        if k is None and (hits is not None or method is not None):
            raise ValueError(f"Orphan TP fields at row {index}")
        if k is not None:
            if method not in ("scMINER", "Random") or k <= 0 or int(k) != k:
                raise ValueError(f"Invalid TP point at row {index}")
            if hits is None or hits < 0 or int(hits) != hits or hits > k:
                raise ValueError(f"Invalid TP count at row {index}")
            tp.append((int(k), int(hits), method, index))
        if ek is not None:
            if ek <= 0 or not math.isfinite(ek) or int(ek) != ek:
                raise ValueError(f"Invalid EPR rank at row {index}")
            if ratio is None or not math.isfinite(ratio) or ratio < 0:
                raise ValueError(f"Invalid EPR at row {index}")
            epr.append((int(ek), float(ratio), index))
        elif ratio is not None:
            raise ValueError(f"Orphan EPR field at row {index}")
        if fpr is not None:
            if not (0 <= fpr <= 1 and tpr is not None and 0 <= tpr <= 1
                    and roc_method in ("scMINER", "Random")):
                raise ValueError(f"Invalid ROC point at row {index}")
            roc.append((float(fpr), float(tpr), roc_method, index))
        elif tpr is not None or roc_method is not None:
            raise ValueError(f"Orphan ROC fields at row {index}")
    lookup = {(k, method): hits for k, hits, method, _ in tp}
    if len(lookup) != len(tp):
        raise ValueError("Duplicate source TP points")
    if len(set(k for k, _, _ in epr)) != len(epr):
        raise ValueError("Duplicate source EPR points")
    for k, ratio, index in epr:
        random = lookup.get((k, "Random"))
        if not random:
            raise ValueError(f"Cannot reconcile EPR denominator at row {index}")
        if not math.isclose(ratio, lookup[(k, "scMINER")] / random, rel_tol=1e-12):
            raise ValueError(f"Published EPR does not reconcile at row {index}")
    if not tp or not epr or not roc:
        raise ValueError("Missing Fig. 6a source-data block")
    return tp, epr, roc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    before = sha256(args.workbook)
    workbook = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    try:
        tp, epr, roc = extract(workbook["Figure_6a"])
    finally:
        workbook.close()
    if sha256(args.workbook) != before:
        raise RuntimeError("Source workbook changed during extraction")
    args.out.mkdir(parents=True, exist_ok=False)
    outputs = (
        ("tp.tsv", ("k", "TP", "method", "worksheet_row"), tp),
        ("epr.tsv", ("k", "EPR", "worksheet_row"), epr),
        ("roc_segment.tsv", ("FPR", "TPR", "method", "worksheet_row"), roc),
    )
    for filename, headers, data in outputs:
        with (args.out / filename).open("x", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(headers)
            writer.writerows(data)
    manifest = {
        "source": str(args.workbook.resolve()), "source_sha256": before,
        "sheet": "Figure_6a", "script_sha256": sha256(__file__),
        "paper": "https://www.nature.com/articles/s41467-025-59620-6",
        "published_AUROC_rounded": 0.75,
        "AUROC_source": "Paper Results; NOT calculated from truncated workbook ROC",
        "tp_counts": {method: sum(row[2] == method for row in tp)
                      for method in ("scMINER", "Random")},
        "epr_points": len(epr), "roc_points": len(roc),
        "roc_FPR_range": [min(row[0] for row in roc), max(row[0] for row in roc)],
        "roc_TPR_range": [min(row[1] for row in roc), max(row[1] for row in roc)],
        "roc_methods": sorted(set(row[2] for row in roc)),
        "full_ROC_available": False,
        "limits": "Exported ROC is incomplete; no extrapolation, full-area integration, or random ROC fabrication.",
        "outputs_sha256": {name: sha256(args.out / name) for name, _, _ in outputs},
    }
    with (args.out / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print(json.dumps({key: manifest[key] for key in
                      ("tp_counts", "epr_points", "roc_points", "roc_FPR_range")}))


if __name__ == "__main__":
    main()
