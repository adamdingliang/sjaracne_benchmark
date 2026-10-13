"""Auditable ranking metrics for the THP-1 perturbation-response benchmark.

NumPy is the only non-standard dependency. No biological reference labels are
created here: callers must supply an explicit, fixed candidate-pair universe.
The primary scores assign zero to unreported pairs; reported-only scores answer
the narrower question of ranking within the already inferred network.

AUROC and average precision group equal scores. Top-k curves necessarily split
ties when k falls inside a score group; those positions are explicitly flagged.
The shuffled EPR baseline is one permutation of the same scored pair list,
not a different random network. ``epr_expected`` uses its exact expected
precision, avoiding single-shuffle denominator noise.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Optional

import numpy as np


Pair = tuple[str, str]


def adjacency(path: str | Path) -> dict[Pair, float]:
    """Read native SJARACNe .adj data, rejecting malformed or duplicate edges.

    Lines beginning with ``>`` are provenance headers. Empty source rows are
    allowed. Scores must be finite and nonnegative; repeated source rows and
    repeated source-target pairs are errors, even when their scores agree.
    """
    edges: dict[Pair, float] = {}
    sources: set[str] = set()
    with Path(path).open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            text = line.rstrip("\r\n")
            if not text.strip() or text.lstrip().startswith(">"):
                continue
            fields = text.split("\t")
            source = fields[0]
            if not source or source != source.strip():
                raise ValueError(f"{path}:{line_number}: invalid source identifier")
            if source in sources:
                raise ValueError(f"{path}:{line_number}: duplicate source row {source!r}")
            sources.add(source)
            if len(fields) % 2 != 1:
                raise ValueError(f"{path}:{line_number}: expected target/MI field pairs")
            for index in range(1, len(fields), 2):
                target = fields[index]
                if not target or target != target.strip():
                    raise ValueError(f"{path}:{line_number}: invalid target identifier")
                pair = (source, target)
                if pair in edges:
                    raise ValueError(f"{path}:{line_number}: duplicate edge {pair!r}")
                try:
                    score = float(fields[index + 1])
                except ValueError as error:
                    raise ValueError(f"{path}:{line_number}: invalid MI for {pair!r}") from error
                if not np.isfinite(score) or score < 0:
                    raise ValueError(f"{path}:{line_number}: MI must be finite and nonnegative")
                edges[pair] = score
    return edges


def _arrays(scores: Iterable[float], labels: Iterable[bool]) -> tuple[np.ndarray, np.ndarray]:
    # Materialize generators, but avoid copying existing million-pair arrays.
    values = np.asarray(scores if isinstance(scores, (np.ndarray, list, tuple)) else list(scores),
                        dtype=np.float64)
    truth = np.asarray(labels if isinstance(labels, (np.ndarray, list, tuple)) else list(labels))
    if values.ndim != 1 or truth.ndim != 1 or values.size != truth.size:
        raise ValueError("scores and labels must be equally sized one-dimensional sequences")
    if truth.size and truth.dtype.kind != "b":
        raise ValueError("labels must be explicit booleans, not numeric or missing values")
    truth = truth.astype(np.bool_, copy=False)
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError("scores must be finite and nonnegative")
    return values, truth


def _grouped(values: np.ndarray, truth: np.ndarray):
    order = np.argsort(-values, kind="stable")
    sorted_values = values[order]
    if not values.size:
        return order, np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    ends = np.r_[np.flatnonzero(sorted_values[:-1] != sorted_values[1:]), values.size - 1]
    cumulative_tp = np.cumsum(truth[order], dtype=np.int64)
    return order, ends, cumulative_tp[ends]


def ranking_metrics(scores: Iterable[float], labels: Iterable[bool]) -> tuple[Optional[float], Optional[float]]:
    """Return tie-aware (AUROC, stepwise average precision).

    AUROC is undefined (None) without both classes. Average precision is None
    without positives; with positives but no negatives it is exactly one.
    The AP convention is grouped-threshold precision weighted by recall gain,
    not trapezoidal precision-recall area.
    """
    values, truth = _arrays(scores, labels)
    _, ends, tp = _grouped(values, truth)
    positives = int(truth.sum())
    negatives = truth.size - positives
    if not positives:
        return None, None
    recall = tp / positives
    precision = tp / (ends + 1)
    average_precision = float(np.sum(np.diff(np.r_[0.0, recall]) * precision))
    if not negatives:
        return None, average_precision
    fpr = np.r_[0.0, (ends + 1 - tp) / negatives]
    tpr = np.r_[0.0, recall]
    # Works with NumPy 1.26 and 2.x; do not rely on np.trapezoid availability.
    auroc = float(np.sum(np.diff(fpr) * (tpr[:-1] + tpr[1:]) / 2.0))
    return auroc, average_precision


def roc_curve(scores: Iterable[float], labels: Iterable[bool]) -> dict:
    """Return grouped-tie ROC coordinates including the empty-selection point.

    The first threshold is None (select no pairs), not non-JSON infinity.
    Undefined FPR/TPR entries are None when the relevant class is absent.
    """
    values, truth = _arrays(scores, labels)
    order, ends, tp = _grouped(values, truth)
    positives = int(truth.sum())
    negatives = truth.size - positives
    points = ends.size + 1
    return {
        "thresholds": [None] + values[order][ends].tolist(),
        "selected": [0] + (ends + 1).tolist(),
        "tp": [0] + tp.tolist(),
        "fp": [0] + (ends + 1 - tp).tolist(),
        "fpr": np.r_[0.0, (ends + 1 - tp) / negatives].tolist() if negatives else [None] * points,
        "tpr": np.r_[0.0, tp / positives].tolist() if positives else [None] * points,
    }


def ranked_curve(scores: Iterable[float], labels: Iterable[bool], k_values: Iterable[int],
                 random_seed: int = 1) -> dict:
    """Return cumulative TP, precision, EPR, FPR and TPR at requested top-k.

    k must be unique, increasing integers in [1, N]. Equal MI values preserve
    input order; use a fixed candidate-pair order between arms. EPR is None
    when its denominator is zero. The shuffled baseline is a single seeded
    permutation, as in the author code conceptually; NumPy's generator is not
    claimed to reproduce R's particular random permutation.
    """
    values, truth = _arrays(scores, labels)
    requested = list(k_values)
    if any(isinstance(k, (bool, np.bool_)) or not isinstance(k, (int, np.integer))
           for k in requested):
        raise ValueError("k_values must contain integers")
    if any(k < 1 or k > values.size for k in requested):
        raise ValueError("k_values must be within [1, number of pairs]")
    if any(a >= b for a, b in zip(requested, requested[1:])):
        raise ValueError("k_values must be unique and increasing")
    if isinstance(random_seed, bool) or not isinstance(random_seed, (int, np.integer)) or random_seed < 0:
        raise ValueError("random_seed must be a nonnegative integer")
    order = np.argsort(-values, kind="stable")
    shuffled_order = np.random.default_rng(int(random_seed)).permutation(order)
    positions = np.asarray(requested, dtype=np.int64) - 1
    tp = np.cumsum(truth[order], dtype=np.int64)[positions]
    tp_random = np.cumsum(truth[shuffled_order], dtype=np.int64)[positions]
    positives = int(truth.sum())
    negatives = truth.size - positives
    expected = positives / truth.size if truth.size else None
    precision = [int(count) / int(k) for k, count in zip(requested, tp)]
    sorted_scores = values[order]
    return {
        "k": [int(k) for k in requested],
        "tp": tp.tolist(),
        "precision": precision,
        "tp_random": tp_random.tolist(),
        "precision_random": [int(count) / int(k) for k, count in zip(requested, tp_random)],
        "epr_shuffle": [int(a) / int(b) if b else None for a, b in zip(tp, tp_random)],
        "expected_random_precision": expected,
        "epr_expected": [p / expected if expected else None for p in precision],
        "fpr": [(int(k) - int(count)) / negatives if negatives else None
                for k, count in zip(requested, tp)],
        "tpr": [int(count) / positives if positives else None for count in tp],
        "split_tie": [bool(k < values.size and sorted_scores[k - 1] == sorted_scores[k])
                      for k in requested],
        "random_seed": int(random_seed),
        "random_baseline": "one shuffled ordering of the same pair list",
    }


def _summary(values: np.ndarray, truth: np.ndarray) -> dict:
    auroc, average_precision = ranking_metrics(values, truth)
    return {
        "pairs": int(truth.size),
        "positives": int(truth.sum()),
        "negatives": int(truth.size - truth.sum()),
        "random_precision": float(truth.mean()) if truth.size else None,
        "auroc": auroc,
        "average_precision": average_precision,
    }


def evaluate(edges: Mapping[Pair, float], reference_labels: Mapping[Pair, bool]) -> dict:
    """Score both a common candidate universe and the reported-only edge pool.

    Unknown output pairs are errors: explicitly filter out-of-scope sources or
    targets before calling, and record that filtering in the runner provenance.
    Pair order is lexicographic for reproducibility. The common-universe binary
    operating point selects every reported edge, including a reported zero-MI
    edge, while its ranking assigns missing pairs score zero.
    """
    unknown = edges.keys() - reference_labels.keys()
    if unknown:
        example = min(unknown)
        raise ValueError(f"{len(unknown)} output pairs are outside the reference universe; example {example!r}")
    pairs = sorted(reference_labels)
    values, truth = _arrays([edges.get(pair, 0.0) for pair in pairs],
                            [reference_labels[pair] for pair in pairs])
    selected = np.fromiter((pair in edges for pair in pairs), dtype=np.bool_, count=len(pairs))
    all_candidate = _summary(values, truth)
    tp = int(np.count_nonzero(selected & truth))
    fp = int(np.count_nonzero(selected & ~truth))
    fn = int(np.count_nonzero(~selected & truth))
    tn = int(np.count_nonzero(~selected & ~truth))
    all_candidate.update({
        "missing_edge_score": 0.0,
        "reported_pairs": int(selected.sum()),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "sensitivity": tp / (tp + fn) if tp + fn else None,
        "specificity": tn / (tn + fp) if tn + fp else None,
        "fpr": fp / (tn + fp) if tn + fp else None,
    })
    return {
        "all_candidates": all_candidate,
        "reported_only": _summary(values[selected], truth[selected]),
        "reported_fraction": float(selected.mean()) if selected.size else None,
    }
