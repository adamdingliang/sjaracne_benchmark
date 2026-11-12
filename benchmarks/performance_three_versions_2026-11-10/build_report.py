#!/usr/bin/env python3
"""Build an honest, incrementally updated performance report and scientific plots.

Inputs are the runner's immutable plan, measurements, and live status JSON files.
Missing and unfinished cases remain labelled; they are never represented by zero
runtime or memory. Scientific method changes are kept explicit in the report.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

# Keep generated Matplotlib cache outside the tracked benchmark report.
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'sjaracne_performance_mpl_20261110'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

VERSIONS = ['commit_4cd8eae', 'v0.3.0', 'v0.4.0']
VERSION_LABELS = {'commit_4cd8eae': 'SJARACNe 4cd8eae', 'v0.3.0': 'SJARACNe v0.3.0', 'v0.4.0': 'SJARACNe2 v0.4.0'}
COMMITS = {'commit_4cd8eae': '4cd8eae2d63eebad8f4329bd907c7fb8877ebc29', 'v0.3.0': '12113fbc80d753d945598ffc2c7d9e45787bc8e0', 'v0.4.0': '8c0c1e08f99cbf14b58265a167459bf766593ef8'}
COLORS = {'commit_4cd8eae': '#697b94', 'v0.3.0': '#2674ad', 'v0.4.0': '#e1812c'}
PHASE_COLORS = ['#4477aa', '#ee7733', '#228833', '#cc6677', '#aa3377', '#66ccee', '#bbbbbb', '#997700']
GIB = 1024 ** 3


def local_path(value):
    """Translate a WSL mount path when the builder runs through Windows Python."""
    value = str(value)
    if os.name == 'nt':
        match = re.match(r'^/mnt/([a-zA-Z])/(.*)$', value)
        if match:
            value = match.group(1).upper() + ':/' + match.group(2)
    return Path(value)


def read_json(path, default=None):
    if path is None or not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def canonical_version(value):
    value = str(value or '')
    lower = value.lower()
    if '4cd8eae' in lower:
        return 'commit_4cd8eae'
    if lower in ('0.3.0', 'v0.3.0', 'v030', 'v0_3_0') or lower.startswith('12113fb'):
        return 'v0.3.0'
    if lower in ('0.4.0', 'v0.4.0', 'v040', 'v0_4_0') or lower.startswith('8c0c1e0'):
        return 'v0.4.0'
    return value


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None



def reported_wall_time(result):
    """Choose GNU elapsed, then UTC interval, then the unchanged runner metric.

    Clock disagreement is recorded without assuming its cause. The input JSON
    remains the authoritative record of every originally observed clock value.
    """
    gnu = number((result.get('gnu_time') or {}).get('elapsed_seconds'))
    interval = None
    try:
        start = datetime.fromisoformat(str(result['started_utc']).replace('Z', '+00:00'))
        finish = datetime.fromisoformat(str(result['finished_utc']).replace('Z', '+00:00'))
        candidate = (finish - start).total_seconds()
        interval = candidate if math.isfinite(candidate) and candidate >= 0 else None
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    monotonic = number(result.get('wall_seconds'))
    if gnu is not None and gnu >= 0:
        return gnu, 'GNU time', interval, monotonic
    if interval is not None:
        return interval, 'UTC interval', interval, monotonic
    if monotonic is not None and monotonic >= 0:
        return monotonic, 'Runner monotonic fallback', interval, monotonic
    return None, None, interval, monotonic


def format_num(value, digits=2):
    value = number(value)
    return 'NA' if value is None else f'{value:,.{digits}f}'


def seconds_label(value):
    if value >= 3600:
        return f'{value / 3600:.2f} h'
    if value >= 60:
        return f'{value / 60:.2f} min'
    return f'{value:.2f} s'


def safe_label(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def write_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode('utf-8'))


def write_tsv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter='\t', lineterminator='\n', extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: 'NA' if row.get(k) is None else row.get(k, '') for k in fields})


def cases_from_plan(plan):
    cases = plan.get('cases', plan.get('runs', []))
    if isinstance(cases, dict):
        cases = [dict(value, id=value.get('id', key)) for key, value in cases.items()]
    return [dict(case) for case in cases]


def normalized_rows(plan, measurements, status):
    raw_results = measurements.get('results', []) if isinstance(measurements, dict) else measurements
    if isinstance(raw_results, dict):
        raw_results = [dict(value, id=value.get('id', key)) for key, value in raw_results.items()]
    raw_results = list(raw_results or [])
    cases = cases_from_plan(plan)
    if not cases:
        cases = [dict(row) for row in raw_results]
    rows = []
    used = set()
    for index, case in enumerate(cases):
        identity = str(case.get('id', case.get('case_id', f'case_{index + 1}')))
        version = canonical_version(case.get('version', case.get('method', '')))
        dataset = str(case.get('dataset', case.get('dataset_id', identity)))
        match = None
        for position, candidate in enumerate(raw_results):
            if position in used:
                continue
            identifiers = {str(candidate.get('id', '')), str(candidate.get('case_id', ''))}
            if identity in identifiers:
                match, matched_position = candidate, position
                break
        if match is None:
            for position, candidate in enumerate(raw_results):
                if position not in used and str(candidate.get('dataset', '')) == dataset and canonical_version(candidate.get('version')) == version and candidate.get('kind', 'full_cli') == case.get('kind', 'full_cli'):
                    match, matched_position = candidate, position
                    break
        if match is not None:
            used.add(matched_position)
        result = match or {}
        state = result.get('status') or ('running' if str(status.get('active_case_id', '')) == identity else 'pending')
        validation = result.get('validation', {}) or {}
        eligible = state == 'complete' and validation.get('passed') is True
        memory = result.get('memory', {}) or {}
        timing = result.get('gnu_time', {}) or {}
        wall, wall_source, utc_interval, monotonic_wall = reported_wall_time(result)
        row = {
            'id': identity, 'case_id': result.get('case_id', identity), 'dataset': dataset,
            'kind': str(case.get('kind', result.get('kind', 'full_cli'))), 'category': case.get('category', ''), 'stage': case.get('stage', result.get('stage', '')), 'dataset_label': case.get('dataset_label', dataset), 'version': version,
            'commit': case.get('commit', case.get('source_commit', COMMITS.get(version, ''))),
            'status': state, 'validation_passed': validation.get('passed'), 'eligible': eligible,
            'wall_seconds': wall, 'wall_time_source': wall_source, 'utc_interval_seconds': utc_interval, 'runner_monotonic_wall_seconds': monotonic_wall,
            'user_cpu_seconds': number(timing.get('user_cpu_seconds')),
            'system_cpu_seconds': number(timing.get('system_cpu_seconds')),
            'peak_descendant_pss_bytes': number(memory.get('peak_descendant_pss_bytes')),
            'peak_descendant_rss_bytes': number(memory.get('peak_descendant_rss_bytes')),
            'max_single_process_rss_kib': number(timing.get('max_single_process_rss_kib')),
            'sample_interval_seconds': number(memory.get('sample_interval_seconds')),
            'memory_samples': memory.get('samples'), 'pss_complete_samples': memory.get('pss_complete_samples'),
            'observed_edges': validation.get('observed_nonempty_noncomment_lines'),
            'phase_rows': result.get('process_class_summary', []) or [],
            'errors': result.get('errors', []), 'warnings': result.get('warnings', []),
            'profiles': case.get('profiles', case.get('samples')),
            'genes': case.get('genes', case.get('features')),
            'hubs': case.get('hubs_count', case.get('hub_count', case.get('hubs', case.get('regulators')))),
            'result': result, 'plan_case': case,
        }
        if row['kind'] == 'matched_native' and result.get('paths', {}).get('stdout'):
            log_path = local_path(result['paths']['stdout'])
            if log_path.is_file():
                text = log_path.read_text(encoding='utf-8', errors='replace')
                mi = re.search(r'Gene:\s*\d+\s+Time:\s*([\d.]+)', text)
                dpi = re.search(r'DPI running time is:\s*([\d.]+)', text)
                row['reported_mi_seconds'] = float(mi.group(1)) if mi else None
                row['reported_dpi_seconds'] = float(dpi.group(1)) if dpi else None
        rows.append(row)
    return rows


def apply_concurrent_workloads(rows, receipt):
    """Annotate performance conditions without changing validation or values."""
    if receipt and (not isinstance(receipt, dict) or receipt.get('schema') != 'sjaracne-performance-concurrent-workloads-v1'):
        raise ValueError('Unrecognized concurrent-workloads receipt schema')
    events = receipt.get('events', []) if receipt else []
    if not isinstance(events, list):
        raise ValueError('Concurrent-workloads events must be an array')
    by_id = {row['id']: row for row in rows}
    for row in rows:
        row.update(concurrent_workload=False, concurrent_workload_started_utc=None,
                   performance_comparability='Sequential benchmark batch', concurrency_events=[])
    for event in events:
        if not isinstance(event, dict) or event.get('affected_case_id') not in by_id or not event.get('started_utc'):
            raise ValueError('Concurrent-workloads event lacks a known case or start time')
        row = by_id[event['affected_case_id']]
        row['concurrent_workload'] = True
        row['concurrency_events'].append(event)
        row['concurrent_workload_started_utc'] = min(x['started_utc'] for x in row['concurrency_events'])
        row['performance_comparability'] = 'Partly concurrent external workload; timing is not an isolated comparison'
    return rows


def case_version_label(row, plot=False):
    label = VERSION_LABELS.get(row['version'], row['version'])
    if row.get('concurrent_workload'):
        label += ('\n(concurrent load)' if plot else ' [concurrent load]')
    return label


def dataset_order(rows):
    return list(dict.fromkeys(row['dataset'] for row in rows))


def version_order(rows):
    found = list(dict.fromkeys(row['version'] for row in rows))
    return [value for value in VERSIONS if value in found] + [value for value in found if value not in VERSIONS]


def display_state(row):
    if row['validation_passed'] is False:
        return 'Validation failed' if row['status'] == 'complete' else str(row['status']).replace('_', ' ').title()
    if row['status'] == 'complete' and row['validation_passed'] is None:
        return 'Complete, unvalidated'
    return {'complete': 'Complete', 'running': 'Running', 'pending': 'Pending', 'failed': 'Failed', 'interrupted': 'Interrupted'}.get(row['status'], str(row['status']).replace('_', ' ').title())


def dataset_title(dataset, rows):
    candidates = [row for row in rows if row['dataset'] == dataset]
    source = candidates[0] if candidates else {}
    title = source.get('dataset_label', dataset).replace('_', ' ')
    counts = []
    for key, label in [('profiles', 'profiles'), ('genes', 'genes'), ('hubs', 'hubs')]:
        value = source.get(key)
        if number(value) is not None:
            counts.append(f'{int(float(value)):,} {label}')
    return title + ('\n' + ' / '.join(counts) if counts else '')


def save_figure(figure, directory, stem):
    directory.mkdir(parents=True, exist_ok=True)
    for extension in ('png', 'pdf', 'svg'):
        kwargs = {'dpi': 180} if extension == 'png' else {}
        figure.savefig(directory / f'{stem}.{extension}', bbox_inches='tight', **kwargs)
    plt.close(figure)
    # Matplotlib SVG text has incidental XML whitespace; keep repository diffs clean.
    path = directory / f'{stem}.svg'
    write_text(path, '\n'.join(line.rstrip() for line in path.read_text(encoding='utf-8').splitlines()) + '\n')


def metric_plot(rows, directory, stem, key, title, unit, divisor, versions):
    datasets = dataset_order(rows)
    figure, axes = plt.subplots(len(datasets) or 1, 1, figsize=(10.8, max(3.8, 3.5 * len(datasets))), squeeze=False)
    for axis, dataset in zip(axes.flat, datasets):
        data = {row['version']: row for row in rows if row['dataset'] == dataset}
        values = [data.get(v, {}).get(key) for v in versions]
        visible = [(v, data[v][key] / divisor) for v in versions if v in data and data[v]['eligible'] and number(data[v].get(key)) is not None]
        largest = max([val for _, val in visible], default=0)
        extent = largest * 1.30 if largest > 0 else 1.0
        axis.set_xlim(0, extent)
        for y, version in enumerate(versions):
            row = data.get(version)
            value = row.get(key) if row else None
            if row and row['eligible'] and number(value) is not None:
                plotted = value / divisor
                axis.barh(y, plotted, color=COLORS.get(version, '#777777'), height=0.57, hatch='//' if row.get('concurrent_workload') else None)
                label = seconds_label(value) if unit == 'minutes' else f'{plotted:.3f} GiB'
                axis.text(plotted + extent * .015, y, label, va='center', fontsize=9)
            else:
                label = display_state(row) if row and not row['eligible'] else 'Not recorded'
                axis.text(extent * .025, y, label, va='center', color='#666666', fontsize=10, fontstyle='italic')
        axis.set_yticks(range(len(versions)), [case_version_label(data[v], plot=True) if v in data else VERSION_LABELS.get(v, v) for v in versions], fontsize=10)
        axis.set_ylim(len(versions) - .4, -.6)
        axis.set_title(dataset_title(dataset, rows), loc='left', fontsize=11, weight='bold', pad=12)
        axis.set_xlabel(('Minutes' if unit == 'minutes' else unit) if visible else 'Measurements pending or unavailable')
        if not visible:
            axis.set_xticks([])
        axis.grid(axis='x', alpha=.18)
        axis.set_axisbelow(True)
        axis.spines[['top', 'right']].set_visible(False)
    if not datasets:
        axes.flat[0].text(.5, .5, 'No cases in plan', ha='center', va='center')
        axes.flat[0].axis('off')
    figure.suptitle(title, x=.02, ha='left', fontsize=14, weight='bold')
    figure.text(.02, .012, 'Complete, validated cases only; unfinished values are not zero.' + (' Hatched bars: partly concurrent workload; not isolated timings.' if any(row.get('concurrent_workload') for row in rows) else ''), fontsize=8.5, color='#555555')
    figure.tight_layout(rect=(0, .035, 1, .95))
    save_figure(figure, directory, stem)


def phase_plot(rows, directory, versions):
    datasets = dataset_order(rows)
    phases = list(dict.fromkeys(str(phase['phase']) for row in rows for phase in row['phase_rows'] if phase.get('phase') in {'native_mi', 'native_mi_and_dpi', 'native_consensus_and_dpi', 'python_consensus', 'python_enhancement', 'python_export', 'python_consensus_and_enhancement'}))
    figure, axes = plt.subplots(len(datasets) or 1, len(versions) or 1, figsize=(max(10.8, 4.1 * len(versions)), max(4.2, max(3.7, .42 * max(1, len(phases))) * len(datasets))), squeeze=False)
    for i, dataset in enumerate(datasets):
        relevant = [row for row in rows if row['dataset'] == dataset]
        row_maximum = max([number(phase.get('union_sampled_active_seconds')) or 0 for row in relevant if row['eligible'] for phase in row['phase_rows']], default=0) / 60
        extent = row_maximum * 1.25 if row_maximum > 0 else 1.0
        data = {row['version']: row for row in relevant}
        for j, version in enumerate(versions):
            axis = axes[i, j]
            row = data.get(version)
            entries = {str(phase['phase']): phase for phase in row['phase_rows']} if row else {}
            axis.set_xlim(0, extent)
            for y, phase in enumerate(phases):
                value = number(entries.get(phase, {}).get('union_sampled_active_seconds'))
                if row and row['eligible'] and value is not None:
                    axis.barh(y, value / 60, height=.6, color=PHASE_COLORS[y % len(PHASE_COLORS)])
                    axis.text(value / 60 + extent * .02, y, seconds_label(value), va='center', fontsize=8)
                else:
                    axis.text(extent * .025, y, 'Not observed' if row and row['eligible'] else (display_state(row) if row else 'Pending'), va='center', fontsize=8, color='#777777', fontstyle='italic')
            axis.set_yticks(range(len(phases)), [p.replace('_', ' ') for p in phases], fontsize=8)
            axis.set_ylim(max(len(phases), 1) - .4, -.6)
            axis.set_title(f'{dataset.replace("_", " ")}\n' + (case_version_label(row, plot=True) if row else VERSION_LABELS.get(version, version)), loc='left', fontsize=10, weight='bold')
            axis.set_xlabel('Sampled active minutes')
            if not phases or row_maximum <= 0:
                axis.set_xticks([])
            if not phases:
                axis.text(.04, .5, 'Phase measurements pending', transform=axis.transAxes, color='#777777', fontstyle='italic')
            axis.grid(axis='x', alpha=.18)
            axis.set_axisbelow(True)
            axis.spines[['top', 'right']].set_visible(False)
    figure.suptitle('Approximate process activity by phase', x=.02, ha='left', fontsize=14, weight='bold')
    figure.text(.02, .012, 'Intervals are unions of sampled process activity within each phase. Scientific classes only; adapter activity is in phases.tsv. Phases overlap: do not add these bars.', fontsize=8.5, color='#555555')
    figure.tight_layout(rect=(0, .04, 1, .94))
    save_figure(figure, directory, 'phase_activity')



def component_plot(rows, directory, stem, key, title, unit, divisor):
    """Show component cases separately; never replace them with pipeline totals."""
    datasets = dataset_order(rows)
    figure, axes = plt.subplots(len(datasets) or 1, 1, figsize=(11.5, max(4.0, 4.2 * len(datasets))), squeeze=False)
    for axis, dataset in zip(axes.flat, datasets):
        selected = [row for row in rows if row['dataset'] == dataset]
        valid = [row[key] / divisor for row in selected if row['eligible'] and number(row.get(key)) is not None]
        extent = max(valid, default=0) * 1.28 if valid and max(valid) > 0 else 1.0
        axis.set_xlim(0, extent)
        labels = []
        for y, row in enumerate(selected):
            labels.append(row['version'] + ' / ' + str(row['stage']).replace('_', ' '))
            value = number(row.get(key))
            if row['eligible'] and value is not None:
                axis.barh(y, value / divisor, color=COLORS.get(row['version'], '#777777'), height=.57)
                label = seconds_label(value) if unit == 'minutes' else f'{value / divisor:.3f} GiB'
                axis.text(value / divisor + extent * .015, y, label, va='center', fontsize=9)
            else:
                axis.text(extent * .025, y, display_state(row) if not row['eligible'] else 'Not recorded', va='center', color='#666666', fontsize=9, fontstyle='italic')
        axis.set_yticks(range(len(selected)), labels, fontsize=9)
        axis.set_ylim(len(selected) - .4, -.6)
        axis.set_title(dataset_title(dataset, rows), loc='left', fontsize=11, weight='bold', pad=12)
        axis.set_xlabel(('Minutes' if unit == 'minutes' else unit) if valid else 'Measurements pending or unavailable')
        if not valid:
            axis.set_xticks([])
        axis.grid(axis='x', alpha=.18)
        axis.set_axisbelow(True)
        axis.spines[['top', 'right']].set_visible(False)
    if not datasets:
        axes.flat[0].text(.5, .5, 'No component replays in plan', ha='center', va='center')
        axes.flat[0].axis('off')
    figure.suptitle(title, x=.02, ha='left', fontsize=14, weight='bold')
    figure.text(.02, .012, 'Saved 100-resample graphs; MI inference excluded. Components are not full workflows and are not summed.', fontsize=8.5, color='#555555')
    figure.tight_layout(rect=(0, .035, 1, .95))
    save_figure(figure, directory, stem)


def component_table(rows):
    if not rows:
        return 'No component replays are included in the plan.'
    table = []
    for row in rows:
        valid = row['eligible']
        table.append([row['dataset'], row['version'], str(row['stage']).replace('_', ' '), display_state(row), format_num(row['wall_seconds'] / 60 if valid and row['wall_seconds'] is not None else None), row['wall_time_source'] if valid else 'NA', format_num(row['peak_descendant_pss_bytes'] / GIB if valid and row['peak_descendant_pss_bytes'] is not None else None, 3), format_num(row['peak_descendant_rss_bytes'] / GIB if valid and row['peak_descendant_rss_bytes'] is not None else None, 3)])
    return markdown_table(['Dataset', 'Version', 'Component', 'State', 'Wall (min)', 'Clock', 'Peak tree PSS (GiB)', 'Peak tree RSS (GiB)'], table)



def matched_native_table(rows):
    if not rows:
        return 'No matched native controls are included in the plan.'
    table = []
    for row in rows:
        valid = row['eligible']
        table.append([VERSION_LABELS.get(row['version'], row['version']), display_state(row), format_num(row['wall_seconds'] if valid else None), row['wall_time_source'] if valid else 'NA', format_num(row['max_single_process_rss_kib'] / 1024 if valid and row['max_single_process_rss_kib'] is not None else None), format_num(row.get('reported_mi_seconds') if valid else None, 0), format_num(row.get('reported_dpi_seconds') if valid else None, 0)])
    return markdown_table(['Version', 'State', 'Total native wall (s)', 'Clock', 'GNU-time peak RSS (MiB)', 'Reported MI (s)', 'Reported DPI (s)'], table)


def matched_native_plot(rows, directory, versions):
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.3))
    data = {row['version']: row for row in rows}
    for axis, key, divisor, title, unit in zip(axes, ['wall_seconds', 'max_single_process_rss_kib'], [60, 1024], ['Total native wall time', 'GNU-time single-process peak RSS'], ['Minutes', 'MiB']):
        valid = [row[key] / divisor for row in rows if row['eligible'] and number(row.get(key)) is not None]
        extent = max(valid, default=0) * 1.30 if valid and max(valid) > 0 else 1.0
        axis.set_xlim(0, extent)
        for y, version in enumerate(versions):
            row = data.get(version)
            value = row.get(key) if row else None
            if row and row['eligible'] and number(value) is not None:
                axis.barh(y, value / divisor, color=COLORS.get(version, '#777777'), height=.56)
                axis.text(value / divisor + extent * .015, y, seconds_label(value) if key == 'wall_seconds' else f'{value / divisor:.1f} MiB', va='center', fontsize=9)
            else:
                axis.text(extent * .025, y, display_state(row) if row and not row['eligible'] else 'Not recorded', va='center', fontsize=9, color='#777777', fontstyle='italic')
        axis.set_yticks(range(len(versions)), [VERSION_LABELS.get(v, v) for v in versions], fontsize=9)
        axis.set_ylim(len(versions) - .4, -.6)
        axis.set_title(title, loc='left', fontsize=11, weight='bold')
        axis.set_xlabel(unit if valid else 'Measurements pending or unavailable')
        if not valid:
            axis.set_xticks([])
        axis.grid(axis='x', alpha=.18)
        axis.set_axisbelow(True)
        axis.spines[['top', 'right']].set_visible(False)
    figure.suptitle('LUAD517 TF: matched native MI + DPI, one seed', x=.02, ha='left', fontsize=14, weight='bold')
    figure.text(.02, .012, 'Seed 101; full-size replacement bootstrap; affine p=1e-7; strict DPI epsilon=0; depth 40. No consensus.', fontsize=8.5, color='#555555')
    figure.tight_layout(rect=(0, .04, 1, .93))
    save_figure(figure, directory, 'matched_native_control')


def markdown_table(headers, body):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] + ['| ' + ' | '.join(safe_label(value) for value in line) + ' |' for line in body])


def historical_appendix(historical):
    if not historical:
        return ['Historical context was not supplied to this report build.']
    lines = ['Earlier records used different dates, storage and concurrent workloads. They are context only; no controlled speedup ratio is calculated from them.', '']
    table = []
    for row in historical.get('legacy_rows', historical.get('rows', [])):
        if row.get('dataset') not in ('BRCA100', 'LUAD517'):
            continue
        elapsed = row.get('elapsed_seconds', {})
        peak = row.get('max_rss_kib', {})
        table.append([row['id'], str(elapsed.get('n', 'NA')), format_num(elapsed.get('median')), format_num(peak.get('median') / 1024 if peak.get('median') is not None else None)])
    if table:
        lines += [markdown_table(['Historical v0.3.0-equivalent arm', 'Timed seeds', 'Median native MI + DPI (s)', 'Median single-process peak RSS (MiB)'], table), '', 'LUAD RSS was not recorded. BRCA100 RSS is GNU-time lifetime maximum per native process. Summed per-seed elapsed times are not pipeline wall time.', '']
    replay = historical.get('modern_historical_appendix', {}).get('recovery_stages', [])
    table = []
    for row in replay:
        if row.get('id') != 'LUAD517_SIG':
            continue
        for phase, value in row.get('stages', {}).items():
            table.append([row['id'], phase.replace('_', ' '), format_num(value.get('elapsed_seconds') / 60 if value.get('elapsed_seconds') is not None else None)])
    if table:
        lines += [markdown_table(['Historical sequential replay', 'Stage', 'Minutes'], table), '', 'This replay used saved 100-resample MI graphs on D: HDD and a pre-release sequential reader. It excludes MI inference and earlier interrupted work, and has no matched lifetime peak-memory measurement. NetBID2 QC is listed separately from inference.']
    return lines


def build_markdown(plan, status, rows, historical, generated, version_ordering, hardware=None):
    all_rows = rows
    components = [row for row in rows if row['kind'] == 'component']
    matched = [row for row in rows if row['kind'] == 'matched_native']
    rows = [row for row in rows if row['kind'] == 'full_cli']
    complete = sum(row['eligible'] for row in rows)
    machine = hardware or {}
    model = re.search(r'model name\s*:\s*(.+)', machine.get('cpu_first_block', ''))
    total_memory = next((number(line.split(':', 1)[1].split()[0]) for line in machine.get('memory', []) if line.startswith('MemTotal:')), None)
    machine_table = markdown_table(['Execution setting', 'Value'], [['CPU', model.group(1).strip() if model else 'See hardware receipt'], ['Affinity', ', '.join(map(str, plan.get('cpu_affinity', []))) + ' (logical CPU IDs)'], ['Memory visible to WSL', f'{total_memory / 1024**2:.2f} GiB' if total_memory is not None else 'See hardware receipt'], ['Storage', plan.get('storage', 'See plan')], ['Repetitions', str(plan.get('repeat_count', 1))]])
    lines = ['# SJARACNe performance: 4cd8eae, v0.3.0 and v0.4.0', '', f'Updated {generated}. **{complete} of {len(rows)} full CLI cases completed and passed output validation.** Component replays: **{sum(row["eligible"] for row in components)} of {len(components)}** complete. Matched native controls: **{sum(row["eligible"] for row in matched)} of {len(matched)}** complete. Runner state: `{status.get("state", "not started")}`.', '',
        'This benchmark compares the complete CLI workflows and their default scientific profiles on matched inputs. Changes in sampling, MI calibration, consensus and DPI are part of the comparison; full-workflow results do not isolate C++ optimization.', '',
        '## Versions and methods', '',
        markdown_table(['Version', 'Pinned commit', 'Scientific process'], [
            ['[SJARACNe 4cd8eae](https://github.com/jyyulab/SJARACNe/commit/' + COMMITS['commit_4cd8eae'] + ')', '`4cd8eae`', 'Full-size replacement bootstraps; strict DPI per resample; historical probability consensus.'],
            ['[SJARACNe v0.3.0](https://github.com/jyyulab/SJARACNe/releases/tag/v0.3.0)', '`12113fbc`', 'Full-size replacement bootstraps; strict DPI per resample; historical probability consensus.'],
            ['[SJARACNe2 v0.4.0](https://github.com/adamdingliang/SJARACNe2/releases/tag/v0.4.0)', '`8c0c1e0`', '100 x 80% resamples without replacement; K20 candidates; supporting-run mean MI; DPI with offset 0.025.'],
        ]), '',
        'The upstream v0.3.0 tag still contains package metadata version 0.2.1. Exact commits and source fingerprints identify the tested versions. The linked SJARACNe2 release is **v0.4.0**.', '',
        '## Inputs and execution', '',
        'Cases use the same expression and hub files across versions. Build, installation, input staging, report generation and NetBID2 QC are excluded from timing. Each full CLI case includes the CLI invocation and workflow overhead. Benchmark cases run sequentially with the same four-worker limit and storage placement; any concurrent external workload is identified below and on affected rows; native controls and component replays use one worker. Numerical-library thread limits are one. Page caches are not forcibly cleared, so run order and cache effects remain. One repetition per case makes this an exploratory performance comparison.', '',
    ]
    lines += [machine_table, '']
    concurrent = [row for row in all_rows if row.get('concurrent_workload')]
    if concurrent:
        lines += ['**Concurrent-workload exception:** MIBC372 reconstruction was started alongside the remaining original-commit LUAD workflow at user request. The affected case is marked **[concurrent load]** in tables and plots. The CPU affinity masks are disjoint, while cache, memory bandwidth, power and SSD remain shared. Its observed values and output validation remain available; its timing is excluded from isolated cross-version rankings. The completed v0.3.0 and v0.4.0 LUAD measurements retain their sequential execution conditions.', '',
                  markdown_table(['Affected case', 'Concurrent work started (UTC)', 'Benchmark logical CPUs', 'MIBC372 logical CPUs'], [[row['id'], event['started_utc'], ', '.join(map(str, event.get('benchmark_cpu_affinity', []))), ', '.join(map(str, event.get('cpu_affinity', [])))] for row in concurrent for event in row['concurrency_events']]), '',
                  'See the [concurrent-workload receipt](concurrent_workloads.json). The start marks release into preflight and includes source checks, build, inference and QC, so no unaffected segment is substituted for the full-case time.', '']
    case_table = []
    for dataset in dataset_order(rows):
        row = next(row for row in rows if row['dataset'] == dataset)
        case_table.append([dataset, row['category'].replace('_', ' '), str(row['profiles'] or 'See plan'), str(row['genes'] or 'See plan'), str(row['hubs'] or 'See plan')])
    lines += [markdown_table(['Dataset', 'Scope', 'Profiles', 'Genes', 'Hubs'], case_table), '',
        'The bundled sparse T-cell test fixture is included to examine computational behavior on sparse inputs. Its cell provenance and independent biological ground truth have not been established. It is **not a validated scRNA-seq benchmark**, and these timings do not establish single-cell inference accuracy or performance across other scRNA-seq datasets.', '',
        '## Overall comparison', '',
    ]
    values = []
    for row in rows:
        valid = row['eligible']
        cpu = row['user_cpu_seconds'] + row['system_cpu_seconds'] if row['user_cpu_seconds'] is not None and row['system_cpu_seconds'] is not None else None
        values.append([row['dataset'], case_version_label(row), display_state(row), format_num(row['wall_seconds'] / 60 if valid and row['wall_seconds'] is not None else None), row['wall_time_source'] if valid else 'NA', format_num(cpu / 60 if valid and cpu is not None else None), format_num(row['peak_descendant_pss_bytes'] / GIB if valid and row['peak_descendant_pss_bytes'] is not None else None, 3), format_num(row['peak_descendant_rss_bytes'] / GIB if valid and row['peak_descendant_rss_bytes'] is not None else None, 3), format_num(row['max_single_process_rss_kib'] / 1024**2 if valid and row['max_single_process_rss_kib'] is not None else None, 3)])
    lines += [markdown_table(['Dataset', 'Version', 'State', 'Wall (min)', 'Clock', 'CPU (min)', 'Peak tree PSS (GiB)', 'Peak tree RSS (GiB)', 'Largest-process RSS (GiB)'], values), '',
        '`NA` means pending, unavailable or excluded because the case failed. Failed or interrupted elapsed times are not treated as completed pipeline measurements.', '',
        '**Clock basis:** primary wall time is GNU-time elapsed seconds, checked against the UTC start/finish interval. If GNU time is unavailable, the report uses a valid UTC interval, then the runner monotonic value as a labelled last fallback. In the three completed sparse-fixture cases, the recorded Python monotonic durations were about 2.5% shorter than GNU time, while GNU time and UTC agreed within 0.014 seconds. The cause has not been established. Raw measurements are unchanged; the Clock column and TSV fields retain the selected source and original clocks. Sampled phase activity remains approximate runner-clock activity.', '',
        'PSS divides shared resident pages among processes and is the preferred process-memory comparison. RSS sums process resident sets and can count shared pages more than once. Both tree peaks are sampled at 0.5-second intervals and can miss short peaks. They exclude the filesystem page cache and the rest of Windows/WSL. GNU-time RSS is the lifetime maximum of the largest individual process, not simultaneous memory across all workers. Memory scheduling requests are not measured usage.', '',
        '![Complete workflow wall time](figures/overall_wall_time.png)', '',
        '![Sampled peak process-tree PSS](figures/peak_process_tree_pss.png)', '',
        '![Sampled peak process-tree RSS](figures/peak_process_tree_rss.png)', '',
        '## Matched native control', '',
        'A separate LUAD517 TF control runs one native seed (101) with identical full-size replacement sampling, affine MI cutoff at p=1e-7, strict DPI tolerance 0 and depth 40 in all three versions. This isolates the native MI/DPI implementation more closely than the default-workflow comparison. It excludes consensus and workflow overhead. One seed is exploratory and is **not extrapolated to a measured 100-resample pipeline time**.', '',
        matched_native_table(matched), '',
        'The native MI and DPI columns come from integer-second `std::time` (CLOCK_REALTIME) messages inside the executable; they exclude input loading and output writing. They need not sum to total measured native process time.', '',
        '![Matched native control](figures/matched_native_control.png)', '',
        '## Component replays', '',
        'These BRCA100 TF/SIG replays reuse the frozen 100-resample graphs for each method. They measure original release functions in fresh processes, or the native consensus/DPI executable, without rerunning MI. Runtime includes that component process and imports. Graph staging and validation are excluded. These are **component measurements, not reconstructed full-pipeline timings**. Different output density is part of the released scientific methods.', '',
        component_table(components), '',
        '![Component wall time](figures/component_wall_time.png)', '',
        '![Component peak process-tree PSS](figures/component_peak_pss.png)', '',
        '![Component peak process-tree RSS](figures/component_peak_rss.png)', '',
        '## Step-level LUAD comparison', '',
        '[Step-level tables, figures and reproducible analysis](steps/README.md) compare the three completed LUAD workflows using their existing logs and sampled process records. The comparison maps MI and DPI to their actual positions in each workflow, and reports peak process-tree PSS during each observed step.', '',
        '![Observed step durations](steps/figures/step_durations.png)', '',
        '![Peak workflow PSS during each step](steps/figures/step_peak_pss.png)', '',
        'Step durations use the original sampler clock and are approximate; full-workflow wall times above use GNU time. The observed clock difference is documented in the step report. Steps can overlap and should not be added to reconstruct total runtime.', '',
        'The original [generic process-class table](phases.tsv) and [activity figure](figures/phase_activity.png) remain diagnostic records. Their coarse classifier included the v0.3.0 module-based Python consensus under the workflow-controller class. The step report identifies that command correctly and supersedes those generic labels for scientific-stage interpretation.', '',
        '## Interpretation', '',
    ]
    all_complete = bool(rows) and complete == len(rows)
    if not all_complete:
        lines += ['The benchmark is still running or has incomplete cases. **No overall winner is assigned until all matched cases finish and validate.** Completed cases can be inspected independently; pending bars are not zeros.', '']
    else:
        for dataset in dataset_order(rows):
            group = [row for row in rows if row['dataset'] == dataset]
            if any(row.get('concurrent_workload') for row in group):
                affected = ', '.join(case_version_label(row) for row in group if row.get('concurrent_workload'))
                lines += [f'For **{dataset}**, {affected} ran partly under concurrent external load. Its measured values are retained, but this report assigns no cross-version workflow winner for that dataset. The sequential v0.3.0 and v0.4.0 cases can be compared independently.', '']
                continue
            fastest = min(group, key=lambda row: row['wall_seconds'] if row['wall_seconds'] is not None else float('inf'))
            pss = [row for row in group if row['peak_descendant_pss_bytes'] is not None]
            text = f'For **{dataset}**, {VERSION_LABELS.get(fastest["version"], fastest["version"])} had the shortest observed workflow time ({seconds_label(fastest["wall_seconds"])}).'
            if pss:
                lowest = min(pss, key=lambda row: row['peak_descendant_pss_bytes'])
                text += f' The lowest observed peak process-tree PSS was {lowest["peak_descendant_pss_bytes"] / GIB:.3f} GiB with {VERSION_LABELS.get(lowest["version"], lowest["version"])}.'
            lines += [text, '']
        lines += ['These observations apply to this machine, storage, concurrency and input set. One repetition does not estimate run-to-run variation. Changes in network density and scientific defaults can change both runtime and memory; timing alone does not rank network quality.', '']
    errors = [(row, message) for row in all_rows for message in row['errors']]
    warnings = [(row, message) for row in all_rows for message in row['warnings']]
    if errors or warnings:
        lines += ['## Recorded issues', '']
        for row, message in errors:
            lines.append(f'- **{row["id"]}:** {safe_label(message)}')
        for row, message in warnings:
            lines.append(f'- {row["id"]}: {safe_label(message)}')
        lines += ['']
    lines += ['## Historical context', ''] + historical_appendix(historical) + ['', '## Files and reproducibility', '',
        '- [Full CLI measurements](overall.tsv), [component measurements](components.tsv), [matched native controls](matched_native.tsv), [phase measurements](phases.tsv), and [plot values](plot_values.tsv).',
        '- [Report provenance](report_provenance.json) records input JSON fingerprints and metric definitions.',
        '- Each figure is provided as PNG, PDF and SVG in [figures/](figures/).',
        '- Raw expressions, resample graphs, environments and workflow scratch remain outside this repository.',
        '- Rebuild with the runner JSON files:', '',
        '```powershell', 'python build_report.py --plan PATH_TO_PLAN_JSON --measurements PATH_TO_MEASUREMENTS_JSON --status PATH_TO_STATUS_JSON', '```', '',
    ]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--measurements', required=True)
    parser.add_argument('--status', required=True)
    parser.add_argument('--historical')
    parser.add_argument('--output-dir', '--outputdir', dest='output_dir', default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    plan_path, measurement_path, status_path = map(local_path, (args.plan, args.measurements, args.status))
    plan = read_json(plan_path)
    if not isinstance(plan, dict):
        raise ValueError('Plan must be an existing JSON object')
    measurements = read_json(measurement_path, {})
    status = read_json(status_path, {})
    historical_path = local_path(args.historical or plan.get('historical_context') or plan.get('historical_evidence')) if (args.historical or plan.get('historical_context') or plan.get('historical_evidence')) else None
    if historical_path is None:
        for candidate in (plan_path.parent / 'historical_evidence.json', plan_path.parent.parent / 'historical_evidence.json'):
            if candidate.is_file():
                historical_path = candidate
                break
    historical = read_json(historical_path, {})
    hardware_path = plan_path.parent / 'hardware.json'
    hardware = read_json(hardware_path, {})
    concurrency_path = plan_path.parent / 'concurrent_workloads.json'
    concurrency = read_json(concurrency_path, {})
    output = local_path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = apply_concurrent_workloads(normalized_rows(plan, measurements, status), concurrency)
    if concurrency_path.is_file():
        (output / 'concurrent_workloads.json').write_bytes(concurrency_path.read_bytes())
    full_rows = [row for row in rows if row['kind'] == 'full_cli']
    matched_rows = [row for row in rows if row['kind'] == 'matched_native']
    component_rows = [row for row in rows if row['kind'] == 'component']
    versions = version_order(full_rows)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.fonttype': 'none', 'axes.titlelocation': 'left', 'pdf.fonttype': 42, 'ps.fonttype': 42})
    figures = output / 'figures'
    metric_plot(full_rows, figures, 'overall_wall_time', 'wall_seconds', 'Complete workflow wall time', 'minutes', 60, versions)
    metric_plot(full_rows, figures, 'peak_process_tree_pss', 'peak_descendant_pss_bytes', 'Sampled peak process-tree PSS', 'GiB', GIB, versions)
    metric_plot(full_rows, figures, 'peak_process_tree_rss', 'peak_descendant_rss_bytes', 'Sampled peak process-tree RSS', 'GiB', GIB, versions)
    phase_plot(full_rows, figures, versions)
    matched_native_plot(matched_rows, figures, versions)
    component_plot(component_rows, figures, 'component_wall_time', 'wall_seconds', 'Component wall time', 'minutes', 60)
    component_plot(component_rows, figures, 'component_peak_pss', 'peak_descendant_pss_bytes', 'Component sampled peak process-tree PSS', 'GiB', GIB)
    component_plot(component_rows, figures, 'component_peak_rss', 'peak_descendant_rss_bytes', 'Component sampled peak process-tree RSS', 'GiB', GIB)
    overall_fields = ['id', 'case_id', 'dataset', 'kind', 'category', 'stage', 'version', 'commit', 'status', 'validation_passed', 'concurrent_workload', 'concurrent_workload_started_utc', 'performance_comparability', 'wall_seconds', 'wall_time_source', 'utc_interval_seconds', 'runner_monotonic_wall_seconds', 'user_cpu_seconds', 'system_cpu_seconds', 'reported_mi_seconds', 'reported_dpi_seconds', 'peak_descendant_pss_bytes', 'peak_descendant_rss_bytes', 'max_single_process_rss_kib', 'sample_interval_seconds', 'memory_samples', 'pss_complete_samples', 'observed_edges']
    write_tsv(output / 'overall.tsv', full_rows, overall_fields)
    write_tsv(output / 'components.tsv', component_rows, overall_fields)
    write_tsv(output / 'matched_native.tsv', matched_rows, overall_fields)
    phases = [{**{'id': row['id'], 'dataset': row['dataset'], 'version': row['version']}, **phase} for row in rows for phase in row['phase_rows']]
    write_tsv(output / 'phases.tsv', phases, ['id', 'dataset', 'version', 'phase', 'process_count', 'union_sampled_active_seconds', 'sum_sampled_process_seconds', 'peak_single_process_rss_bytes', 'peak_single_process_pss_bytes'])
    plot_rows = [{'id': row['id'], 'dataset': row['dataset'], 'version': row['version'], 'kind': row['kind'], 'stage': row['stage'], 'metric': key, 'value': row[key] if row['eligible'] else None, 'metric_source': row['wall_time_source'] if key == 'wall_seconds' else 'Sampled process tree', 'status': row['status'], 'validation_passed': row['validation_passed'], 'concurrent_workload': row['concurrent_workload'], 'concurrent_workload_started_utc': row['concurrent_workload_started_utc'], 'performance_comparability': row['performance_comparability']} for row in rows for key in ['wall_seconds', 'peak_descendant_pss_bytes', 'peak_descendant_rss_bytes']]
    write_tsv(output / 'plot_values.tsv', plot_rows, ['id', 'dataset', 'kind', 'stage', 'version', 'metric', 'value', 'metric_source', 'status', 'validation_passed', 'concurrent_workload', 'concurrent_workload_started_utc', 'performance_comparability'])
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    markdown = build_markdown(plan, status, rows, historical, generated, versions, hardware)
    write_text(output / 'README.md', markdown)
    paths = {'plan': plan_path, 'measurements': measurement_path, 'status': status_path, 'historical': historical_path, 'hardware': hardware_path, 'concurrent_workloads': concurrency_path}
    provenance = {'schema': 'sjaracne-performance-report-v1', 'generated_utc': generated, 'builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'inputs': {name: {'path': str(path), 'exists': path.exists(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None} for name, path in paths.items() if path is not None}, 'case_count': len(rows), 'completed_validated_cases': sum(row['eligible'] for row in rows), 'case_kinds': {kind: sum(row['kind'] == kind for row in rows) for kind in ['full_cli', 'component', 'matched_native']}, 'metric_definitions': {**(measurements.get('metric_definitions', {}) if isinstance(measurements, dict) else {}), 'wall_seconds': 'Report primary wall time: finite GNU-time elapsed seconds; fallback valid UTC finish-start interval; fallback unchanged runner monotonic seconds. See wall_time_source.', 'runner_monotonic_wall_seconds': 'Original unmodified measurements.results[*].wall_seconds.', 'utc_interval_seconds': 'UTC finished_utc minus started_utc when valid and nonnegative.'}, 'raw_measurement_metric_definitions': measurements.get('metric_definitions', {}) if isinstance(measurements, dict) else {}, 'wall_clock_selection': {'preference_order': ['gnu_time.elapsed_seconds', 'UTC finished_utc-started_utc', 'raw wall_seconds monotonic fallback'], 'raw_measurements_modified': False, 'observed_clock_difference_cause': 'Not established'}, 'phase_intervals_are_not_additive': True, 'missing_values_are_not_zero': True, 'default_method_comparison_not_pure_implementation_speedup': True, 'concurrent_workload_events': concurrency.get('events', []), 'concurrent_cases_excluded_from_isolated_rankings': [row['id'] for row in rows if row.get('concurrent_workload')]}
    write_text(output / 'report_provenance.json', json.dumps(provenance, indent=2) + '\n')
    print(json.dumps({'state': 'report_built', 'output': str(output), 'cases': len(rows), 'completed_validated': sum(row['eligible'] for row in rows), 'figures': 8, 'formats_per_figure': 3}))


if __name__ == '__main__':
    main()