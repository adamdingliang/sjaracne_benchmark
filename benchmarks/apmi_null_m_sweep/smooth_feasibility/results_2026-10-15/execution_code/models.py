"""Deterministic smoothing candidates for an exploratory AP-MI calibration audit.

These functions have no file access, random draws, fitting-stream access, or model
selection. Callers must supply only their current training fold. The independent
columns of ``train_quantiles`` correspond to the caller's fixed p grid; a separate
``interpolate_probability`` function interpolates those knots. No function
repairs p or m monotonicity.

``loglinear`` and ``logquadratic`` are global least-squares polynomials in log m.
``pchip`` interpolates in log m with extrapolation disabled. Its out-of-range
predictions are NaN; polynomial extrapolation is allowed but must be labeled by
the caller. No prediction is clipped to the physical MI domain.
"""

from collections.abc import Mapping

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.special import expit, logit


METHODS = ("loglinear", "logquadratic", "pchip")
PARAMETER_NAMES = ("u", "scale", "shape", "tail_probability")


def _sample_sizes(values, name):
    array = np.asarray(values, dtype=float)
    if array.ndim > 1 or not np.all(np.isfinite(array)) or np.any(array <= 1):
        raise ValueError(f"{name} must be finite scalar/vector sizes greater than 1")
    return array


def _prepare(train_m, train_values, test_m, method):
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}")
    train = _sample_sizes(train_m, "train_m")
    test = _sample_sizes(test_m, "test_m")
    if train.ndim != 1:
        raise ValueError("train_m must be a vector")
    required = 3 if method == "logquadratic" else 2
    if train.size < required:
        raise ValueError(f"{method} requires at least {required} training sizes")
    order = np.argsort(train, kind="stable")
    train = train[order]
    if np.any(np.diff(train) == 0):
        raise ValueError("train_m must contain distinct sizes")
    values = np.asarray(train_values, dtype=float)
    if values.ndim != 2 or values.shape[0] != train.size or values.shape[1] == 0:
        raise ValueError("train_values must have shape (n_training_sizes, n_columns)")
    if not np.all(np.isfinite(values)):
        raise ValueError("training values must be finite")
    return np.log(train), values[order], np.log(test)


def _smooth(train_m, transformed_values, test_m, method):
    x, y, x_test = _prepare(train_m, transformed_values, test_m, method)
    if method == "pchip":
        return np.asarray(PchipInterpolator(x, y, axis=0, extrapolate=False)(x_test))
    degree = 1 if method == "loglinear" else 2
    coefficients = np.polynomial.polynomial.polyfit(x, y, degree)
    # numpy's polyval orders output as (n_columns, n_test); transpose restores
    # the common scalar->(n_columns,), vector->(n_test,n_columns) interface.
    return np.polynomial.polynomial.polyval(x_test, coefficients).T


def predict_quantiles(train_m, train_quantiles, test_m, method="loglinear"):
    """Predict positive cutoffs at a supplied, unchanged p grid.

    Inputs are n training m values and an (n, n_p) positive cutoff array. A scalar
    test_m produces shape (n_p,); a vector produces shape (n_test, n_p). Zero
    training cutoffs cannot be log-smoothed and raise rather than being shifted.
    Any nonfinite/out-of-MI-support predictions must be rejected by the caller.
    """
    quantiles = np.asarray(train_quantiles, dtype=float)
    if not np.all(np.isfinite(quantiles)) or np.any(quantiles <= 0):
        raise ValueError("train_quantiles must be finite and strictly positive")
    with np.errstate(over="ignore", invalid="ignore"):
        return np.exp(_smooth(train_m, np.log(quantiles), test_m, method))


def interpolate_probability(p_knots, cutoff_knots, query_p):
    """PCHIP-interpolate log cutoff versus log p, with no extrapolation.

    ``cutoff_knots`` has shape (..., n_p); its last axis aligns with p_knots.
    A scalar query returns shape (...,), a vector returns (..., n_query).
    Inputs are deterministically sorted by p. Cutoffs must be positive and
    nonincreasing as p increases; failures raise rather than being repaired.
    This is interpolation only: evaluate null rates at p values not used as
    knots to check its quality. This function has no m input and does not check
    the physical MI upper bound; callers must do so for each evaluated m.
    """
    knots = np.asarray(p_knots, dtype=float)
    values = np.asarray(cutoff_knots, dtype=float)
    queries = np.asarray(query_p, dtype=float)
    if (knots.ndim != 1 or knots.size < 2 or not np.all(np.isfinite(knots))
            or np.any(knots <= 0) or np.any(knots >= 1)):
        raise ValueError("p_knots must be a finite vector of at least two probabilities in (0,1)")
    if values.ndim == 0 or values.shape[-1] != knots.size:
        raise ValueError("cutoff_knots last axis must align with p_knots")
    if not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("cutoff_knots must be finite and strictly positive")
    if queries.ndim > 1 or not np.all(np.isfinite(queries)):
        raise ValueError("query_p must be a finite scalar or vector")
    order = np.argsort(knots, kind="stable")
    knots, values = knots[order], values[..., order]
    if np.any(np.diff(knots) == 0):
        raise ValueError("p_knots must be distinct")
    if np.any(np.diff(values, axis=-1) > 0):
        raise ValueError("cutoff_knots must be nonincreasing as p increases; no repair is applied")
    if np.any(queries < knots[0]) or np.any(queries > knots[-1]):
        raise ValueError("query_p lies outside the p knot range; extrapolation is disabled")
    interpolator = PchipInterpolator(np.log(knots), np.log(values), axis=-1, extrapolate=False)
    return np.exp(interpolator(np.log(queries)))


