#!/usr/bin/env python3
"""Independent, small-data native DPI differential validation.

No SJARACNe Python modules or test helpers are imported. The baseline is the
unmodified current-develop binary, built with the same compiler as the candidate.
All input fixtures, commands, stdout/stderr, and machine-readable results remain
under a newly created --output-dir. This is a diagnostic compatibility check,
not biological validation, cutoff calibration, or a bootstrap benchmark.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


EPSILONS = (0.0, 0.05, 0.15, 0.9)
LEVELS = (1, 2, 3, 5, 10)
STAT_RE = re.compile(
    r"^\[DPI_STATS\] pre_edges=(\d+) pruned_edges=(\d+) "
    r"post_edges=(\d+) dpi_applied=([01])$", re.MULTILINE
)


@dataclass
class Case:
    name: str
    n: int
    graph: dict | None
    epsilon: float = 0.0
    selected: list | None = None
    annotated: list = field(default_factory=list)
    threshold: float = 0.0
    probability: str = "1"
    model: str | None = None
    seed: int = 1701
    subsample: str | None = None
    inferred: bool = False


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gene(index):
    return chr(65 + index) if index < 26 else "G" + str(index)


def write_expression(path, n, observations, seed):
    rng = random.Random(seed)
    # Related and unrelated rows ensure that thresholded inference is nonempty
    # without requiring thousands of probes or scientific-scale replicates.
    bases = [[rng.gauss(0, 1) for _ in range(observations)] for _ in range(3)]
    lines = ["isoformId\tgeneSymbol\t" + "\t".join(
        "s" + str(i) for i in range(observations))]
    for row in range(n):
        values = [10 + 2 * bases[row % 3][i] +
                  (0.03 if row < 6 else 1.3) * rng.gauss(0, 1)
                  for i in range(observations)]
        lines.append("\t".join([gene(row), gene(row)] +
                               [format(value, ".15g") for value in values]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def replay_cases(random_count):
    cases = []
    triangle = {0: {1: 0.2, 2: 0.8}, 1: {0: 0.2, 2: 0.7},
                2: {0: 0.8, 1: 0.7}}
    for mask in range(8):
        for eps in EPSILONS:
            cases.append(Case("annotation_%03d_e%s" % (mask, eps), 3,
                              triangle, eps, annotated=[i for i in range(3)
                                                       if mask & (1 << i)]))
    rng = random.Random(276721)
    full = {i: {j: rng.choice((0.1, 0.25, 0.5, 0.75, 1.0))
                for j in range(7) if i != j} for i in range(7)}
    families = [
        ("full_asymmetric", 7, full, None),
        ("sparse", 7, {0: {1: .2, 2: .8, 4: .9},
                       1: {2: .7}, 3: {4: .3}, 6: {}}, None),
        # B's nonempty direct row suppresses the stronger reverse C->B.
        ("direct_precedence", 5, {0: {1: .2, 2: .8},
                                  1: {3: .1}, 2: {1: .9}}, [0]),
        ("reverse_missing", 5, {0: {1: .2, 2: .8},
                               2: {1: .9}}, [0]),
        ("reverse_empty", 5, {0: {1: .2, 2: .8},
                             1: {}, 2: {1: .9}}, [0, 1]),
        ("source_only_skips", 5, {0: {1: .2, 2: .8}}, [0]),
        ("two_empty_rows", 5, {0: {}, 3: {}}, [0, 3]),
        ("selected_empty_plus_support", 5, {0: {}, 1: {2: .2, 3: .8},
                                            3: {2: .7}}, [0, 1]),
        ("zero_and_ties", 5, {0: {1: 0., 2: .5, 3: .5},
                             1: {2: .5, 3: .5}, 2: {3: .5}}, None),
        ("prior_pruned_support", 5, {0: {1: .1, 2: .3, 3: .9},
                                     1: {2: .5}, 2: {3: .8},
                                     3: {1: .7}}, None),
    ]
    for name, n, graph, selected in families:
        for eps in EPSILONS:
            cases.append(Case(name + "_e" + str(eps), n, graph, eps, selected))
    # Using nextafter catches strict > versus >= and binary64 epsilon edges.
    for eps in EPSILONS:
        weak = .5 * (1.0 - eps)
        for label, strong in (("below", math.nextafter(.5, 0.)),
                              ("exact", .5),
                              ("above", math.nextafter(.5, 1.))):
            graph = {0: {1: weak, 2: strong}, 1: {2: strong}}
            cases.append(Case("boundary_%s_e%s" % (label, eps), 4,
                              graph, eps, [0]))
    for count in (1, 2, 3, 4, 5, 9, 10, 11):
        graph = {0: {1: .1, **{i: .8 for i in range(2, count + 2)}},
                 1: {i: .7 for i in range(2, count + 2)}}
        for eps in (0., .15):
            cases.append(Case("witness_%02d_e%s" % (count, eps),
                              count + 3, graph, eps, [0]))
    for index in range(random_count):
        n = rng.randrange(3, 12)
        sources = rng.sample(range(n), rng.randrange(2, n + 1))
        graph = {source: {target: rng.choice((0., .05, .1, .2, .4, .8, 1.))
                          for target in range(n)
                          if target != source and rng.random() < .48}
                 for source in sources}
        selected = rng.sample(sources, rng.randrange(1, len(sources) + 1)) \
            if index % 2 else None
        cases.append(Case("random_%03d" % index, n, graph,
                          EPSILONS[index % 4], selected,
                          [i for i in range(n) if rng.random() < .3],
                          threshold=.1 if index % 7 == 0 else 0.))
    # Disabled DPI is a successful ordinary run but rejects requested witnesses.
    cases.append(Case("disabled_dpi", 3, triangle, 1.0))
    return cases


def inference_cases():
    cases = []
    for probability in ("0.001", "0.0005"):
        for seed in (17, 23):
            for eps in (0., .15):
                cases.append(Case("pchip_p%s_seed%d_e%s" %
                                  (probability, seed, eps), 12, None, eps,
                                  [0, 1, 2], probability=probability,
                                  model="pchip", seed=seed, subsample="80",
                                  inferred=True))
    for mode in ("legacy", "explicit"):
        for eps in (0., .15):
            cases.append(Case(mode + "_e" + str(eps), 12, None, eps,
                              [0, 1, 2], threshold=.05 if mode == "explicit"
                              else 0., probability="0.001", seed=17,
                              subsample="80", inferred=True))
    return cases


def parse_network(path):
    text = path.read_text(encoding="utf-8")
    header, data, edges = [], [], {}
    for line in text.splitlines():
        if line.startswith(">"):
            header.append(line)
        elif line:
            data.append(line)
            fields = line.split("\t")
            require(len(fields) % 2 == 1, "malformed serialized network row")
            require(fields[0] not in edges, "duplicate serialized source")
            row = {}
            for i in range(1, len(fields), 2):
                require(fields[i] not in row, "duplicate serialized target")
                require(math.isfinite(float(fields[i + 1])), "nonfinite output MI")
                row[fields[i]] = fields[i + 1]
            edges[fields[0]] = row
    return header, data, edges


def edge_count(network):
    return sum(len(row) for row in network[2].values())


def compare_networks(left_path, right_path):
    left, right = parse_network(left_path), parse_network(right_path)
    require(left[0] == right[0], "serialized network metadata changed")
    require(left[1] == right[1], "serialized data rows or MI values changed")
    require(left_path.read_bytes() == right_path.read_bytes(),
            "serialized network bytes changed despite equal parsed lines")
    return right


def statistics(stdout):
    rows = STAT_RE.findall(stdout)
    require(len(rows) == 1, "expected exactly one DPI_STATS record, got %r" % rows)
    pre, pruned, post, applied = map(int, rows[0])
    require(pre == pruned + post, "DPI_STATS conservation failed")
    return dict(pre_edges=pre, pruned_edges=pruned, post_edges=post,
                dpi_applied=applied)


def filtered_graph(case):
    return {i: {j: float(value) for j, value in case.graph.get(i, {}).items()
                if float(value) >= case.threshold} for i in range(case.n)}


def oracle_counts(case):
    """Simple exhaustive triple enumeration, without native intersection code."""
    graph = filtered_graph(case)
    sources = case.selected if case.selected is not None else list(range(case.n))
    annotated = set(case.annotated)
    rows, retained = [], {}
    for a in sources:
        counts = []
        retained[gene(a)] = set()
        for b, value_ab in graph[a].items():
            cutoff = value_ab / (1.0 - case.epsilon)
            eligible = set()
            for c, value_ac in graph[a].items():
                # A nonempty B row takes precedence, even if B->C is absent.
                value_bc = graph[b].get(c, 0.) if graph[b] else \
                    graph[c].get(b, 0.) if graph[c] else -1.
                if value_ac > cutoff and value_bc > cutoff and \
                        not ((a in annotated or b in annotated) and c not in annotated):
                    eligible.add(c)
            counts.append(len(eligible))
            if not eligible:
                retained[gene(a)].add(gene(b))
        row = dict(source_index=a, pre_edges=len(graph[a]))
        row.update({"witnesses_ge_" + str(k): sum(count >= k for count in counts)
                    for k in LEVELS})
        rows.append(row)
    return rows, retained


def parse_sidecar(path):
    metadata, table = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            key, value = line[2:].split("\t", 1)
            require(key not in metadata, "duplicate sidecar provenance key")
            metadata[key] = value
        elif line:
            table.append(line)
    rows = list(csv.DictReader(io.StringIO("\n".join(table)), delimiter="\t"))
    expected_fields = ["source_index", "pre_edges"] + [
        "witnesses_ge_" + str(k) for k in LEVELS]
    require(table and table[0].split("\t") == expected_fields,
            "unexpected witness table schema")
    return metadata, [{key: int(value) for key, value in row.items()} for row in rows]


def check_sidecar(path, case, paths, stats, unpruned, pruned):
    meta, rows = parse_sidecar(path)
    sources = case.selected if case.selected is not None else list(range(case.n))
    require([row["source_index"] for row in rows] == sources,
            "sidecar source membership/order changed")
    expected_meta = {
        "schema": "sjaracne.dpi_witness_threshold_counts.v1",
        "count_unit": "source-target edges",
        "source_index_basis": "zero-based expression-row index",
        "source_mode": "selected rows" if case.selected is not None else "all rows",
        "source_count": str(len(sources)),
        "annotated_gene_count": str(len(set(case.annotated))),
        "input_file": str(paths["expression"]),
        "input_adjacency_file": str(paths["adjacency"]) if case.graph is not None else "",
        "network_output_file": str(paths["witness_network"]),
        "subnetwork_file": str(paths["sources"]) if case.selected is not None else "",
        "annotation_file": str(paths["annotations"]) if case.annotated else "",
        "k1_pruned_edges": str(stats["pruned_edges"]),
    }
    for key, value in expected_meta.items():
        require(meta.get(key) == value, "wrong sidecar provenance %s: %r != %r" %
                (key, meta.get(key), value))
    require(float(meta.get("dpi_epsilon", "nan")) == case.epsilon,
            "wrong sidecar epsilon")
    require("unchanged pre-DPI" in meta.get("graph_state", ""),
            "sidecar graph state is missing")
    require("distinct eligible intermediates" in meta.get("count_semantics", ""),
            "sidecar witness semantics are missing")
    for row in rows:
        a = gene(row["source_index"])
        before = unpruned[2].get(a, {})
        after = pruned[2].get(a, {})
        require(set(after) <= set(before), "DPI introduced an edge")
        require(row["pre_edges"] == len(before), "per-source pre-edge mismatch")
        require(row["witnesses_ge_1"] == len(before) - len(after),
                "per-source ge1 differs from independent baseline pruning")
        nested = [row["pre_edges"]] + [row["witnesses_ge_" + str(k)] for k in LEVELS] + [0]
        require(all(a >= b for a, b in zip(nested, nested[1:])),
                "witness threshold counts are not nested")
    require(sum(row["pre_edges"] for row in rows) == stats["pre_edges"],
            "sidecar aggregate pre-edge mismatch")
    require(sum(row["witnesses_ge_1"] for row in rows) == stats["pruned_edges"],
            "sidecar aggregate ge1 mismatch")
    if case.graph is not None:
        expected, retained = oracle_counts(case)
        require(rows == expected, "sidecar differs from independent triple oracle: "
                + repr({"actual": rows, "expected": expected}))
        for source, targets in retained.items():
            require(set(pruned[2].get(source, {})) == targets,
                    "native retained targets differ from independent oracle")
    return {"rows": rows, "metadata": meta}


class Runner:
    def __init__(self, args):
        self.args = args
        self.invocations = 0

    def run(self, binary, args, folder, label):
        command = [str(binary)] + [str(arg) for arg in args]
        start = time.perf_counter()
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False,
                                timeout=self.args.timeout, cwd=folder)
        self.invocations += 1
        record = dict(command=command, returncode=result.returncode,
                      elapsed_seconds=time.perf_counter() - start,
                      stdout=result.stdout, stderr=result.stderr)
        (folder / (label + ".json")).write_text(json.dumps(record, indent=2) + "\n",
                                               encoding="utf-8")
        return result

    def check_case(self, case, folder):
        folder.mkdir()
        paths = {key: folder / name for key, name in {
            "expression": "input.exp", "adjacency": "input.adj",
            "sources": "sources.txt", "annotations": "annotations.txt",
            "baseline_network": "baseline.adj", "candidate_network": "candidate.adj",
            "unpruned_network": "unpruned.adj", "witness_network": "witness.adj",
            "sidecar": "witness.tsv"}.items()}
        write_expression(paths["expression"], case.n, 100 if case.inferred else 12,
                         19001)
        common = ["-i", paths["expression"], "-p", case.probability,
                  "-S", str(case.seed), "-N", "40"]
        if case.graph is not None:
            lines = []
            for source, row in case.graph.items():
                fields = [gene(source)]
                for target, value in row.items():
                    fields += [gene(target), repr(float(value))]
                lines.append("\t".join(fields))
            paths["adjacency"].write_text("\n".join(lines) + "\n", encoding="utf-8")
            common += ["-j", paths["adjacency"], "-t", str(case.threshold)]
        elif case.threshold:
            common += ["-t", str(case.threshold)]
        if case.model:
            common += ["-M", case.model]
        if case.subsample:
            common += ["-u", case.subsample, "-v", "on"]
        if case.inferred and not case.model and not case.threshold:
            common += ["-H", str(self.args.config_dir).replace("\\", "/") + "/"]
        if case.selected is not None:
            paths["sources"].write_text("\n".join(map(gene, case.selected)) + "\n",
                                        encoding="utf-8")
            common += ["-s", paths["sources"]]
        if case.annotated:
            paths["annotations"].write_text("\n".join(map(gene, case.annotated)) + "\n",
                                            encoding="utf-8")
            common += ["-l", paths["annotations"]]
        results = {}
        for label, binary, output, epsilon in (
                ("unpruned", self.args.baseline, paths["unpruned_network"], 1.),
                ("baseline", self.args.baseline, paths["baseline_network"], case.epsilon),
                ("candidate", self.args.candidate, paths["candidate_network"], case.epsilon)):
            results[label] = self.run(binary, common + ["-e", str(epsilon), "-o", output],
                                      folder, label)
            require(results[label].returncode == 0, label + " failed; inspect " + str(folder))
        unpruned = parse_network(paths["unpruned_network"])
        network = compare_networks(paths["baseline_network"], paths["candidate_network"])
        stats = statistics(results["candidate"].stdout)
        require(stats["pre_edges"] == edge_count(unpruned),
                "pre_edges differs from independent unpruned baseline")
        require(stats["post_edges"] == edge_count(network),
                "post_edges differs from serialized network")
        applied = case.epsilon < 1 and (case.inferred or len(case.graph) >= 2)
        require(stats["dpi_applied"] == int(applied), "incorrect dpi_applied flag")
        require(stats["pruned_edges"] == edge_count(unpruned) - edge_count(network),
                "pruned_edges differs from baseline edge loss")
        for source, row in network[2].items():
            before = unpruned[2].get(source, {})
            require(set(row) <= set(before), "new edge introduced during DPI")
            require(all(before[target] == value for target, value in row.items()),
                    "DPI changed retained MI values")
        witness_args = common + ["-e", str(case.epsilon), "-o", paths["witness_network"],
                                 "-W", paths["sidecar"]]
        witness = self.run(self.args.candidate, witness_args, folder, "witness")
        details = {}
        if applied:
            require(witness.returncode == 0, "-W failed; inspect " + str(folder))
            compare_networks(paths["baseline_network"], paths["witness_network"])
            require(statistics(witness.stdout) == stats, "-W altered DPI_STATS")
            details = check_sidecar(paths["sidecar"], case, paths, stats,
                                    unpruned, network)
        else:
            require(witness.returncode != 0, "-W accepted without active/applied DPI")
            require("requires" in witness.stderr and "DPI" in witness.stderr,
                    "-W rejection lacks expected DPI explanation")
            require(not paths["witness_network"].exists() and not paths["sidecar"].exists(),
                    "rejected -W created output")
            sentinel = b"DO NOT OVERWRITE: rejected witness diagnostic\n"
            paths["witness_network"].write_bytes(sentinel)
            paths["sidecar"].write_bytes(sentinel)
            repeat = self.run(self.args.candidate, witness_args, folder, "witness_existing")
            require(repeat.returncode != 0, "-W accepted on repeat without applied DPI")
            require(paths["witness_network"].read_bytes() == sentinel and
                    paths["sidecar"].read_bytes() == sentinel,
                    "rejected -W overwrote pre-existing output")
        if case.inferred:
            samples = [line for line in results["baseline"].stdout.splitlines()
                       if line.startswith("[SAMPLING] Selected original")]
            require(len(samples) == 1 and len(samples[0].split(":", 1)[1].split()) == 80,
                    "inference did not use the expected 80 observations")
            for result in (results["candidate"], results["unpruned"], witness):
                require(samples == [line for line in result.stdout.splitlines()
                                    if line.startswith("[SAMPLING] Selected original")],
                        "same-seed sampled observations changed")
            header = "\n".join(network[0])
            if case.model:
                require("AP-MI actual m 80" in header and "AP-MI Npar 40" in header,
                        "PCHIP actual m/Npar changed")
                require("experimental-not-uniformly-confirmed" in header and
                        "off-grid m yes" in header,
                        "PCHIP provenance or off-grid warning changed")
                cutoff = [line for line in results["baseline"].stdout.splitlines()
                          if line.startswith("[THRESHOLD] PCHIP cutoff binary64=")]
                require(len(cutoff) == 1, "PCHIP cutoff not reported")
                for result in (results["candidate"], results["unpruned"], witness):
                    require(cutoff == [line for line in result.stdout.splitlines()
                                      if line.startswith("[THRESHOLD] PCHIP cutoff binary64=")],
                            "PCHIP binary64 cutoff changed")
            else:
                require("PCHIP" not in header, "legacy/explicit mode gained PCHIP provenance")
        return dict(name=case.name, passed=True, inferred=case.inferred,
                    statistics=stats, witness_checked=applied,
                    independent_triple_oracle=applied and not case.inferred,
                    network_sha256=sha256(paths["baseline_network"]), **details)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Must not already exist; contains all retained evidence.")
    parser.add_argument("--config-dir", type=Path,
                        default=Path(__file__).resolve().parents[2] /
                        "SJARACNe-pr4-refresh" / "SJARACNe" / "config")
    parser.add_argument("--random-cases", type=int, default=60)
    parser.add_argument("--timeout", type=float, default=30.)
    parser.add_argument("--filter", default="", help="Only case names containing this text.")
    args = parser.parse_args()
    for key in ("baseline", "candidate", "output_dir", "config_dir"):
        setattr(args, key, getattr(args, key).resolve())
    for binary in (args.baseline, args.candidate):
        parser.error("binary not found: " + str(binary)) if not binary.is_file() else None
    if args.output_dir.exists():
        parser.error("--output-dir already exists; use a fresh directory")
    if not 0 <= args.random_cases <= 80:
        parser.error("--random-cases must be between 0 and 80 (lightweight scope)")
    if not (args.config_dir / "config_threshold.txt").is_file():
        parser.error("--config-dir must contain config_threshold.txt")
    cases = [case for case in replay_cases(args.random_cases) + inference_cases()
             if args.filter in case.name]
    if not cases:
        parser.error("--filter selected no cases")
    args.output_dir.mkdir(parents=True)
    runner = Runner(args)
    report = dict(scope="lightweight synthetic diagnostic differential; not scientific validation",
                  baseline=str(args.baseline), baseline_sha256=sha256(args.baseline),
                  candidate=str(args.candidate), candidate_sha256=sha256(args.candidate),
                  config_dir=str(args.config_dir),
                  affine_config_sha256=sha256(args.config_dir / "config_threshold.txt"),
                  random_cases=args.random_cases, total_cases=len(cases), cases=[])
    started = time.perf_counter()
    for index, case in enumerate(cases):
        try:
            result = runner.check_case(case, args.output_dir / ("%03d_" % index + case.name))
        except Exception as error:
            result = dict(name=case.name, passed=False, error=type(error).__name__ + ": " + str(error))
        report["cases"].append(result)
        print("[%d/%d] %s %s" % (index + 1, len(cases),
                                 "PASS" if result["passed"] else "FAIL", case.name), flush=True)
        if not result["passed"]:
            print("  " + result["error"], flush=True)
        report.update(passed=sum(row["passed"] for row in report["cases"]),
                      failed=sum(not row["passed"] for row in report["cases"]),
                      binary_invocations=runner.invocations,
                      elapsed_seconds=time.perf_counter() - started)
        (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                    encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("passed", "failed", "binary_invocations", "elapsed_seconds")}))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
