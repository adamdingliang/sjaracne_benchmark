#!/usr/bin/env python3
"""Measure sequential, pinned commands without changing their implementations.

Usage: python run_benchmark.py PLAN.json --output-dir RESULTS [--check-only]
       python run_benchmark.py PLAN.json --output-dir RESULTS --resume

A plan has ``cases`` with id, dataset, version, kind, command (argv array), cwd,
optional env, expected_files, depends_on, stage, and expected_min_edges. Top-level env is
merged before each case's env. Optional report_command/report_cwd runs after each
result and final status. Relative expected_files are resolved against case cwd.
expected_min_edges counts nonempty, noncomment lines of the first expected file;
it is a basic output sanity check, not a biological edge-accuracy assessment.

Each command runs under GNU time in its own session. Every 0.5 s, psutil samples
the wrapper and all visible descendants. Aggregate PSS/RSS peaks are sampled;
GNU time max RSS is the largest individual process, not process-tree peak RAM.
Process-phase activity is inferred from argv and polling intervals. Phases can
overlap and must not be summed as exact pipeline step durations.

--check-only reads/validates plan, directories, executables and measurement tools;
it does not start commands or create output directories. --resume requires the
identical plan bytes, retains all existing evidence, and skips recorded cases.
Interrupted unrecorded cases receive a new attempt directory on resumption.
"""
from __future__ import annotations

import argparse
import collections
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback

