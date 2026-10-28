#!/usr/bin/env python3
"""Plot frozen BRCA/LUAD summary tables without rerunning network inference."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
CASES = {'BRCA100': ('brca100_fixed_grid', 479, 2608, 10680),
         'LUAD100': ('luad100_common', 477, 1929, 9464)}
MODES = ('strict', 'fixed', 'fixed_0.2', 'fixed_0.25', 'dynamic_0.05')
LABELS = {'strict': 'Strict', 'fixed': 'Fixed 0.10', 'fixed_0.2': 'Fixed 0.20',
          'fixed_0.25': 'Fixed 0.25', 'dynamic_0.05': 'Dynamic s=0.05'}
COLORS = {'strict': '#41464d', 'fixed': '#8c65a8', 'fixed_0.2': '#c87520',
          'fixed_0.25': '#448256', 'dynamic_0.05': '#176ba0'}


def table(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def one(rows, **conditions):
    selected = [r for r in rows if all(r[k] == str(v) for k, v in conditions.items())]
    if len(selected) != 1:
        raise ValueError(f'Expected one summary row, found {len(selected)}: {conditions}')
    row = selected[0]
    if int(row['comparisons']) != 3 or int(row['available_comparisons']) != 3:
        raise ValueError(f'Endpoint must have three available observation pairs: {conditions}')
    return row


def paired_increase(rows, network, baseline, full, mode):
    """Deduplicate panel aliases, subtract within seed, then summarize."""
    pairs = []
    for seed in ('1', '2', '3'):
        endpoints = []
        for h in (baseline, full):
            subset = [r for r in rows if r['network'] == network and r['seed'] == seed
                      and int(r['H']) == h and r['strategy_label'] == mode]
            ids = {r['job_id'] for r in subset}
            values = {float(r['pooled_pruning_fraction']) for r in subset}
            if not subset or len(ids) != 1 or len(values) != 1:
                raise ValueError('Missing endpoint or inconsistent physical aliases')
            value = values.pop()
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Invalid pruning fraction')
            endpoints.append(value)
        pairs.append({'seed': int(seed), 'baseline': endpoints[0], 'full': endpoints[1],
                      'increase_pp': 100 * (endpoints[1] - endpoints[0])})
    return pairs


def record(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def load():
    result, sources = {}, {}
    for dataset, (folder, baseline, tf_full, sig_full) in CASES.items():
        directory = ROOT / 'benchmarks/dpi_epsilon_summaries/evidence' / folder
        tables = {}
        for name in ('frontier_summary.tsv', 'run_summary.tsv', 'runs.tsv'):
            path = directory / name
            tables[name] = table(path)
            sources[str(path.relative_to(ROOT)).replace('\\', '/')] = record(path)
        endpoints = {}
        for mode in MODES:
            common = dict(comparison_kind='tf_full_vs_sig_full', left_H=tf_full,
                          right_H=sig_full, strategy_label=mode)
            raw = one(tables['frontier_summary.tsv'], **common, metric_scope='raw')
            matched = one(tables['frontier_summary.tsv'], **common, metric_scope='matched',
                          budget='20', tie_namespace='brca-common-ties-primary-v1')
            endpoints[mode] = {key: float(raw[column]) for key, column in {
                'raw_jaccard': 'pooled_jaccard_median', 'tf_pruning': 'left_pruning_median',
                'sig_pruning': 'right_pruning_median', 'combined_pruning': 'combined_pruning_median'}.items()}
            endpoints[mode].update(top20_jaccard=float(matched['pooled_jaccard_median']),
                                   top20_eligible_sources=int(matched['eligible_sources_median']))
        increases = {network: {mode: paired_increase(tables['runs.tsv'], network, baseline, full, mode)
                              for mode in ('strict', 'fixed_0.2', 'fixed_0.25', 'dynamic_0.05')}
                     for network, full in (('tf', tf_full), ('sig', sig_full))}
        targets = {network: {mode: sorted([
            {'H': int(r['H']), 'median_targets': float(r['median_targets_median']),
             'comparisons': int(r['available_comparisons'])}
            for r in tables['run_summary.tsv'] if r['network'] == network and r['strategy_label'] == mode
        ], key=lambda r: r['H']) for mode in ('strict', 'fixed_0.2', 'fixed_0.25', 'dynamic_0.05')}
                   for network in ('tf', 'sig')}
        result[dataset] = {'endpoints': endpoints, 'increases': increases, 'targets': targets}
    return result, sources


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    data, sources = load()
    output = ROOT / 'docs/benchmark_summaries/figures'
    output.mkdir(exist_ok=True, parents=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    outputs = {}

    def save(fig, name):
        path = output / (name + '.png')
        fig.savefig(path, dpi=180, facecolor='white', metadata={'Software': 'Matplotlib'})
        plt.close(fig)
        outputs[path.name] = record(path)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharex=True, sharey=True)
    for ax, metric, title in zip(axes, ('raw_jaccard', 'top20_jaccard'),
                                 ('All retained common-source edges', 'Top 20 targets per eligible source')):
        for offset, (dataset, color) in zip((-0.18, 0.18), (('BRCA100', '#176ba0'), ('LUAD100', '#ca7824'))):
            vals = [data[dataset]['endpoints'][m][metric] for m in MODES]
            ax.barh([i + offset for i in range(5)], vals, height=0.32, color=color, label=dataset)
            for i, value in enumerate(vals):
                ax.text(value + 0.012, i + offset, f'{value:.3f}', va='center', fontsize=9)
        ax.set_yticks(range(5), [LABELS[m] for m in MODES])
        ax.set_xlim(0, 1.10)
        ax.set_xticks((0, .25, .5, .75, 1))
        ax.set_xlabel('Pooled TF-versus-SIG edge-set Jaccard')
        ax.set_title(title, fontsize=12)
        ax.grid(axis='x', alpha=.18)
        ax.set_axisbelow(True)
    axes[0].invert_yaxis()
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.5, .93),
               ncol=2, frameon=False)
    fig.suptitle('Do common sources retain the same targets in TF and SIG contexts?', fontsize=14, y=.98)
    fig.text(.5, .055, 'Medians of three matched observation pairs. Agreement is not accuracy.', ha='center')
    fig.text(.5, .018, 'Top-20 median eligible sources: BRCA100 276 of 479 probes; LUAD100 457 of 477 genes.', ha='center', fontsize=9)
    fig.subplots_adjust(left=.13, right=.965, top=.80, bottom=.18, wspace=.22)
    save(fig, 'common_source_identity')

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), sharey=True)
    for ax, network in zip(axes, ('tf', 'sig')):
        for mode, points in data['LUAD100']['targets'][network].items():
            ax.plot(range(len(points)), [r['median_targets'] for r in points], '-o',
                    color=COLORS[mode], label=LABELS[mode], linewidth=2, markersize=5)
        ax.set_xticks(range(len(points)), [str(r['H']) for r in points])
        ax.set_xlabel('Hub-list size H (categorical panel levels)')
        ax.set_title('LUAD100 - ' + network.upper() + ' context', fontsize=12)
        ax.set_ylim(35, 160)
        ax.grid(axis='y', alpha=.2)
    axes[0].set_ylabel('Median targets per common source')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(.5, .12), ncol=4, frameon=False)
    fig.suptitle('LUAD common-source target-list sizes as surrounding panels expand', fontsize=14, y=.97)
    fig.text(.5, .08, 'Positive fixed tolerance relaxes the baseline too; dynamic starts at epsilon zero at H=477.', ha='center', fontsize=9)
    fig.text(.5, .035, 'Group medians, not paired changes. Baseline/full aliases are deduplicated; coverage stays 100%.', ha='center', fontsize=9)
    fig.subplots_adjust(left=.08, right=.98, top=.82, bottom=.31, wspace=.15)
    save(fig, 'luad_target_sizes')

    modes = ('strict', 'fixed_0.2', 'fixed_0.25', 'dynamic_0.05')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), sharey=True)
    for ax, dataset in zip(axes, CASES):
        for offset, network, color in ((-.18, 'tf', '#176ba0'), (.18, 'sig', '#ca7824')):
            vals = [statistics.median(r['increase_pp'] for r in data[dataset]['increases'][network][m]) for m in modes]
            ax.bar([i + offset for i in range(4)], vals, width=.32, label=network.upper(), color=color)
            for i, value in enumerate(vals):
                ax.text(i + offset, value + .6, f'{value:.1f}', ha='center', fontsize=9)
        ax.set_xticks(range(4), [LABELS[m].replace(' ', '\n', 1) for m in modes])
        ax.set_title(dataset)
        ax.set_ylim(0, 38)
        ax.grid(axis='y', alpha=.18)
        ax.set_axisbelow(True)
    axes[0].set_ylabel('Full-minus-baseline pruning increase (percentage points)')
    axes[0].legend(frameon=False)
    fig.suptitle('How much does common-source pruning increase with panel size?', fontsize=14, y=.97)
    fig.text(.5, .09, 'Subtract within each seed, then take the median of three pairs. Physical panel aliases are deduplicated.', ha='center', fontsize=9)
    fig.text(.5, .04, 'Baseline: 479 BRCA probes or 477 LUAD genes. Fixed tolerance relaxes the baseline; dynamic is zero there.', ha='center', fontsize=9)
    fig.subplots_adjust(left=.08, right=.98, top=.82, bottom=.25, wspace=.16)
    save(fig, 'bulk_pruning_increase')

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
    offsets = {'strict': (-20, -20), 'fixed': (8, -10), 'fixed_0.2': (-15, -28),
               'fixed_0.25': (-5, 12), 'dynamic_0.05': (8, -18)}
    for ax, dataset in zip(axes, CASES):
        for mode in MODES:
            point = data[dataset]['endpoints'][mode]
            x, y = 100 * point['combined_pruning'], point['top20_jaccard']
            ax.scatter([x], [y], color=COLORS[mode], s=75, marker='D' if mode == 'dynamic_0.05' else 'o', zorder=3)
            ax.annotate(LABELS[mode], (x, y), xytext=offsets[mode], textcoords='offset points', fontsize=9, color=COLORS[mode])
        ax.set_title(dataset)
        ax.set_xlabel('Combined common-source candidate pruning (%)')
        ax.set_ylim(.5, 1.015)
        ax.set_xlim((10, 40) if dataset == 'BRCA100' else (30, 77))
        ax.grid(alpha=.2)
    axes[0].set_ylabel('Pooled Top-20 TF-versus-SIG Jaccard')
    fig.suptitle('Full-context target agreement versus how much pruning is retained', fontsize=14, y=.97)
    fig.text(.5, .10, 'Points are separate metric medians across three matched observation pairs; horizontal scales differ.', ha='center', fontsize=9)
    fig.text(.5, .055, 'Neither agreement nor pruning is an accuracy score. No optimum is selected; fixed 0.20 and 0.25 remain competitive.', ha='center', fontsize=9)
    fig.text(.5, .015, 'No-DPI Top-20 was not assessed and is not plotted. Its raw context Jaccard is 1 by construction, with zero pruning.', ha='center', fontsize=9)
    fig.subplots_adjust(left=.09, right=.98, top=.82, bottom=.245, wspace=.15)
    save(fig, 'bulk_full_context_tradeoff')

    meta = {'schema': 'bulk-dpi-summary-figures-v1', 'new_inference_runs': False,
            'matplotlib_version': matplotlib.__version__, 'source_files': sources,
            'script': record(__file__), 'data': data, 'outputs': outputs,
            'scope': 'Only fixed common-source edges; no biological reference or accuracy scores.',
            'replication': 'Three overlapping observation resamples, with shared native endpoint aliases.',
            'no_dpi': 'Not in run summaries; no matched Top-20 values imputed or plotted.'}
    (output / 'bulk_dpi_summary_figures.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'figures': list(outputs), 'source_tables': len(sources), 'new_inference_runs': False}))


if __name__ == '__main__':
    main()
