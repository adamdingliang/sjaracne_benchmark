"""Fixed-universe, tie-aware raw-MI scores. No inference or reference changes.

The native writer omits computed MI=0. A complete source-row traversal at
p=1, threshold=0 and DPI tolerance=1 permits those omissions to join the zero
tie. The caller MUST additionally verify successful process completion and its
log/checkpoint; a syntactically complete .adj alone is not proof of execution.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np


DEFAULT_KS = (1000, 5000, 10000, 50000, 100000)


def _rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream, delimiter="\t")


def _unique(values, label):
    values = tuple(values)
    if not values or any(not value for value in values) or len(set(values)) != len(values):
        raise ValueError(f"Empty or duplicate {label}")
    return values


@dataclass
class Universe:
    sources: tuple[str, ...]
    targets: tuple[str, ...]
    labels: np.ndarray
    definition: dict
    source_ids: dict = field(init=False, repr=False)
    target_ids: dict = field(init=False, repr=False)

    def __post_init__(self):
        self.sources = _unique(self.sources, "sources")
        self.targets = _unique(self.targets, "targets")
        if not set(self.sources) <= set(self.targets):
            raise ValueError("Every eligible source must also be a target")
        self.source_ids = {value: i for i, value in enumerate(self.sources)}
        self.target_ids = {value: i for i, value in enumerate(self.targets)}
        self.labels = np.asarray(self.labels, dtype=bool)
        if self.labels.ndim != 1 or len(self.labels) != self.size:
            raise ValueError("Incorrect fixed-universe label shape")

    @property
    def size(self):
        return len(self.sources) * (len(self.targets) - 1)

    @property
    def P(self):
        return int(np.count_nonzero(self.labels))

    @property
    def N(self):
        return self.size - self.P

    @property
    def definition_sha256(self):
        return self.definition["definition_sha256"]

    def pair_index(self, source, target):
        if source == target:
            raise ValueError("Self-pair outside scoring universe")
        try:
            source_id = self.source_ids[source]
            target_id = self.target_ids[target]
            self_id = self.target_ids[source]
        except KeyError as exc:
            raise ValueError("Pair outside scoring universe") from exc
        return source_id * (len(self.targets) - 1) + target_id - (target_id > self_id)


def load_universe(prepared_dir):
    """Reconstruct exactly the existing canonical eligible-source universe."""
    prepared_dir = Path(prepared_dir)
    genes = list(_rows(prepared_dir / "gene_selection.tsv"))
    raw = _unique((row["gene"] for row in genes), "raw genes")
    raw_ids = {value: i for i, value in enumerate(raw)}
    targets = _unique((row["gene"] for row in genes if row["used_for_network"] == "TRUE"), "targets")
    eligible = _unique((row["source"] for row in _rows(prepared_dir / "reference_eligible_sources.tsv")), "eligible sources")
    hubs = _unique((prepared_dir / "hubs.txt").read_text(encoding="utf-8").splitlines(), "hubs")
    strict = {row["gene"] for row in genes if row["strict_SIG_reference_annotation"] == "TRUE"}
    if not set(hubs) <= set(targets) or not set(eligible) <= strict:
        raise ValueError("Hubs or eligible sources violate frozen annotations")
    sources = tuple(sorted(set(eligible) & set(hubs) & set(targets)))
    if not sources:
        raise ValueError("No eligible inference sources")
    source_ids = {value: i for i, value in enumerate(sources)}
    target_ids = {value: i for i, value in enumerate(targets)}
    labels = np.zeros(len(sources) * (len(targets) - 1), dtype=bool)
    seen = set()
    excluded = {"source_not_eligible_inference_hub": 0, "target_not_inference_gene": 0, "self_pair": 0}
    for row in _rows(prepared_dir / "reference_positive_edges.tsv"):
        source, target = row["source"], row["target"]
        if source not in raw_ids or target not in raw_ids:
            raise ValueError("Reference identifier absent from frozen gene panel")
        key = raw_ids[source] * len(raw_ids) + raw_ids[target]
        if key in seen:
            raise ValueError("Duplicate reference pair")
        seen.add(key)
        reason = ("source_not_eligible_inference_hub" if source not in source_ids else
                  "target_not_inference_gene" if target not in target_ids else
                  "self_pair" if source == target else None)
        if reason:
            excluded[reason] += 1
            continue
        ti, si = target_ids[target], target_ids[source]
        labels[source_ids[source] * (len(targets) - 1) + ti - (ti > si)] = True
    size, positive = len(labels), int(labels.sum())
    if not 0 < positive < size:
        raise ValueError("Raw-MI scoring requires both reference classes")
    definition = {
        "sources": list(sources), "targets": list(targets),
        "n_sources": len(sources), "n_targets": len(targets),
        "self_pairs_excluded": len(sources), "candidate_pairs": size,
        "reference_positive_pairs": positive, "reference_negative_pairs": size - positive,
        "positive_prevalence": positive / size,
        "full_prepared_reference_positive_pairs": len(seen), "excluded_reference_pairs": excluded,
    }
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    definition["definition_sha256"] = hashlib.sha256(canonical).hexdigest()
    return Universe(sources, targets, labels, definition)


def _normalized_path(value):
    value = str(value).replace("\\", "/")
    if re.match(r"^/mnt/[A-Za-z]/", value):
        value = value[5].lower() + ":" + value[6:]
    if re.match(r"^[A-Za-z]:/", value):
        value = value[0].lower() + value[1:]
    return value.rstrip("/")


_HEADERS = ("Input file", "MI threshold", "MI P-value", "DPI tolerance", "Subnetwork file",
            "Sampling method", "Sampling request", "Eligible observations", "Sampled observations")


def parse_adjacency(path, universe, expected_sources=None, expected_subnetwork=None, arm=None):
    """Validate native zero-suppressed output; caller verifies process completion.

    Every requested source row must occur exactly once, even if entirely zero.
    Non-eligible rows from a full-SIG traversal are validated but not scored.
    Header checks cannot detect a missing final target/value pair if the writer
    were interrupted immediately at a line boundary; external completion proof
    is therefore mandatory before calling this parser on real runs.
    """
    expected = _unique(universe.sources if expected_sources is None else expected_sources, "expected sources")
    expected_set = set(expected)
    if not set(universe.sources) <= expected_set or not expected_set <= set(universe.targets):
        raise ValueError("Expected sources do not cover eligible sources or contain unknown genes")
    scores = np.zeros(universe.size, dtype=np.float64)
    seen_rows, headers = set(), {}
    data_started = False
    emitted = eligible_emitted = 0
    path = Path(path)
    with path.open("rb") as stream:
        stream.seek(0, 2)
        if not stream.tell():
            raise ValueError("Empty adjacency file")
        stream.seek(-1, 2)
        if stream.read(1) != b"\n":
            raise ValueError("Adjacency missing final newline")
    with path.open(encoding="utf-8", newline="") as stream:
        for line_number, line in enumerate(stream, 1):
            line = line.rstrip("\r\n")
            if not line:
                raise ValueError(f"Empty adjacency line {line_number}")
            if line.startswith(">"):
                if data_started:
                    raise ValueError("Header after adjacency rows")
                body = line[1:].strip()
                matching = [key for key in _HEADERS if body.startswith(key + " ")]
                if len(matching) != 1:
                    raise ValueError(f"Unknown adjacency header: {body}")
                key = matching[0]
                if key in headers:
                    raise ValueError(f"Duplicate header: {key}")
                headers[key] = body[len(key):].strip()
                continue
            data_started = True
            fields = line.split("\t")
            source = fields[0]
            if source not in expected_set or source in seen_rows:
                raise ValueError("Unknown or duplicate source row")
            seen_rows.add(source)
            if len(fields) % 2 != 1:
                raise ValueError("Malformed target/MI fields")
            seen_targets = set()
            is_eligible = source in universe.source_ids
            for offset in range(1, len(fields), 2):
                target = fields[offset]
                if target not in universe.target_ids or target == source or target in seen_targets:
                    raise ValueError("Unknown, annotated, self or duplicate target")
                seen_targets.add(target)
                try:
                    value = float(fields[offset + 1])
                except ValueError as exc:
                    raise ValueError("Invalid MI token") from exc
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Nonfinite or negative MI")
                emitted += 1
                if is_eligible:
                    scores[universe.pair_index(source, target)] = value
                    eligible_emitted += 1
    if seen_rows != expected_set:
        raise ValueError("Missing expected source rows; cannot infer zero MI")
    if not set(_HEADERS[:5]) <= headers.keys():
        raise ValueError("Missing required native headers")
    for key, expected_value in (("MI threshold", 0.0), ("MI P-value", 1.0), ("DPI tolerance", 1.0)):
        try:
            actual = float(headers[key])
        except ValueError as exc:
            raise ValueError(f"Invalid header {key}") from exc
        if actual != expected_value:
            raise ValueError(f"Raw-MI requires {key}={expected_value:g}")
    if expected_subnetwork is not None and _normalized_path(headers["Subnetwork file"]) != _normalized_path(expected_subnetwork):
        raise ValueError("Subnetwork header differs from expected input")
    if arm in ("before", "legacy", "baseline"):
        if any(key in headers for key in _HEADERS[5:]):
            raise ValueError("Unexpected sampling-only headers in baseline")
    elif arm in ("after", "sampling", "sampling_after"):
        expected_sampling = {"Sampling method": "fixed-size without replacement", "Sampling request": "80%",
                             "Eligible observations": "121", "Sampled observations": "97"}
        if any(headers.get(key) != value for key, value in expected_sampling.items()):
            raise ValueError("Sampling-only headers differ from frozen 80% protocol")
    elif arm is not None:
        raise ValueError("Unknown sampling arm")
    return scores, {
        "status": "complete_syntax_requires_external_execution_proof", "headers": headers,
        "source_rows": len(seen_rows), "expected_source_rows": len(expected),
        "emitted_pairs": emitted, "eligible_emitted_pairs": eligible_emitted,
        "eligible_zero_MI_pairs": int(np.count_nonzero(scores == 0)),
        "eligible_zero_suppressed_pairs": universe.size - eligible_emitted,
        "zero_policy": "Absent pairs within verified complete rows have native MI=0; caller verifies successful process completion",
        "candidate_pairs": universe.size,
    }


def score_arrays(scores, labels, ks=DEFAULT_KS, curve_ks=None):
    """Rank all pairs, retain exact MI ties, and sample curves on a fixed k-grid."""
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=bool)
    if scores.ndim != 1 or labels.shape != scores.shape or not len(scores):
        raise ValueError("Scores and labels require equal nonempty vector shape")
    if not np.all(np.isfinite(scores)) or np.any(scores < 0):
        raise ValueError("Scores must be finite nonnegative native MI")
    total = len(scores)
    positive = int(labels.sum())
    negative = total - positive
    if not positive or not negative:
        raise ValueError("Both reference classes required")
    order = np.argsort(-scores, kind="stable")
    ordered = scores[order]
    starts = np.r_[0, np.flatnonzero(ordered[1:] != ordered[:-1]) + 1]
    sizes = np.diff(np.r_[starts, total]).astype(np.int64)
    gp = np.add.reduceat(labels[order].astype(np.int64), starts)
    gn = sizes - gp
    cp, cn, counts = np.cumsum(gp), np.cumsum(gn), np.cumsum(sizes)
    # Int64 safe for this fixed <5M-pair universe (products below 5e13).
    twice_wins = int(np.sum(gp * (2 * (negative - cn) + gn), dtype=np.int64))
    auc = twice_wins / (2 * positive * negative)
    # Independent geometric trapezoidal ROC calculation, all score groups.
    roc_tp = np.r_[0, cp].astype(float) / positive
    roc_fp = np.r_[0, cn].astype(float) / negative
    integrated = float(np.sum((roc_tp[1:] + roc_tp[:-1]) * np.diff(roc_fp) / 2))
    if not math.isclose(auc, integrated, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Pairwise and trapezoidal AUROC disagree")
    prevalence = positive / total

    def point(k):
        if isinstance(k, (bool, np.bool_)) or not isinstance(k, (int, np.integer)) or not 0 <= k <= total:
            raise ValueError("k must be an integer in [0, candidate_pairs]")
        k = int(k)
        if not k:
            return {"k": 0, "TP_tie_expected": 0.0, "TP_min": 0, "TP_max": 0,
                    "FP_tie_expected": 0.0, "precision_tie_expected": None,
                    "sensitivity_tie_expected": 0.0, "specificity_tie_expected": 1.0,
                    "FPR_tie_expected": 0.0, "random_TP_expectation_at_k": 0.0,
                    "EPR_tie_expected": None, "boundary_MI": None,
                    "boundary_group_size": 0, "split_MI_tie": False}
        group = int(np.searchsorted(counts, k, side="left"))
        before = int(counts[group - 1]) if group else 0
        tp_before = int(cp[group - 1]) if group else 0
        take = k - before
        p, n, size = int(gp[group]), int(gn[group]), int(sizes[group])
        tp = tp_before + take * p / size
        fp = k - tp
        precision = tp / k
        return {"k": k, "TP_tie_expected": tp,
                "TP_min": tp_before + max(0, take - n), "TP_max": tp_before + min(take, p),
                "FP_tie_expected": fp, "precision_tie_expected": precision,
                "sensitivity_tie_expected": tp / positive,
                "specificity_tie_expected": 1 - fp / negative, "FPR_tie_expected": fp / negative,
                "random_TP_expectation_at_k": k * prevalence, "EPR_tie_expected": precision / prevalence,
                "boundary_MI": float(ordered[starts[group]]), "boundary_group_size": size,
                "split_MI_tie": take < size}

    ks = tuple(ks)
    if len(set(ks)) != len(ks) or any(k <= 0 for k in ks):
        raise ValueError("Prespecified k must be distinct positive integers")
    top = [point(k) for k in ks]
    if curve_ks is None:
        grid = np.unique(np.r_[0, np.linspace(0, total, 1001, dtype=np.int64),
                               np.arange(1000, min(total, 100000) + 1, 1000), ks, total])
    else:
        grid = sorted(set([0, total, *curve_ks, *ks]))
    curve = [point(k) for k in grid]
    fpr_grid = np.linspace(0.0, 1.0, 1001)
    # np.interp takes the last point at duplicate FPR, i.e. the upper endpoint
    # of vertical ROC segments; no rank ordering is introduced inside MI ties.
    tpr_grid = np.interp(fpr_grid, roc_fp, roc_tp)
    return {
        "status": "complete", "candidate_pairs": total, "reference_positive_pairs": positive,
        "reference_negative_pairs": negative, "random_positive_fraction": prevalence,
        "AUROC_MI_ties": auc, "AUROC_ROC_integral_check": integrated,
        "distinct_MI_groups": len(starts), "zero_MI_pairs": int(np.count_nonzero(scores == 0)),
        "top_k": top, "curve": curve,
        "roc_curve": {"FPR": fpr_grid.tolist(), "sensitivity": tpr_grid.tolist(),
                      "interpolation": "Linear between complete MI-tie groups; upper endpoint at vertical segments; plot only, not AUROC calculation"},
        "definitions": {"reference": "Frozen perturbation-response positives; nonmembers are operational negatives, not proven biological negatives",
                        "rank": "Descending raw native MI over the same complete eligible universe",
                        "ties": "Exact serialized MI ties; top-k expected under uniform boundary-tie ordering, plus attainable TP range",
                        "EPR": "Precision divided by fixed-universe reference-positive prevalence",
                        "AUROC": "Positive-negative ranking probability, half credit for equal MI; no omitted bottom group",
                        "curve": "Sampled common-rank curve; AUROC uses ALL distinct MI groups, not the sampled plot"},
    }
