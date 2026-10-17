"""Pure scoring and fixed-denominator summaries for the frozen analysis.

Only caller-supplied, already opened arrays are scored. This module performs
no scientific file reads, parameter fitting, candidate selection or retries.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math

import numpy as np
from scipy.stats import beta

try:
    from . import fit_data, fit_models
except ImportError:
    import fit_data
    import fit_models


COARSE_P = tuple(fit_models._GRID.COARSE_P)
ALL_P = tuple(fit_models._GRID.ALL_P)
GRID_M = tuple(range(50, 10001, 50))
CORE_P = tuple(fit_models.SELECTION_P)
SCOPES = {
    "core_four": CORE_P,
    "primary_eight": COARSE_P,
    "all_moderate": tuple(p for p in ALL_P if p >= 0.0005),
    "all_49": ALL_P,
}
POINT_CONFIDENCE = 0.999
FAMILY_CONFIDENCE = 0.99
FAMILY_SIZE = 1600
POINT_ALPHA = 0.001
FAMILY_ALPHA = 0.01


def _real(value):
    return (not isinstance(value, (bool, np.bool_))
            and isinstance(value, (int, float, np.integer, np.floating))
            and math.isfinite(float(value)))


def _intervals(counts, n, alpha):
    """Vectorized two-sided exact Clopper-Pearson, with literal endpoints."""
    counts = np.asarray(counts, dtype=np.int64)
    lower = np.zeros(len(counts), dtype=np.float64)
    upper = np.ones(len(counts), dtype=np.float64)
    lower_mask = counts > 0
    upper_mask = counts < n
    lower[lower_mask] = beta.ppf(alpha / 2, counts[lower_mask], n - counts[lower_mask] + 1)
    upper[upper_mask] = beta.ppf(1 - alpha / 2, counts[upper_mask] + 1, n - counts[upper_mask])
    if not np.all(np.isfinite(lower)) or not np.all(np.isfinite(upper)):
        raise ValueError("nonfinite exact binomial interval")
    return lower, upper


def score_predictions(values, predictions, method, phase, primary=False):
    """Score each prediction literally; preserve unavailable predictions.

    ``values`` must be an ascending, finite float64 vector. Only the single
    frozen primary, scored in phase ``final_validation``, receives the planned
    simultaneous intervals at the eight primary probabilities. Other rows
    receive descriptive pointwise intervals only. ``relative_error`` is the
    absolute relative error; ``signed_relative_error`` retains its direction.
    The shared data-layer roundoff policy maps only [-64eps,0) to positive
    zero in a read-only analysis copy. Raw inputs are never modified. The
    roundoff fields audit this caller-supplied vector before normalization;
    generation-byte normalization provenance is separately retained by caches.
    """
    if not isinstance(method, str) or not method or not isinstance(phase, str) or not phase:
        raise ValueError("nonempty method and phase labels required")
    if not isinstance(primary, bool):
        raise ValueError("primary must be a boolean")
    supplied_values = np.asarray(values)
    values = fit_data.normalize_roundoff(supplied_values)
    array_summary = fit_data.sorted_summary(values)
    raw_minimum = float(np.min(supplied_values))
    roundoff_negative_count = int(np.count_nonzero(supplied_values < 0))
    n = int(values.size)
    rows, available_indices = [], []
    for prediction in predictions:
        row = dict(prediction)
        p, m, cutoff = row.get("p"), row.get("m"), row.get("cutoff")
        row.update(method=method, phase=phase, n=n, count=None, gt=None, ties=None,
                   minus_ulp_ge=None, plus_ulp_ge=None, actual=None, ratio=None,
                   relative_error=None, signed_relative_error=None,
                   point_lower=None, point_upper=None,
                   simultaneous_lower=None, simultaneous_upper=None,
                   classification=None, simultaneous_applicable=False,
                   zero_count=array_summary["zero_count"], unique_count=array_summary["unique_count"],
                   roundoff_negative_count=roundoff_negative_count,
                   roundoff_tolerance=fit_data.SUPPORT_TOLERANCE,
                   raw_minimum=raw_minimum,
                   engine_zero_omission_count=None)
        reason = row.get("reason")
        if not _real(p) or not 0 < float(p) < 1:
            reason = "invalid_probability"
            row["p"] = float(p) if _real(p) else None
        else:
            row["p"] = float(p)
        if not _real(m) or float(m) < 2:
            reason = "invalid_sample_size"
            row["m"] = float(m) if _real(m) else None
        else:
            row["m"] = float(m)
        if not _real(cutoff):
            reason = reason or "invalid_cutoff"
            row["cutoff"] = None
            row["cutoff_hex"] = None
        elif _real(m) and float(m) >= 2 and not 0 <= float(cutoff) <= math.log(float(m)):
            reason = reason or "cutoff_outside_MI_support"
        if row.get("available") is not True or reason:
            row.update(available=False, reason=reason or "prediction_unavailable")
            if primary and phase == "final_validation" and row.get("p") in COARSE_P:
                row.update(classification="invalid", simultaneous_applicable=True)
        else:
            count = fit_data.count_sorted(values, cutoff)
            actual = count["ge"] / n
            ratio = actual / float(p)
            row.update(available=True, reason=None, cutoff=float(cutoff), cutoff_hex=float(cutoff).hex(),
                       count=count["ge"], gt=count["gt"], ties=count["ties"],
                       minus_ulp_ge=count["minus_ulp_ge"], plus_ulp_ge=count["plus_ulp_ge"],
                       actual=actual, ratio=ratio, relative_error=abs(ratio - 1),
                       signed_relative_error=ratio - 1,
                       engine_zero_omission_count=count["ge"] - array_summary["zero_count"] if cutoff == 0 else count["ge"])
            available_indices.append(len(rows))
        rows.append(row)
    if available_indices:
        counts = [rows[i]["count"] for i in available_indices]
        lower, upper = _intervals(counts, n, POINT_ALPHA)
        for index, lo, hi in zip(available_indices, lower, upper):
            rows[index].update(point_lower=float(lo), point_upper=float(hi))
    simultaneous_indices = [i for i in available_indices if primary and phase == "final_validation" and rows[i]["p"] in COARSE_P]
    if simultaneous_indices:
        lower, upper = _intervals([rows[i]["count"] for i in simultaneous_indices], n,
                                 FAMILY_ALPHA / FAMILY_SIZE)
        for index, lo, hi in zip(simultaneous_indices, lower, upper):
            row = rows[index]
            p = row["p"]
            if lo >= 0.9 * p and hi <= 1.1 * p:
                classification = "confirmed"
            elif hi < 0.9 * p or lo > 1.1 * p:
                classification = "inconsistent"
            else:
                classification = "unresolved"
            row.update(simultaneous_lower=float(lo), simultaneous_upper=float(hi),
                       classification=classification, simultaneous_applicable=True)
    return rows


def _group(m):
    return ("final_interpolation_test" if m % 500 == 350 else
            "development" if m % 500 == 450 else "training")


def _phase_sizes(phase):
    if phase in {"internal", "internal_development", "training_internal"}:
        return tuple(m for m in GRID_M if _group(m) == "training")
    if phase in {"development", "development_selection"}:
        return tuple(m for m in GRID_M if _group(m) == "development")
    if phase in {"final_test_fit", "final_test_fit_diagnostic", "final_test_baseline"}:
        return tuple(m for m in GRID_M if _group(m) == "final_interpolation_test")
    # Unknown phase labels do not imply a favorable observed-only denominator.
    return GRID_M


def summarize(rows, expected_m=None):
    """Return method/phase/m-group/p-scope summaries with fixed denominators.

    Missing cells, duplicate cells and unavailable predictions are explicit
    non-passes. Error quantiles describe available cells only, with that
    denominator stated. The known phases infer their prospectively fixed m
    set; ``expected_m`` can explicitly supply one immutable m set for a caller's
    diagnostic phase. Unknown phase names conservatively expect all 200 sizes.
    """
    rows = list(rows)
    if expected_m is not None:
        supplied = list(expected_m)
        if (not supplied or any(isinstance(m, bool) or not isinstance(m, (int, np.integer)) or m not in GRID_M for m in supplied)
                or len(set(supplied)) != len(supplied)):
            raise ValueError("expected_m must be distinct frozen-grid integer sizes")
        expected_m = tuple(sorted(map(int, supplied)))
    grouped = defaultdict(list)
    for row in rows:
        if not isinstance(row.get("method"), str) or not isinstance(row.get("phase"), str):
            raise ValueError("summary rows require method and phase labels")
        grouped[(row["method"], row["phase"])].append(row)
    summaries = []
    for (method, phase), member_rows in sorted(grouped.items()):
        sizes = expected_m if expected_m is not None else _phase_sizes(phase)
        out_of_grid_rows = sum(row.get("m") not in sizes or row.get("p") not in ALL_P for row in member_rows)
        m_groups = ["all"] + [name for name in ("training", "development", "final_interpolation_test")
                              if any(_group(m) == name for m in sizes)]
        for m_group in m_groups:
            selected_m = sizes if m_group == "all" else tuple(m for m in sizes if _group(m) == m_group)
            for pscope, probabilities in SCOPES.items():
                expected = {(m, p) for m in selected_m for p in probabilities}
                cells = defaultdict(list)
                for row in member_rows:
                    key = (row.get("m"), row.get("p"))
                    if key in expected:
                        cells[key].append(row)
                available, invalid, missing, duplicates, errors = 0, 0, 0, 0, []
                within, classes = 0, Counter()
                for cell in expected:
                    entries = cells.get(cell, [])
                    if not entries:
                        missing += 1
                        classes["missing"] += 1
                    elif len(entries) != 1:
                        duplicates += 1
                        invalid += 1
                        classes["invalid"] += 1
                    else:
                        row = entries[0]
                        error = row.get("relative_error")
                        if row.get("available") is not True or not _real(error) or error < 0:
                            invalid += 1
                            classes["invalid"] += 1
                        else:
                            available += 1
                            errors.append(float(error))
                            within += int(error <= 0.1)
                            classes[row.get("classification") or "not_applicable"] += 1
                summaries.append({
                    "method": method, "phase": phase, "m_group": m_group, "pscope": pscope,
                    "total": len(expected), "reported": sum(len(v) for v in cells.values()),
                    "out_of_grid_rows": out_of_grid_rows,
                    "available": available, "invalid": invalid, "missing": missing,
                    "duplicate_cells": duplicates, "within10_count": within,
                    "within10_fraction": within / len(expected),
                    "error_stat_denominator": available,
                    "median_absolute_relative_error": float(np.median(errors)) if errors else None,
                    "p90_absolute_relative_error": float(np.quantile(errors, 0.9)) if errors else None,
                    "worst_absolute_relative_error": max(errors) if errors else None,
                    "classes": dict(sorted(classes.items())),
                })
    return summaries
