"""Pure, serializable quadratic/PCHIP empirical cutoff surfaces.

This module never reads scientific streams.  Callers supply fitting quantiles
and scoring counts under a separately frozen access protocol.  Quadratic and
PCHIP were benchmark comparators in the October 16 specification; promoting
either to a selectable family requires an explicit prospective amendment.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator


_GRID_SPEC = importlib.util.spec_from_file_location(
    "broad_frozen_probability_grid", Path(__file__).parent.parent / "p_axis_refinement" / "grid.py"
)
_GRID = importlib.util.module_from_spec(_GRID_SPEC)
_GRID_SPEC.loader.exec_module(_GRID)
P_KNOTS = tuple(_GRID.DENSE_P)
SELECTION_P = (0.05, 0.01, 0.001, 0.0005)
DEVELOPMENT_M = tuple(range(450, 10000, 500))
SCHEMA = "sjaracne-apmi-empirical-surface-v1"
METHODS = ("quadratic", "pchip")
_LOG_LO = math.log(50.0)
_LOG_WIDTH = math.log(10000.0) - _LOG_LO
_BOUNDARY = 0.0001
_BODY_COUNT = sum(p >= _BOUNDARY for p in P_KNOTS)


def _number(value):
    return not isinstance(value, (bool, np.bool_)) and isinstance(value, (int, float, np.integer, np.floating))


def _coordinate(m):
    return (np.log(m) - _LOG_LO) / _LOG_WIDTH


def fit_surface(train_m, quantiles, method="quadratic"):
    """Fit 25 independent log-cutoff curves across m; return a JSON-safe dict.

    A failed column is retained as unavailable, so a rare-only failure cannot
    erase valid moderate-p predictions.  Input dimensions/domain errors raise
    ValueError; scientific cutoff errors invalidate their entire column.
    """
    if method not in METHODS:
        raise ValueError("method must be quadratic or pchip")
    supplied_m = list(train_m)
    if any(not _number(m) or not math.isfinite(float(m)) for m in supplied_m):
        raise ValueError("training m must be finite real numbers")
    ms = np.asarray(supplied_m, dtype=np.float64)
    minimum = 3 if method == "quadratic" else 2
    if ms.ndim != 1 or len(ms) < minimum or np.any(ms < 50) or np.any(ms > 10000) or np.any(np.diff(ms) <= 0):
        raise ValueError("training m must increase strictly within [50,10000] with enough points")
    array = np.asarray(quantiles)
    if array.dtype.kind not in "fiu" or array.shape != (len(ms), len(P_KNOTS)):
        raise ValueError("quantiles must be a real numeric n_m by 25 matrix")
    values = array.astype(np.float64)
    x = _coordinate(ms)
    design = np.column_stack((np.ones(len(ms)), x, x * x))
    columns = []
    for j, p in enumerate(P_KNOTS):
        observed = values[:, j]
        column = {
            "p": p,
            "available": False,
            "reason": None,
            "observed": [float(t) if math.isfinite(float(t)) else None for t in observed],
            "observed_hex": [float(t).hex() if math.isfinite(float(t)) else None for t in observed],
        }
        if not np.all(np.isfinite(observed)):
            column["reason"] = "nonfinite_training_cutoff"
        elif np.any(observed <= 0):
            column["reason"] = "nonpositive_training_cutoff"
        elif np.any(observed > np.log(ms)):
            column["reason"] = "training_cutoff_above_log_m"
        else:
            transformed = np.log(observed)
            if method == "quadratic":
                try:
                    coefficients, _, rank, singular = np.linalg.lstsq(design, transformed, rcond=None)
                    if rank != 3 or not np.all(np.isfinite(coefficients)):
                        column["reason"] = "invalid_quadratic_fit"
                    else:
                        column.update(
                            coefficients=coefficients.tolist(), rank=int(rank),
                            singular_values=singular.tolist(),
                            condition_number=float(singular[0] / singular[-1]),
                        )
                        column["available"] = True
                except np.linalg.LinAlgError as error:
                    column["reason"] = "quadratic_fit_failed: " + str(error)
            else:
                # Explicit construction checks the deterministic SciPy contract;
                # storing transformed observations reproduces this interpolant.
                try:
                    PchipInterpolator(x, transformed, extrapolate=False)
                    column.update(log_values=transformed.tolist())
                    column["available"] = True
                except ValueError as error:
                    column["reason"] = "pchip_fit_failed: " + str(error)
        columns.append(column)
    return {
        "schema": SCHEMA,
        "method": method,
        "train_m": ms.tolist(),
        "p_knots": list(P_KNOTS),
        "m_coordinate": {"minimum": 50, "maximum": 10000, "transform": "normalized_log"},
        "p_interpolation": "separate_pchip_log_p_log_cutoff_at_0.0001",
        "columns": columns,
    }


def _predicted_knots(model, m):
    """Return literal predicted knots or None and per-column reasons."""
    if model.get("schema") != SCHEMA or model.get("method") not in METHODS:
        raise ValueError("unrecognized model schema or method")
    if model.get("p_knots") != list(P_KNOTS) or len(model.get("columns", [])) != len(P_KNOTS):
        raise ValueError("model probability knots do not match the frozen grid")
    ms = np.asarray(model["train_m"], dtype=np.float64)
    if ms.ndim != 1 or len(ms) < 2 or not np.all(np.isfinite(ms)) or np.any(np.diff(ms) <= 0):
        raise ValueError("malformed model training coordinates")
    if m < ms[0] or m > ms[-1]:
        return [None] * len(P_KNOTS), ["m_outside_training_range"] * len(P_KNOTS)
    x = float(_coordinate(float(m)))
    exact = np.flatnonzero(ms == m)
    result, reasons = [], []
    for column in model["columns"]:
        if not column.get("available"):
            result.append(None)
            reasons.append(column.get("reason") or "column_unavailable")
            continue
        if model["method"] == "pchip" and len(exact):
            # Literal return avoids exp(log(T)) shifting a discrete MI atom.
            value = float.fromhex(column["observed_hex"][int(exact[0])])
        else:
            if model["method"] == "quadratic":
                coefficients = np.asarray(column["coefficients"], dtype=np.float64)
                log_value = float(coefficients @ np.asarray([1.0, x, x * x]))
            else:
                curve = PchipInterpolator(_coordinate(ms), column["log_values"], extrapolate=False)
                log_value = float(curve(x))
            with np.errstate(over="ignore", under="ignore", invalid="ignore"):
                value = float(np.exp(log_value))
        reason = None
        if not math.isfinite(value):
            reason = "nonfinite_predicted_cutoff"
        elif value <= 0:
            reason = "nonpositive_predicted_cutoff"
        elif value > math.log(m):
            reason = "predicted_cutoff_above_log_m"
        result.append(value if reason is None else None)
        reasons.append(reason)
    return result, reasons


def _scope(knots, reasons, indices):
    values = [knots[i] for i in indices]
    failed = [f"p={P_KNOTS[i]:.17g}:{reasons[i]}" for i in indices if knots[i] is None]
    if failed:
        return None, "invalid_scope_knot: " + "; ".join(failed)
    # P_KNOTS descend, so cutoffs must increase or remain equal.
    if np.any(np.diff(values) < 0):
        return None, "crossed_scope_knots"
    ps = np.asarray([P_KNOTS[i] for i in indices])
    try:
        interpolator = PchipInterpolator(np.log(ps[::-1]), np.log(values[::-1]), extrapolate=False)
    except ValueError as error:
        return None, "scope_pchip_failed: " + str(error)
    return interpolator, None


def predict_surface(model, m, probabilities):
    """Predict one m and an iterable of p; unavailable predictions remain rows.

    No extrapolation, clipping, sorting of crossed cutoffs, or observed-value
    overrides of a quadratic fit are permitted.  ``source`` identifies the
    independently validated moderate or rare interpolation scope.
    """
    probabilities = list(probabilities)
    valid_m = _number(m) and math.isfinite(float(m)) and 50 <= float(m) <= 10000
    if valid_m:
        m = float(m)
        knots, reasons = _predicted_knots(model, m)
        moderate, moderate_reason = _scope(knots, reasons, range(_BODY_COUNT))
        rare, rare_reason = _scope(knots, reasons, range(_BODY_COUNT - 1, len(P_KNOTS)))
    else:
        moderate = rare = None
        moderate_reason = rare_reason = "m_outside_domain"
    rows = []
    for supplied_p in probabilities:
        valid_p = _number(supplied_p) and math.isfinite(float(supplied_p)) and P_KNOTS[-1] <= float(supplied_p) <= P_KNOTS[0]
        p = float(supplied_p) if _number(supplied_p) and math.isfinite(float(supplied_p)) else None
        source = "moderate" if p is not None and p >= _BOUNDARY else "rare"
        row = {"m": float(m) if valid_m else None, "p": p, "source": source,
               "available": False, "cutoff": None, "cutoff_hex": None, "reason": None}
        reason = moderate_reason if source == "moderate" else rare_reason
        if not valid_m:
            row["reason"] = "m_outside_domain"
        elif not valid_p:
            row["reason"] = "p_outside_domain"
        elif reason is not None:
            row["reason"] = reason
        else:
            if p in P_KNOTS:
                cutoff = knots[P_KNOTS.index(p)]
            else:
                curve = moderate if source == "moderate" else rare
                with np.errstate(over="ignore", under="ignore", invalid="ignore"):
                    cutoff = float(np.exp(curve(math.log(p))))
            if not math.isfinite(cutoff) or not (0 < cutoff <= math.log(m)):
                row["reason"] = "invalid_interpolated_cutoff"
            else:
                row.update(available=True, cutoff=cutoff, cutoff_hex=cutoff.hex())
        rows.append(row)
    return rows


def selection_loss(records):
    """Equal-weight 80-cell prospective loss, with no missing-cell fallback.

    Each row requires m, p, count and n; an explicit available=False invalidates
    it.  Only the 20 fixed development sizes and four selection probabilities
    are accepted.  Returned JSON uses None instead of infinity.
    """
    expected = {(m, p) for m in DEVELOPMENT_M for p in SELECTION_P}
    seen, losses, errors, failures = set(), [], [], []
    for row in records:
        m, p = row.get("m"), row.get("p")
        key = (m, p)
        if key not in expected or key in seen:
            failures.append("unexpected_or_duplicate_cell")
            continue
        seen.add(key)
        n, c = row.get("n"), row.get("count")
        if row.get("available", True) is not True:
            failures.append("unavailable_cell")
        elif (not isinstance(n, (int, np.integer)) or isinstance(n, (bool, np.bool_)) or n <= 0
              or not isinstance(c, (int, np.integer)) or isinstance(c, (bool, np.bool_)) or not 0 <= c <= n):
            failures.append("invalid_counts")
        else:
            log_ratio = math.log(((int(c) + 0.5) / (int(n) + 1)) / p)
            losses.append(log_ratio * log_ratio)
            errors.append(abs((int(c) / int(n)) / p - 1.0))
    if seen != expected:
        failures.append("missing_cells")
    eligible = not failures and len(losses) == len(expected)
    return {
        "eligible": eligible,
        "loss": float(math.fsum(losses) / len(expected)) if eligible else None,
        "cells_expected": len(expected), "cells_valid": len(losses),
        "median_absolute_relative_error": float(np.median(errors)) if eligible else None,
        "worst_absolute_relative_error": float(max(errors)) if eligible else None,
        "failures": failures,
    }


def select_surface(candidates):
    """Select between explicitly authorized quadratic/PCHIP loss summaries.

    A caller must prospectively authorize these comparator families as primary
    before calling this helper.  Within absolute 1e-12 of the best finite loss,
    quadratic is first.  Refit failures must not call this helper again.
    """
    supplied = list(candidates)
    if any(row.get("method") not in METHODS for row in supplied):
        raise ValueError("selection permits only the declared two methods")
    if len({row["method"] for row in supplied}) != len(supplied):
        raise ValueError("duplicate candidate method")
    eligible = [row for row in supplied if row.get("eligible") is True and _number(row.get("loss"))
                and math.isfinite(float(row["loss"])) and float(row["loss"]) >= 0]
    if not eligible:
        return {"selected_method": None, "reason": "no_finite_eligible_loss"}
    minimum = min(float(row["loss"]) for row in eligible)
    tied = [row for row in eligible if abs(float(row["loss"]) - minimum) <= 1e-12]
    winner = min(tied, key=lambda row: METHODS.index(row["method"]))
    return {"selected_method": winner["method"], "selected_loss": float(winner["loss"]),
            "minimum_loss": minimum, "tie_tolerance": 1e-12,
            "tied_methods": [name for name in METHODS if any(row["method"] == name for row in tied)]}
