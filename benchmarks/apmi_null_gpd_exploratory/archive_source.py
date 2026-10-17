"""Copy tracked historical PR1 evidence without modifying its contents."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-root', required=True, type=Path)
    args = parser.parse_args()
    source = args.engine_root.resolve(strict=True)
    here = Path(__file__).resolve().parent
    destination = here / 'legacy_pr1'
    manifest_path = here / 'legacy_pr1_manifest.json'
    if destination.exists() or manifest_path.exists():
        raise ValueError('archive output must be fresh')
    commit = '0d155367982e96744cf8c98c7752311871a06488'

    def git(*arguments):
        return subprocess.check_output(['git', '-c', 'safe.directory=' + source.as_posix(),
                                        '-C', str(source), *arguments])

    targets = ('benchmarks/apmi_null_calibration', 'SJARACNe/calibrate_apmi_null.py',
               'SJARACNe/config/apmi_null', 'tests/test_apmi_null_calibration.py')
    files = git('ls-tree', '-r', '--name-only', commit, '--', *targets).decode('utf-8').splitlines()
    if not files or git('diff', '--name-only', commit, '--', *targets).strip():
        raise ValueError('historical source paths differ from the pinned PR1 commit')
    records = []
    for relative in files:
        original = source / relative
        copied = destination / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, copied)
        raw = original.read_bytes()
        if copied.read_bytes() != raw:
            raise ValueError('copy mismatch: ' + relative)
        records.append({'path': relative, 'bytes': len(raw),
                        'sha256': hashlib.sha256(raw).hexdigest(),
                        'git_blob': git('rev-parse', commit + ':' + relative).decode('ascii').strip()})
    manifest = {'source_repository': 'https://github.com/adamdingliang/SJARACNe',
                'source_commit': commit, 'copy_policy': 'preserve working-copy bytes; Git blob identities also retained',
                'raw_draws_copied': False, 'files': records}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'files': len(records), 'bytes': sum(row['bytes'] for row in records)}))


if __name__ == '__main__':
    main()
