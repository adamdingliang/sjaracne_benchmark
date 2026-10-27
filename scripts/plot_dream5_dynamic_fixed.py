#!/usr/bin/env python3
"""Plot existing matched-budget DPI comparisons; never run network inference."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


HUBS = {'network1': (49, 98, 195), 'network3': (84, 167, 334)}
SLOPE = 0.05


def select_cases(path):
    """Select the declared comparison, rejecting missing/duplicate cases."""
    groups = {(dataset, h): [] for dataset, hubs in HUBS.items() for h in hubs}
    seen = set()
    with Path(path).open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            if not (row['scope'] == 'trajectory'
                    and row['annotation_mode'] == 'panel'
                    and row['comparison'] == 'dynamic_vs_fixed'
                    and float(row['slope']) == SLOPE
                    and row['target_label'] == 'strict_count'):
                continue
            dataset, h = row['dataset'], int(row['H'])
            panel, seed = int(row['panel']), int(row['seed'])
            key = dataset, h, panel, seed
            if key in seen:
                raise ValueError(f'Duplicate comparison: {key}')
            seen.add(key)
            if (dataset, h) not in groups or panel not in (1, 2, 3) or seed not in (1, 2, 3):
                raise ValueError(f'Unexpected comparison: {key}')
            if row['available'].lower() != 'true':
                raise ValueError(f'Unavailable comparison: {key}')
            tp, fp = float(row['TP_delta']), float(row['FP_delta'])
            budget = int(row['budget'])
            if not all(math.isfinite(v) for v in (tp, fp)) or budget <= 0:
                raise ValueError(f'Invalid numeric values: {key}')
            if not math.isclose(tp + fp, 0.0, rel_tol=0.0, abs_tol=1e-8):
                raise ValueError(f'TP/FP differences do not conserve the budget: {key}')
            if h == HUBS[dataset][-1] and abs(tp) > 1e-12:
                raise ValueError(f'Full-H arms must be identical: {key}')
            groups[dataset, h].append({
                'panel': panel, 'seed': seed, 'strict_labelled_edge_budget': budget,
                'TP_delta': tp, 'FP_delta': fp,
            })
    expected = {(p, s) for p in (1, 2, 3) for s in (1, 2, 3)}
    for key, cases in groups.items():
        if {(r['panel'], r['seed']) for r in cases} != expected:
            raise ValueError(f'Incomplete panel/seed comparisons: {key}')
        cases.sort(key=lambda r: (r['panel'], r['seed']))
    return groups


def file_record(path):
    content = Path(path).read_bytes()
    return {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}


def plot(source, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    groups = select_cases(source)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.hashsalt': 'dream5-dynamic-fixed-matched-budget-v1'})
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), sharey=True)
    low = min(r['TP_delta'] for cases in groups.values() for r in cases)
    high = max(r['TP_delta'] for cases in groups.values() for r in cases)
    for axis, (dataset, hubs) in zip(axes, HUBS.items()):
        axis.axhline(0, color='#333333', linestyle='--', linewidth=1.2, zorder=1)
        medians = []
        for x, h in enumerate(hubs):
            cases = groups[dataset, h]
            values = [r['TP_delta'] for r in cases]
            # Deterministic horizontal offsets expose coincident observations.
            xs = [x + (i - 4) * 0.025 for i in range(9)]
            axis.scatter(xs, values, color='#737c88', alpha=0.65, s=27,
                         edgecolors='white', linewidths=0.4, zorder=2,
                         label='Paired panel/seed cases' if x == 0 else None)
            median = statistics.median(values)
            medians.append(median)
            axis.annotate(f'{median:+g}' if median else '0', (x, median),
                          xytext=(0, -21 if median < 0 else 12),
                          textcoords='offset points', ha='center',
                          color='#125988', fontweight='bold', fontsize=12)
        axis.plot(range(3), medians, '-D', color='#125988', linewidth=2,
                  markersize=6, label='Median', zorder=3)
        axis.set_xticks(range(3), [str(h) for h in hubs])
        axis.set_xlabel('Hub-list size H')
        axis.set_xlim(-0.3, 2.3)
        axis.set_ylim(min(-5, low - 4), max(7, high + 3))
        axis.grid(axis='y', color='#e5e7eb', linewidth=0.7, zorder=0)
        name = 'Network 1 - simulated' if dataset == 'network1' else 'Network 3 - E. coli'
        axis.set_title(name, fontsize=13, pad=13)
    axes[0].set_ylabel('TP difference (dynamic minus fixed)')
    axes[0].legend(loc='lower right', frameon=False, fontsize=9)
    fig.suptitle('Does dynamic epsilon recover more TPs than fixed epsilon?',
                 fontsize=15, y=0.97)
    fig.text(0.5, 0.895,
             'Same strict-DPI labelled-edge budget in each case. Slope 0.05; panel annotation.',
             ha='center', fontsize=10)
    fig.text(0.5, 0.105,
             'Above zero favors dynamic; below zero favors fixed. Full-H zero is guaranteed by identical epsilon.',
             ha='center', fontsize=9)
    fig.text(0.5, 0.06,
             'Nine paired cases per H: 3 panel memberships x 3 sample seeds, not independent biological replicates.',
             ha='center', fontsize=9)
    fig.text(0.5, 0.02,
             'Each trajectory keeps its smallest-panel sources. Source sets differ across memberships; native jobs are reused.',
             ha='center', fontsize=9)
    fig.subplots_adjust(left=0.085, right=0.98, top=0.80, bottom=0.235, wspace=0.14)
    stem = output / 'dynamic_vs_fixed_matched_budget'
    png, svg = stem.with_suffix('.png'), stem.with_suffix('.svg')
    fig.savefig(png, dpi=180, facecolor='white', metadata={'Software': 'Matplotlib'})
    with svg.open('w', encoding='utf-8', newline='\n') as stream:
        fig.savefig(stream, format='svg', facecolor='white', metadata={'Date': None})
    plt.close(fig)
    metadata = {
        'schema': 'dream5-dpi-summary-figure-v1',
        'new_inference_runs': False,
        'source': Path(source).name, 'source_record': file_record(source),
        'script_record': file_record(__file__), 'matplotlib_version': matplotlib.__version__,
        'selection': {'scope': 'trajectory', 'annotation_mode': 'panel',
                      'comparison': 'dynamic_vs_fixed', 'slope': SLOPE,
                      'target_label': 'strict_count'},
        'budget_definition': 'Each case uses the strict-DPI emitted reference-labelled edge count.',
        'score_definition': 'Expected TP at MI-tie boundaries; paired dynamic minus fixed.',
        'replication_note': 'Overlapping source panels and reused native jobs; not biological replication.',
        'groups': [{'dataset': dataset, 'H': h, 'cases': cases,
                    'median_TP_delta': statistics.median(r['TP_delta'] for r in cases)}
                   for (dataset, h), cases in groups.items()],
        'outputs': {p.name: file_record(p) for p in (png, svg)},
    }
    stem.with_suffix('.json').write_text(json.dumps(metadata, indent=2) + '\n',
                                       encoding='utf-8', newline='\n')
    return metadata


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=root / 'benchmarks/dpi_epsilon_summaries/evidence/dream5_controls/matched_budget_comparisons.tsv')
    parser.add_argument('--output-dir', type=Path, default=root / 'docs/benchmark_summaries/figures')
    args = parser.parse_args()
    result = plot(args.source, args.output_dir)
    print(json.dumps({'groups': len(result['groups']), 'cases': sum(len(g['cases']) for g in result['groups']),
                      'output_dir': str(args.output_dir)}))


if __name__ == '__main__':
    main()
