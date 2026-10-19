#!/usr/bin/env python3
"""Independent, source-streamed audit of directed consensus recurrence.

No engine modules are imported. The pinned driver list defines an order which
every raw adjacency stream must obey; unknown or out-of-order sources fail
closed. Only one source's union is aggregated at once. The two selected output
networks, not the full raw union, are held in memory.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import heapq
import json
import math
from pathlib import Path
import sys
import time


class AuditError(ValueError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def driver_order(path):
    result = {}
    with Path(path).open(encoding='utf-8-sig') as handle:
        for line in handle:
            name = line.strip()
            if name and name not in result:
                if '\t' in name or ' ' in name:
                    raise AuditError('Driver identifiers must not contain whitespace')
                result[sys.intern(name)] = len(result)
    if not result:
        raise AuditError('Empty driver list')
    return result


def adjacency_groups(handle, path, order, record):
    """Yield one deduplicated source group per file, retaining file order."""
    digest = hashlib.sha256()
    current = None
    current_rank = -1
    edges = {}
    for number, raw in enumerate(handle, 1):
        digest.update(raw)
        record['bytes'] += len(raw)
        line = raw.decode('utf-8').rstrip('\r\n')
        if not line or line.startswith('>'):
            continue
        fields = line.split('\t')
        source = sys.intern(fields[0])
        if source not in order:
            raise AuditError('Unknown source %r at %s:%d' % (source, path, number))
        rank = order[source]
        if rank < current_rank:
            raise AuditError('Out-of-order source %r at %s:%d' % (source, path, number))
        if len(fields) % 2 != 1:
            raise AuditError('Malformed adjacency row at %s:%d' % (path, number))
        if current is not None and rank != current_rank:
            record['edge_count'] += len(edges)
            record['source_groups'] += 1
            yield current_rank, current, edges
            edges = {}
        current, current_rank = source, rank
        for index in range(1, len(fields), 2):
            target = sys.intern(fields[index])
            if not target:
                raise AuditError('Empty target at %s:%d' % (path, number))
            try:
                mi = float(fields[index + 1])
            except ValueError as error:
                raise AuditError('Invalid MI at %s:%d' % (path, number)) from error
            if not math.isfinite(mi):
                raise AuditError('Non-finite MI at %s:%d' % (path, number))
            if target in edges:
                if edges[target] != mi:
                    raise AuditError('Conflicting duplicate %s->%s in %s' % (source, target, path))
                record['duplicate_occurrences_ignored'] += 1
            else:
                edges[target] = mi
    if current is not None:
        record['edge_count'] += len(edges)
        record['source_groups'] += 1
        yield current_rank, current, edges
    record['sha256'] = digest.hexdigest()
    record['source_order_verified'] = True


def network_rows(path):
    """Read a strictly sorted network projection, accepting 3col or ncol."""
    previous = None
    with Path(path).open(encoding='utf-8', newline='') as handle:
        columns = handle.readline().rstrip('\r\n').split('\t')
        if len(set(columns)) != len(columns) or not {'source', 'target', 'MI'} <= set(columns):
            raise AuditError('Invalid network header: ' + str(path))
        source_index, target_index, mi_index = (columns.index(name) for name in ('source', 'target', 'MI'))
        for number, line in enumerate(handle, 2):
            fields = line.rstrip('\r\n').split('\t')
            if len(fields) != len(columns):
                raise AuditError('Malformed network row at %s:%d' % (path, number))
            key = (sys.intern(fields[source_index]), sys.intern(fields[target_index]))
            if not all(key) or previous is not None and key <= previous:
                raise AuditError('Network is not strictly ordered at %s:%d' % (path, number))
            mi = fields[mi_index]
            try:
                numeric = float(mi)
            except ValueError as error:
                raise AuditError('Invalid consensus MI at %s:%d' % (path, number)) from error
            if not math.isfinite(numeric) or mi != format(numeric, '.4f'):
                raise AuditError('Consensus MI must be finite and four-decimal at %s:%d' % (path, number))
            previous = key
            yield key, mi


def load_network(path):
    result = {}
    count = 0
    for (source, target), mi in network_rows(path):
        result.setdefault(source, {})[target] = mi
        count += 1
    return result, {'path': str(path), 'sha256': sha256(path), 'edges': count,
                    'strict_lexical_order_verified': True}


def normal_tail(support, mu, sigma):
    # Match the historical sigma=0 convention, but independently evaluate the
    # Gaussian survival function with libm erfc, never the engine's uprob code.
    z = (support - mu) / sigma if sigma else 100.0
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def validate_support(adjacency_dir, drivers, k6_network, legacy_network, *,
                     expected_runs=100, minimum_recurrence=6, legacy_p=1e-5,
                     historical_legacy_network=None, historical_legacy_sha256=None,
                     check_metadata=True, check_enhanced=True, progress=None):
    started = time.monotonic()
    if expected_runs < 1 or not 1 <= minimum_recurrence <= expected_runs:
        raise AuditError('Require 1 <= minimum recurrence <= expected runs')
    if not math.isfinite(legacy_p) or not 0 < legacy_p <= 1:
        raise AuditError('Legacy probability must be in (0,1]')
    adjacency_dir, drivers = Path(adjacency_dir), Path(drivers)
    paths = sorted(adjacency_dir.glob('*.adj'))
    if len(paths) != expected_runs or any(not path.is_file() for path in paths):
        raise AuditError('Expected exactly %d adjacency files, found %d' % (expected_runs, len(paths)))
    order = driver_order(drivers)
    k6, k6_info = load_network(k6_network)
    legacy, legacy_info = load_network(legacy_network)
    issues = {}
    examples = []

    def issue(kind, amount=1, example=None):
        issues[kind] = issues.get(kind, 0) + amount
        if example is not None and len(examples) < 20:
            examples.append({'kind': kind, 'example': example})

    def projection_check(network):
        path = Path(network)
        enhanced = path.with_name('consensus_network_ncol_.txt')
        from itertools import zip_longest
        count = 0
        for left, right in zip_longest(network_rows(path), network_rows(enhanced)):
            if left != right:
                issue('enhanced_projection_mismatch', example=repr((left, right)))
            count += 1
        return {'path': str(enhanced), 'sha256': sha256(enhanced), 'rows_compared': count}

    enhanced_info = ({'k6': projection_check(k6_network), 'legacy_pc': projection_check(legacy_network)}
                     if check_enhanced else None)
    histogram = [0] * (expected_runs + 1)
    selected_histograms = {'k6': [0] * (expected_runs + 1),
                           'legacy_pc': [0] * (expected_runs + 1)}
    overlap = {'shared': 0, 'k6_only': 0, 'legacy_pc_only': 0}
    runs = []
    source_count = 0
    with ExitStack() as stack:
        streams = []
        heap = []
        for index, path in enumerate(paths):
            record = {'file': path.name, 'path': str(path), 'bytes': 0,
                      'edge_count': 0, 'source_groups': 0,
                      'duplicate_occurrences_ignored': 0, 'source_order_verified': False}
            runs.append(record)
            stream = adjacency_groups(stack.enter_context(path.open('rb')), path, order, record)
            streams.append(stream)
            first = next(stream, None)
            if first is not None:
                heapq.heappush(heap, (first[0], index, first[1], first[2]))
        while heap:
            rank = heap[0][0]
            source = heap[0][2]
            stats = {}
            while heap and heap[0][0] == rank:
                _, index, observed_source, edges = heapq.heappop(heap)
                if observed_source != source:
                    raise AuditError('Driver order map is inconsistent')
                # Heap tie order is sorted adjacency filename order, exactly
                # fixing the binary64 summation order for MI means.
                for target, mi in edges.items():
                    if target in stats:
                        stats[target][0] += 1
                        stats[target][1] += mi
                    else:
                        stats[target] = [1, mi]
                following = next(streams[index], None)
                if following is not None:
                    heapq.heappush(heap, (following[0], index, following[1], following[2]))
            actual = {'k6': k6.pop(source, {}), 'legacy_pc': legacy.pop(source, {})}
            for target, (support, mi_sum) in stats.items():
                if not 1 <= support <= expected_runs:
                    raise AuditError('Support outside [1,B]')
                histogram[support] += 1
                expected_mi = format(mi_sum / support, '.4f')
                present = {}
                for mode in ('k6', 'legacy_pc'):
                    present[mode] = target in actual[mode]
                    if present[mode]:
                        selected_histograms[mode][support] += 1
                        if actual[mode][target] != expected_mi:
                            issue(mode + '_mi_mismatch', example='%s->%s' % (source, target))
                if present['k6'] != (support >= minimum_recurrence):
                    issue('k6_membership_mismatch', example='%s->%s support=%d' % (source, target, support))
                if present['k6'] and present['legacy_pc']:
                    overlap['shared'] += 1
                elif present['k6']:
                    overlap['k6_only'] += 1
                elif present['legacy_pc']:
                    overlap['legacy_pc_only'] += 1
            for mode in ('k6', 'legacy_pc'):
                absent = actual[mode].keys() - stats.keys()
                if absent:
                    issue(mode + '_edges_absent_from_union', len(absent), source)
            source_count += 1
            if progress and source_count % 1000 == 0:
                progress({'sources_processed': source_count})
    for mode, remaining in (('k6', k6), ('legacy_pc', legacy)):
        if remaining:
            issue(mode + '_edges_absent_from_union', sum(map(len, remaining.values())))
    union = sum(histogram)
    incidence = sum(support * count for support, count in enumerate(histogram))
    if incidence != sum(run['edge_count'] for run in runs):
        raise AuditError('Histogram/run incidence conservation failed')
    probabilities = [float(run['edge_count']) / union if union else 0.0 for run in runs]
    mu = sum(probabilities)
    sigma = math.sqrt(sum(q * (1.0 - q) for q in probabilities))
    gate = []
    eligible = []
    for support in range(1, expected_runs + 1):
        tail = normal_tail(support, mu, sigma)
        accepted = tail < legacy_p
        if accepted:
            eligible.append(support)
        expected = histogram[support] if accepted else 0
        observed = selected_histograms['legacy_pc'][support]
        if expected != observed:
            issue('legacy_pc_membership_mismatch', abs(expected - observed),
                  'support=%d expected=%d observed=%d normal_tail=%.17g' %
                  (support, expected, observed, tail))
        gate.append({'support': support, 'normal_tail': tail, 'selected': accepted,
                     'union_edges': histogram[support], 'actual_legacy_edges': observed})
    # Every actual legacy edge was checked against the raw union. For a gate
    # depending only on integer support, equality in every support bin proves
    # exact membership, not just equality of overall network sizes.
    metadata_info = {}
    if check_metadata:
        for mode, network in (('k6', k6_network), ('legacy_pc', legacy_network)):
            directory = Path(network).parent
            metadata_path = directory / 'bootstrap_info_.txt'
            values = dict(line.split(': ', 1) for line in metadata_path.read_text().splitlines())
            if values.get('Total edge tested') != str(union):
                issue(mode + '_metadata_union_mismatch')
            parameter_path = directory / 'parameter_info_.txt'
            parameters = parameter_path.read_text()
            if '>  Bootstrap No: %d\n' % expected_runs not in parameters:
                issue(mode + '_metadata_B_mismatch')
            if mode == 'k6':
                required = {'Consensus selection': 'minimum recurrence',
                            'Bootstrap networks': str(expected_runs),
                            'Minimum recurrence': str(minimum_recurrence),
                            'Minimum recurrence fraction': format(minimum_recurrence / expected_runs, '.12g')}
                if any(values.get(key) != value for key, value in required.items()):
                    issue('k6_metadata_selection_mismatch')
                for line in ('>  Consensus selection minimum recurrence\n',
                             '>  Minimum recurrence %d of %d\n' % (minimum_recurrence, expected_runs),
                             '>  Minimum recurrence fraction %s\n' % required['Minimum recurrence fraction']):
                    if line not in parameters:
                        issue('k6_parameter_selection_mismatch', example=line.strip())
            else:
                if 'Minimum recurrence' in parameters or 'Minimum recurrence' in values:
                    issue('legacy_pc_metadata_selection_mismatch')
                for key, expected in (('mu', mu), ('sigma', sigma)):
                    try:
                        matches = math.isclose(float(values[key]), expected, rel_tol=1e-12, abs_tol=1e-12)
                    except (KeyError, ValueError):
                        matches = False
                    if not matches:
                        issue('legacy_pc_metadata_' + key + '_mismatch')
            metadata_info[mode] = {'bootstrap_info_sha256': sha256(metadata_path),
                                   'parameter_info_sha256': sha256(parameter_path)}
    historical = None
    if historical_legacy_network is not None:
        historical_hash = sha256(historical_legacy_network)
        historical = {'path': str(historical_legacy_network), 'sha256': historical_hash,
                      'expected_sha256': historical_legacy_sha256,
                      'matches_new_legacy_sha256': historical_hash == legacy_info['sha256']}
        if historical_hash != legacy_info['sha256']:
            issue('historical_legacy_sha256_mismatch')
        if historical_legacy_sha256 is not None and historical_hash != historical_legacy_sha256:
            issue('historical_baseline_sha256_mismatch')
    elif historical_legacy_sha256 is not None:
        raise AuditError('A historical SHA256 requires its historical network path')
    observed_legacy_supports = [support for support in range(1, expected_runs + 1)
                               if selected_histograms['legacy_pc'][support]]
    return {
        'schema': 'brca100-pchip-independent-support-audit-v1', 'passed': not issues,
        'algorithm': 'driver-order-verified source-wise heap merge; no engine imports',
        'legacy_reference': 'canonical normal survival 0.5*erfc(z/sqrt(2)); strict p comparison; no retuning',
        'auditor_sha256': sha256(__file__), 'B': expected_runs, 'K': minimum_recurrence,
        'K_over_B': minimum_recurrence / expected_runs, 'legacy_p': legacy_p,
        'drivers': {'path': str(drivers), 'sha256': sha256(drivers), 'count': len(order)},
        'source_order_verified_for_all_files': all(run['source_order_verified'] for run in runs),
        'empty_adjacency_files': sum(run['edge_count'] == 0 for run in runs),
        'sources_with_rows': source_count, 'union_edges': union, 'pair_incidence': incidence,
        'histogram': {str(k): histogram[k] for k in range(1, expected_runs + 1)},
        'selected_histograms': {mode: {str(k): values[k] for k in range(1, expected_runs + 1)}
                                for mode, values in selected_histograms.items()},
        'runs': runs, 'networks': {'k6': k6_info, 'legacy_pc': legacy_info},
        'enhanced_projection': enhanced_info, 'metadata': metadata_info,
        'legacy_mu': mu, 'legacy_sigma': sigma, 'legacy_gate_by_support': gate,
        'legacy_minimum_eligible_support': min(eligible) if eligible else None,
        'legacy_observed_minimum_support': min(observed_legacy_supports) if observed_legacy_supports else None,
        'overlap': overlap,
        'legacy_is_subset_of_k6': overlap['legacy_pc_only'] == 0,
        'k6_is_subset_of_legacy': overlap['k6_only'] == 0,
        'historical_legacy': historical, 'issues': issues, 'issue_examples': examples,
        'duration_seconds': time.monotonic() - started,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('adjacency-dir', 'drivers', 'k6-network', 'legacy-network', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-runs', type=int, default=100)
    parser.add_argument('--minimum-recurrence', type=int, default=6)
    parser.add_argument('--legacy-p', type=float, default=1e-5)
    parser.add_argument('--historical-legacy-network', type=Path)
    parser.add_argument('--historical-legacy-sha256')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite existing audit output')
    arguments = vars(args).copy()
    output = arguments.pop('output')
    try:
        record = validate_support(**arguments, progress=lambda item: print(json.dumps(item), file=sys.stderr, flush=True))
    except (AuditError, OSError, UnicodeError, ValueError) as error:
        record = {'schema': 'brca100-pchip-independent-support-audit-v1', 'passed': False,
                  'error': {'type': type(error).__name__, 'message': str(error)}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(record, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    print('SUPPORT_AUDIT_RESULT=' + json.dumps({'passed': record['passed'], 'output': str(output)}), flush=True)
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
