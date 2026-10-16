"""Frozen, deterministic probability grids for the exploratory p-axis refinement.

Grid construction is exact in decimal arithmetic until the final float conversion.
The new probes are rounded geometric midpoints of adjacent moderate dense knots,
not fitting knots. Their 14-significant-digit decimal rounding is part of the
protocol. This module performs no file access, random sampling, or fitting.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import math


_COARSE_DECIMAL = tuple(map(Decimal, (
    "0.05", "0.01", "0.001", "0.0005", "0.0001", "0.00001",
    "0.000001", "0.0000001",
)))
_OLD_PROBE_DECIMAL = tuple(map(Decimal, (
    "0.02", "0.005", "0.002", "0.00075", "0.0002", "0.00005",
    "0.000005", "0.0000005",
)))


def _dense_decimals():
    mantissas = tuple(map(Decimal, ("1", "1.5", "2", "3", "4", "5", "6", "7.5")))
    with localcontext() as context:
        context.prec = 50
        values = {a * Decimal(10) ** exponent
                  for exponent in (-4, -3, -2) for a in mantissas
                  if a * Decimal(10) ** exponent <= Decimal("0.05")}
    values.update(map(Decimal, ("0.00001", "0.000001", "0.0000001")))
    return tuple(sorted(values, reverse=True))


def _midpoint_decimal(upper, lower):
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        midpoint = (upper * lower).sqrt()
        context.prec = 14
        # Unary plus applies the frozen significant-digit rounding policy.
        return +midpoint


_DENSE_DECIMAL = _dense_decimals()
_MODERATE_DECIMAL = tuple(p for p in _DENSE_DECIMAL if p >= Decimal("0.0001"))
_NEW_PROBE_DECIMAL = tuple(_midpoint_decimal(a, b)
                         for a, b in zip(_MODERATE_DECIMAL, _MODERATE_DECIMAL[1:]))
_OLD_QUERY_DECIMAL = tuple(sorted(set(_COARSE_DECIMAL + _OLD_PROBE_DECIMAL), reverse=True))
_ALL_DECIMAL = tuple(sorted(set(_DENSE_DECIMAL + _NEW_PROBE_DECIMAL + _OLD_QUERY_DECIMAL),
                            reverse=True))

COARSE_P = tuple(map(float, _COARSE_DECIMAL))
DENSE_P = tuple(map(float, _DENSE_DECIMAL))
NEW_PROBE_P = tuple(map(float, _NEW_PROBE_DECIMAL))
OLD_PROBE_P = tuple(map(float, _OLD_PROBE_DECIMAL))
OLD_QUERY_P = tuple(map(float, _OLD_QUERY_DECIMAL))
ALL_P = tuple(map(float, _ALL_DECIMAL))
PRIMARY_P = (0.001, 0.0005)
GRIDM = (30, 50, 80, 90, 100, 150, 200, 250, 300, 400, 500, 516,
         600, 644, 700, 725, 800, 900, 1000)
SMOOTHERS = ("loglinear", "logquadratic", "pchip")


def probability_roles(probability):
    """Return overlapping boolean memberships for a probability in ALL_P.

``moderate`` is the principal p >= 0.0005 evaluation range, distinct from the
dense-knot construction range p >= 0.0001. ``lower_diagnostic`` is the half-open
interval [0.0001, 0.0005); ``rare`` is p < 0.0001. Old query points that become
dense knots are explicitly both roles, not mislabeled as new held-out probes.
    """
    if isinstance(probability, bool):
        raise ValueError("probability must be one of the frozen ALL_P values")
    try:
        p = float(probability)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("probability must be one of the frozen ALL_P values") from error
    if not math.isfinite(p) or p not in ALL_P:
        raise ValueError("probability must be one of the frozen ALL_P values")
    return {
        "p": p,
        "coarse_knot": p in COARSE_P,
        "dense_knot": p in DENSE_P,
        "new_probe": p in NEW_PROBE_P,
        "old_query": p in OLD_QUERY_P,
        "old_probe": p in OLD_PROBE_P,
        "moderate": p >= 0.0005,
        "lower_diagnostic": 0.0001 <= p < 0.0005,
        "rare": p < 0.0001,
        "primary": p in PRIMARY_P,
    }


def grid_manifest():
    """Return a fresh, JSON-safe declaration of every grid and overlapping role."""
    return {
        "schema": "sjaracne-apmi-p-axis-refinement-grid-v1",
        "coarse_p": list(COARSE_P),
        "dense_p": list(DENSE_P),
        "new_probe_p": list(NEW_PROBE_P),
        "old_probe_p": list(OLD_PROBE_P),
        "old_query_p": list(OLD_QUERY_P),
        "all_p": list(ALL_P),
        "grid_m": list(GRIDM),
        "primary_p": list(PRIMARY_P),
        "smoothers": list(SMOOTHERS),
        "new_probe_rule": "geometric midpoint of adjacent dense knots >= 0.0001; "
                          "rounded to 14 significant decimal digits, ROUND_HALF_EVEN",
        "roles": [dict(probability_roles(float(p)), decimal_p=str(p)) for p in _ALL_DECIMAL],
    }