SCHEMA = 'sjaracne-performance-measurements-v1'
INTERVAL = 0.5
GNU_TIME = '/usr/bin/time'
METRIC_DEFINITIONS = {
    'wall_seconds': 'Monotonic elapsed seconds from Popen through wait; excludes validation and report building.',
    'gnu_time.max_single_process_rss_kib': 'GNU time maximum resident set size in KiB; largest individual process, not summed scatter-worker RAM.',
    'memory.peak_descendant_rss_bytes': 'Maximum sampled sum of RSS of GNU time wrapper plus visible descendants; shared pages may be counted more than once.',
    'memory.peak_descendant_pss_bytes': 'Maximum sampled sum of PSS at samples where every observed process supplied PSS; excludes unmapped filesystem cache and kernel memory.',
    'memory.sample_interval_seconds': 'Target polling interval; short-lived processes/brief memory spikes can be missed. Actual timestamps are retained.',
    'process_class_summary': 'Argv-inferred phases. Active seconds sum polling intervals with a phase observed; phases overlap and are not exact stage wall times or additive.',
    'process_events': 'Observed PID/create-time identities, argv, first/last observations and per-process sampled memory peaks; unobserved short-lived processes are absent.',
    'expected_min_edges': 'Minimum nonempty noncomment line count of first expected file; not ground-truth accuracy.',
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + f'.tmp.{os.getpid()}')
    with temporary.open('w', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def argv(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(x, str) and x and '\x00' not in x for x in value):
        raise ValueError(f'{label} must be a nonempty argv array of strings')
    return value


def environment(plan: dict, case: dict) -> dict[str, str]:
    result = os.environ.copy()
    for label, values in [('plan.env', plan.get('env', {})), ('case.env', case.get('env', {}))]:
        if not isinstance(values, dict) or not all(isinstance(k, str) and isinstance(v, str) and '\x00' not in k + v for k, v in values.items()):
            raise ValueError(f'{label} must map strings to strings')
        result.update(values)
    # GNU time output must use the stable English keys parsed below.
    result['LC_ALL'] = 'C'
    return result


def validate_plan(plan: dict) -> None:
    if not isinstance(plan, dict) or not isinstance(plan.get('cases'), list) or not plan['cases']:
        raise ValueError('Plan must contain a nonempty cases array')
    if not Path(GNU_TIME).is_file():
        raise FileNotFoundError(GNU_TIME)
    seen = set()
    for case in plan['cases']:
        if not isinstance(case, dict):
            raise ValueError('Each case must be an object')
        identity = case.get('id')
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', identity) or identity in seen:
            raise ValueError('Case ids must be unique safe path components')
        dependencies = case.get('depends_on', [])
        if not isinstance(dependencies, list) or not all(isinstance(x, str) and x in seen for x in dependencies):
            raise ValueError(f'{identity}: depends_on must name earlier cases')
        seen.add(identity)
        for name in ['dataset', 'version', 'kind', 'cwd']:
            if not isinstance(case.get(name), str) or not case[name]:
                raise ValueError(f'{identity}: {name} must be a nonempty string')
        if not Path(case['cwd']).is_dir():
            raise FileNotFoundError(f'{identity}: cwd {case["cwd"]}')
        command = argv(case.get('command'), identity + '.command')
        env = environment(plan, case)
        if shutil.which(command[0], path=env.get('PATH')) is None:
            raise FileNotFoundError(f'{identity}: executable {command[0]}')
        expected = case.get('expected_files', [])
        if not isinstance(expected, list) or not all(isinstance(x, str) and x for x in expected):
            raise ValueError(f'{identity}: expected_files must be an array of paths')
        minimum = case.get('expected_min_edges')
        if minimum is not None and (isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0 or not expected):
            raise ValueError(f'{identity}: expected_min_edges requires first expected file and nonnegative integer')
    if 'report_command' in plan:
        argv(plan['report_command'], 'report_command')
        if not Path(plan.get('report_cwd', '.')).is_dir():
            raise FileNotFoundError('report_cwd does not exist')


def classify(command: list[str]) -> str:
    basenames = [Path(x).name.lower() for x in command]
    first = basenames[0] if basenames else ''
    joined = ' '.join(command).lower()
    if first == 'time':
        return 'measurement_wrapper'
    native = first in {'sjaracne.exe', 'aracne', 'aracne.exe'}
    if native:
        if '--consensus-inputs' in command:
            return 'native_consensus_and_dpi'
        if '--raw-mi' in command:
            return 'native_mi'
        return 'native_mi_and_dpi'
    if 'stage_worker.py' in basenames:
        for name in ['legacy_consensus', 'legacy_enhance', 'modern_export', 'modern_enhance']:
            if name in command:
                return {'legacy_consensus': 'python_consensus', 'legacy_enhance': 'python_enhancement', 'modern_export': 'python_export', 'modern_enhance': 'python_enhancement'}[name]
    if 'create_consensus_network.py' in basenames:
        return 'python_consensus_and_enhancement'
    if 'sjaracne.bin.wdl_workflow' in joined or 'wdl_workflow.py' in basenames:
        if 'prepare' in command:
            return 'workflow_preparation_adapter'
        if 'infer' in command:
            return 'workflow_inference_adapter'
        if 'consensus' in command:
            return 'workflow_consensus_and_enhancement_adapter'
    if any(x in joined for x in ['cwltool', 'sprocket', 'sjaracne']):
        return 'workflow_controller_or_adapter'
    if first == 'time':
        return 'measurement_wrapper'
    return 'other'


def parse_time(path: Path) -> dict:
    fields = {}
    if path.is_file():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            if ': ' in line:
                key, value = line.strip().rsplit(': ', 1)
                fields[key] = value.strip()
    def number(key: str, convert=float):
        try:
            return convert(fields[key])
        except (KeyError, ValueError):
            return None
    elapsed = None
    for key, value in fields.items():
        if key.startswith('Elapsed (wall clock)'):
            try:
                elapsed = 0.0
                for part in value.split(':'):
                    elapsed = elapsed * 60 + float(part)
            except ValueError:
                elapsed = None
    return {'elapsed_seconds': elapsed, 'user_cpu_seconds': number('User time (seconds)'),
            'system_cpu_seconds': number('System time (seconds)'),
            'max_single_process_rss_kib': number('Maximum resident set size (kbytes)', int),
            'raw_fields': fields}


def stop_owned_session(process: subprocess.Popen) -> None:
    """Stop only the new session owned by this case, preserving all files."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def new_attempt(case_root: Path) -> Path:
    case_root.mkdir(parents=True, exist_ok=True)
    for index in range(1, 10000):
        attempt = case_root / f'attempt_{index:03d}'
        try:
            attempt.mkdir()
            return attempt
        except FileExistsError:
            continue
    raise RuntimeError('Too many retained attempts')


def output_validation(case: dict) -> dict:
    expected = []
    for value in case.get('expected_files', []):
        path = Path(value)
        if not path.is_absolute():
            path = Path(case['cwd']) / path
        expected.append({'path': str(path), 'exists': path.is_file(), 'bytes': path.stat().st_size if path.is_file() else None})
    observed = None
    minimum = case.get('expected_min_edges')
    if minimum is not None and expected and expected[0]['exists']:
        with Path(expected[0]['path']).open('rb') as handle:
            observed = sum(1 for line in handle if line.strip() and not line.lstrip().startswith(b'#'))
    passed = all(x['exists'] for x in expected) and (minimum is None or observed is not None and observed >= minimum)
    return {'passed': passed, 'expected_files': expected, 'expected_min_edges': minimum, 'observed_nonempty_noncomment_lines': observed}


def measure(plan: dict, case: dict, directory: Path, psutil) -> tuple[dict, bool]:
    paths = {name: str(directory / filename) for name, filename in {
        'stdout': 'stdout.log', 'stderr': 'stderr.log', 'gnu_time': 'gnu_time.txt',
        'timeseries': 'timeseries.tsv', 'process_events': 'process_events.json'}.items()}
    result = {name: case[name] for name in ['id', 'dataset', 'version', 'kind', 'cwd']}
    if 'stage' in case:
        result['stage'] = case['stage']
    result.update(case_id=case['id'], status='failed', started_utc=utc(), argv=case['command'], paths=paths, errors=[], warnings=[])
    command = [GNU_TIME, '-v', '-o', paths['gnu_time'], '--'] + case['command']
    result['measurement_command'] = command
    result['environment_overrides'] = {**plan.get('env', {}), **case.get('env', {}), 'LC_ALL': 'C'}
    process = None
    events = {}
    counts = collections.Counter()
    union_seconds = collections.Counter()
    process_seconds = collections.Counter()
    peak_rss = None
    peak_pss = None
    samples = complete_pss_samples = 0
    interrupted = False
    started = previous = time.monotonic()
    probe_errors = collections.Counter()
    try:
        with Path(paths['stdout']).open('xb') as stdout, Path(paths['stderr']).open('xb') as stderr, Path(paths['timeseries']).open('x', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
            writer.writerow(['elapsed_seconds', 'process_count', 'total_rss_bytes', 'total_pss_bytes', 'pss_process_count', 'pss_complete', 'active_phases_json'])
            started = previous = time.monotonic()
            process = subprocess.Popen(command, cwd=case['cwd'], env=environment(plan, case), stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                root = psutil.Process(process.pid)
            except psutil.NoSuchProcess:
                root = None
            finished_clock = {}
            done = threading.Event()
            def wait_for_case():
                process.wait()
                finished_clock['at'] = time.monotonic()
                done.set()
            waiter = threading.Thread(target=wait_for_case, daemon=True)
            waiter.start()
            while True:
                sample_started = time.monotonic()
                elapsed = sample_started - started
                delta = sample_started - previous
                previous = sample_started
                try:
                    candidates = [root] + root.children(recursive=True) if root is not None else []
                except psutil.NoSuchProcess:
                    candidates = []
                rss = pss = pss_count = observed = 0
                active = set()
                phase_counts = collections.Counter()
                for item in candidates:
                    try:
                        created = item.create_time()
                        info = item.memory_info()
                        command_line = item.cmdline()
                        # exec() retains PID/create time; retain separate argv states.
                        command_id = hashlib.sha256(json.dumps(command_line).encode()).hexdigest()[:12]
                        identity = f'{item.pid}:{created:.6f}:{command_id}'
                        phase = classify(command_line)
                        proportional = None
                        try:
                            proportional = getattr(item.memory_full_info(), 'pss', None)
                        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as error:
                            probe_errors[type(error).__name__ + '_pss'] += 1
                        rss += info.rss
                        observed += 1
                        if proportional is not None:
                            pss += proportional
                            pss_count += 1
                        active.add(phase)
                        phase_counts[phase] += 1
                        event = events.get(identity)
                        if event is None:
                            event = {'pid': item.pid, 'create_time_epoch_seconds': created, 'argv': command_line,
                                     'phase': phase, 'first_observed_seconds': elapsed, 'last_observed_seconds': elapsed,
                                     'samples': 0, 'peak_sampled_rss_bytes': 0, 'peak_sampled_pss_bytes': None}
                            events[identity] = event
                            counts[phase] += 1
                        event['last_observed_seconds'] = elapsed
                        event['samples'] += 1
                        event['peak_sampled_rss_bytes'] = max(event['peak_sampled_rss_bytes'], info.rss)
                        if proportional is not None:
                            event['peak_sampled_pss_bytes'] = max(event['peak_sampled_pss_bytes'] or 0, proportional)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as error:
                        probe_errors[type(error).__name__] += 1
                complete = observed > 0 and pss_count == observed
                samples += 1
                complete_pss_samples += int(complete)
                if observed:
                    peak_rss = max(peak_rss or 0, rss)
                if complete:
                    peak_pss = max(peak_pss or 0, pss)
                for phase in active:
                    union_seconds[phase] += delta
                    process_seconds[phase] += delta * phase_counts[phase]
                writer.writerow([f'{elapsed:.6f}', observed, rss, pss if complete else '', pss_count, int(complete), json.dumps(sorted(active), separators=(',', ':'))])
                stream.flush()
                if done.wait(timeout=max(0.0, INTERVAL - (time.monotonic() - sample_started))):
                    break
            result['exit_code'] = process.wait()
            result['wall_seconds'] = finished_clock['at'] - started
    except KeyboardInterrupt:
        interrupted = True
        result['errors'].append('Runner interrupted; only this case session was stopped')
        if process is not None:
            stop_owned_session(process)
        result['status'] = 'interrupted'
    except Exception as error:
        result['errors'].append(f'{type(error).__name__}: {error}')
        result['exception_traceback'] = traceback.format_exc()
        if process is not None:
            stop_owned_session(process)
    finally:
        result.setdefault('wall_seconds', time.monotonic() - started)
        result.setdefault('exit_code', process.returncode if process is not None else None)
        result['finished_utc'] = utc()
        result['gnu_time'] = parse_time(Path(paths['gnu_time']))
        result['memory'] = {'sample_interval_seconds': INTERVAL, 'samples': samples,
                            'peak_descendant_rss_bytes': peak_rss, 'peak_descendant_pss_bytes': peak_pss,
                            'pss_complete_samples': complete_pss_samples, 'probe_errors': dict(probe_errors)}
        summary = []
        for phase in sorted(counts):
            group = [x for x in events.values() if x['phase'] == phase]
            summary.append({'phase': phase, 'process_count': counts[phase],
                            'peak_single_process_rss_bytes': max(x['peak_sampled_rss_bytes'] for x in group),
                            'peak_single_process_pss_bytes': max((x['peak_sampled_pss_bytes'] for x in group if x['peak_sampled_pss_bytes'] is not None), default=None),
                            'union_sampled_active_seconds': union_seconds[phase],
                            'sum_sampled_process_seconds': process_seconds[phase]})
        result['process_class_summary'] = summary
        atomic_json(Path(paths['process_events']), {'schema': 'sjaracne-observed-processes-v1', 'events': list(events.values()), 'sample_interval_seconds': INTERVAL})
    try:
        result['validation'] = output_validation(case)
    except Exception as error:
        result['validation'] = {'passed': False, 'error': str(error)}
    if not result['validation']['passed']:
        result['errors'].append('Expected output validation failed')
    if result['gnu_time']['max_single_process_rss_kib'] is None:
        result['errors'].append('GNU time maximum RSS was not recorded')
    if result['exit_code'] not in (None, 0):
        result['errors'].append(f'Command exited {result["exit_code"]}')
    if not interrupted and not result['errors'] and result['exit_code'] == 0:
        result['status'] = 'complete'
    if complete_pss_samples < samples:
        result['warnings'].append('Some polling samples lacked complete process PSS; inspect timeseries and probe counters')
    atomic_json(directory / 'result.json', result)
    return result, interrupted



def not_run_result(case: dict, state: str, error: str) -> dict:
    """Retain skipped/preflight-failed cases with null performance metrics."""
    result = {name: case[name] for name in ['id', 'dataset', 'version', 'kind', 'cwd']}
    if 'stage' in case:
        result['stage'] = case['stage']
    result.update(case_id=case['id'], status=state, started_utc=utc(), finished_utc=utc(),
                  argv=case['command'], wall_seconds=None, exit_code=None,
                  gnu_time={'elapsed_seconds': None, 'user_cpu_seconds': None,
                            'system_cpu_seconds': None, 'max_single_process_rss_kib': None},
                  memory={'sample_interval_seconds': INTERVAL, 'samples': 0,
                          'peak_descendant_rss_bytes': None, 'peak_descendant_pss_bytes': None,
                          'pss_complete_samples': 0}, process_class_summary=[], paths={},
                  validation={'passed': False, 'not_run': True}, errors=[error], warnings=[])
    return result


def check_disk_space(plan: dict, case: dict, output: Path) -> list[dict]:
    """Require ten GiB available on explicit run/scratch paths before a case."""
    env = environment(plan, case)
    candidates = [str(output), case['cwd']]
    for value in [plan.get('disk_guard_path'), case.get('disk_guard_path'), env.get('TMPDIR')]:
        if value:
            candidates.append(value)
    checks = []
    for value in dict.fromkeys(candidates):
        path = Path(value)
        if not path.exists():
            raise FileNotFoundError(f'Disk guard path does not exist: {path}')
        usage = shutil.disk_usage(path)
        checks.append({'path': str(path), 'free_bytes': usage.free, 'minimum_free_bytes': 10 * 1024**3})
        if usage.free < 10 * 1024**3:
            raise RuntimeError(f'Less than 10 GiB free at {path}; no command started')
    return checks


def run_report(plan: dict, output: Path, errors: list[dict]) -> None:
    command = plan.get('report_command')
    if not command:
        return
    try:
        with (output / 'report.log').open('ab') as log:
            log.write(('\nREPORT ' + utc() + '\n').encode())
            completed = subprocess.run(command, cwd=plan.get('report_cwd', '.'), env=environment(plan, {}), stdout=log, stderr=subprocess.STDOUT, timeout=180, check=False)
        if completed.returncode:
            errors.append({'at_utc': utc(), 'error': 'report_command exit ' + str(completed.returncode)})
    except Exception as error:
        errors.append({'at_utc': utc(), 'error': f'{type(error).__name__}: {error}'})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    import psutil
    raw = args.plan.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    plan = json.loads(raw)
    validate_plan(plan)
    if args.check_only:
        print(json.dumps({'state': 'validated', 'cases': len(plan['cases']), 'psutil_version': psutil.__version__, 'plan_sha256': digest, 'jobs_started': 0}))
        return 0
    output = args.output_dir.resolve()
    if output.exists() and not args.resume:
        raise FileExistsError('Output directory exists; use a new directory or --resume with unchanged plan')
    output.mkdir(parents=True, exist_ok=True)
    results = []
    if args.resume and (output / 'measurements.json').exists():
        previous = json.loads((output / 'measurements.json').read_text())
        if previous['plan_sha256'] != digest:
            raise ValueError('Resume requires identical plan bytes')
        results = previous['results']
    elif args.resume and any(output.iterdir()):
        raise ValueError('Nonempty output has no resumable measurements.json')
    atomic_json(output / 'plan_snapshot.json', plan)
    report_errors = []
    def publish(state: str, active: str | None = None, active_directory: str | None = None) -> None:
        atomic_json(output / 'measurements.json', {'schema': SCHEMA, 'plan_sha256': digest,
                    'updated_utc': utc(), 'metric_definitions': METRIC_DEFINITIONS, 'results': results})
        atomic_json(output / 'status.json', {'schema': 'sjaracne-performance-status-v1', 'state': state,
                    'updated_utc': utc(), 'active_case_id': active, 'active_attempt_directory': active_directory,
                    'completed_cases': sum(x['status'] == 'complete' for x in results),
                    'failed_cases': sum(x['status'] != 'complete' for x in results),
                    'finished_cases': len(results), 'total_cases': len(plan['cases']), 'report_errors': report_errors})
    publish('running')
    recorded = {x['id'] for x in results}
    signal.signal(signal.SIGTERM, lambda signum, frame: (_ for _ in ()).throw(KeyboardInterrupt()))
    interrupted = False
    for case in plan['cases']:
        if case['id'] in recorded:
            continue
        directory = new_attempt(output / 'cases' / case['id'])
        publish('running', case['id'], str(directory))
        by_id = {x['id']: x for x in results}
        failed_dependencies = [x for x in case.get('depends_on', []) if by_id.get(x, {}).get('status') != 'complete']
        if failed_dependencies:
            result = not_run_result(case, 'dependency_failed', 'Prerequisite cases not complete: ' + ', '.join(failed_dependencies))
            atomic_json(directory / 'result.json', result)
        else:
            try:
                disk_checks = check_disk_space(plan, case, output)
            except Exception as error:
                result = not_run_result(case, 'preflight_failed', f'{type(error).__name__}: {error}')
                atomic_json(directory / 'result.json', result)
            else:
                result, interrupted = measure(plan, case, directory, psutil)
                result['disk_space_before'] = disk_checks
                atomic_json(directory / 'result.json', result)
        results.append(result)
        publish('interrupted' if interrupted else 'running')
        run_report(plan, output, report_errors)
        publish('interrupted' if interrupted else 'running')
        if interrupted:
            break
    final = 'interrupted' if interrupted else ('complete_with_errors' if any(x['status'] != 'complete' for x in results) else 'complete')
    publish(final)
    run_report(plan, output, report_errors)
    publish(final)
    print(json.dumps({'state': final, 'results': len(results), 'output_dir': str(output)}), flush=True)
    return 0 if final == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())