def predict_gpd_parameters(train_m, train_parameters, test_m, method="loglinear"):
    """Smooth an existing GPD parameter map without fitting a GPD anew.

    Required keys are u, scale, shape, tail_probability; each value is a vector
    aligned to train_m. Positive u/scale are log-transformed, shape is unchanged,
    and tail_probability in (0,1) is logit-transformed. Scalar test_m returns a
    dictionary of floats; vector test_m returns a dictionary of 1-D arrays.
    Predictions are not clipped: evaluate with gpd_cutoff to check validity.
    """
    if not isinstance(train_parameters, Mapping):
        raise ValueError("train_parameters must be a mapping")
    missing = set(PARAMETER_NAMES).difference(train_parameters)
    if missing:
        raise ValueError(f"missing GPD parameters: {sorted(missing)}")
    arrays = [np.asarray(train_parameters[name], dtype=float) for name in PARAMETER_NAMES]
    sizes = _sample_sizes(train_m, "train_m")
    if sizes.ndim != 1 or any(array.shape != sizes.shape for array in arrays):
        raise ValueError("each GPD parameter must be a vector aligned to train_m")
    if not all(np.all(np.isfinite(array)) for array in arrays):
        raise ValueError("training GPD parameters must be finite")
    u, scale, shape, tail = arrays
    if np.any(u <= 0) or np.any(u > np.log(sizes)):
        raise ValueError("training u must satisfy 0 < u <= log(m)")
    if np.any(scale <= 0):
        raise ValueError("training scale must be positive")
    if np.any(tail <= 0) or np.any(tail >= 1):
        raise ValueError("training tail_probability must lie strictly between 0 and 1")
    transformed = np.column_stack((np.log(u), np.log(scale), shape, logit(tail)))
    prediction = _smooth(train_m, transformed, test_m, method)
    with np.errstate(over="ignore", invalid="ignore"):
        values = (np.exp(prediction[..., 0]), np.exp(prediction[..., 1]),
                  prediction[..., 2], expit(prediction[..., 3]))
    if np.asarray(test_m).ndim == 0:
        return {name: float(value) for name, value in zip(PARAMETER_NAMES, values)}
    return dict(zip(PARAMETER_NAMES, values))


def gpd_cutoff(u, scale, shape, tail_probability, p, m):
    """Evaluate a GPD upper-tail MI cutoff, with strict validity checks.

    P(MI > u) is tail_probability. The target p must be in (0,tail_probability].
    Inputs broadcast; a scalar input set returns float, otherwise an ndarray.
    Any invalid element raises ValueError with a reason, so callers wanting
    per-point invalid reasons should call this function pointwise. Floating-point
    overflow, collapsed negative-shape support, and cutoffs outside [0,log(m)]
    are failures, never repaired. Shape zero uses the exponential-tail limit.
    """
    try:
        u, scale, shape, tail, p, m = np.broadcast_arrays(
            *[np.asarray(value, dtype=float)
              for value in (u, scale, shape, tail_probability, p, m)])
    except ValueError as error:
        raise ValueError("GPD inputs must be numeric and broadcast-compatible") from error
    if not all(np.all(np.isfinite(value)) for value in (u, scale, shape, tail, p, m)):
        raise ValueError("GPD inputs must be finite")
    if np.any(m <= 1):
        raise ValueError("m must be greater than 1")
    if np.any(scale <= 0):
        raise ValueError("scale must be positive")
    if np.any(tail <= 0) or np.any(tail >= 1):
        raise ValueError("tail_probability must lie strictly between 0 and 1")
    if np.any(p <= 0) or np.any(p > tail):
        raise ValueError("p must satisfy 0 < p <= tail_probability")
    if np.any(u < 0) or np.any(u > np.log(m)):
        raise ValueError("u must lie within MI support [0, log(m)]")
    # Difference of logs avoids overflow in tail/p. expm1 avoids cancellation
    # near shape zero; the exact shape-zero case is evaluated separately.
    log_ratio = np.log(tail) - np.log(p)
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        excess = np.array(log_ratio, copy=True)
        np.divide(np.expm1(shape * log_ratio), shape, out=excess, where=shape != 0)
        cutoff = u + scale * excess
        standardized_support = 1 + shape * excess
    if not np.all(np.isfinite(cutoff)):
        raise ValueError("GPD cutoff is not finite")
    if np.any(standardized_support <= 0):
        raise ValueError("GPD cutoff reaches or exceeds the finite tail endpoint")
    if np.any(cutoff < 0) or np.any(cutoff > np.log(m)):
        raise ValueError("GPD cutoff lies outside MI support [0, log(m)]")
    return float(cutoff) if cutoff.ndim == 0 else cutoff
