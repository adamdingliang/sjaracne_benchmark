"""Verify external DREAM5 Systems Genetics A gold files.

This verifier checks only reference graphs. It never checks expression/genotype
inputs, downloads data, derives regulators, or runs inference. Use prepare.py to
verify the complete source bundle and prepare expression inputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


HERE = Path(__file__).resolve().parent
ARCHIVE_SHA256 = '7ea861c57a05d5dd7e504d67506076f2ed97fa0c348e3fb01efc604572c2c68f'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def parse_gold(text, gene_count=1000):
    """Validate positive-only directed edges against a fixed gene universe.

    Missing pairs are negative because these files give a complete generating
    model, not an incomplete experimental interaction reference. The universe
    is fixed independently of which nodes have edges.
    """
    if isinstance(gene_count, bool) or not isinstance(gene_count, int) or gene_count < 2:
        raise ValueError('gene_count must be an integer of at least two')
    pairs = set()
    for number, row in enumerate(csv.reader(io.StringIO(text), delimiter='\t'), 1):
        if not row:
            continue
        if len(row) != 3 or row[2] != '1':
            raise ValueError('Gold row %d must have source, target and literal positive label 1' % number)
        for gene in row[:2]:
            match = re.fullmatch(r'G([1-9]\d*)', gene)
            if match is None or int(match.group(1)) > gene_count:
                raise ValueError('Gold contains an unknown or malformed gene ID')
        pair = tuple(row[:2])
        if pair[0] == pair[1]:
            raise ValueError('Gold self-edges are excluded')
        if pair in pairs:
            raise ValueError('Duplicate directed gold edge')
        pairs.add(pair)
    if not pairs:
        raise ValueError('Gold file contains no positive edges')
    sources = {source for source, _ in pairs}
    targets = {target for _, target in pairs}
    total = gene_count * (gene_count - 1)
    return {'positive_edges': len(pairs), 'negative_edges': total - len(pairs),
            'full_directed_nonself_pairs': total, 'reference_source_genes': len(sources),
            'reference_target_genes': len(targets), 'unique_nodes_in_gold': len(sources | targets)}


def _checked_bytes(data, record):
    if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError('Source size/SHA256 mismatch: ' + record['path'])


def _read_external(root, record):
    relative = Path(record['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Unsafe external source path')
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError('Source resolves outside the selected data root')
    data = path.read_bytes()
    _checked_bytes(data, record)
    return data


def verify(*, data_root=None, archive=None, manifest=None):
    """Verify source hashes, positive-only graphs and complete model universes.

    Args:
        data_root: External data directory containing A100/, A300/, A999/.
        archive: Original gold ZIP; choose this or data_root, not both.
        manifest: Optional in-memory metadata for offline synthetic tests.

    Returns:
        A gold-only verification record; expression and genotype remain unchecked.

    Raises:
        ValueError: Source choice, hashes, identifiers or graph counts differ.
    """
    if (data_root is None) == (archive is None):
        raise ValueError('Choose exactly one of data_root or archive')
    metadata = json.loads((HERE / 'data/provenance.json').read_text(encoding='utf-8')) if manifest is None else manifest
    records = metadata['files']
    source_notice = metadata['source_notice']
    contents = {}
    if archive is not None:
        archive = Path(archive).resolve(strict=True)
        expected = metadata['source']['gold_archive']
        if archive.stat().st_size != expected['bytes'] or digest(archive) != expected['sha256']:
            raise ValueError('Gold archive size/SHA256 differs from the pinned source')
        with zipfile.ZipFile(archive) as source:
            names = source.namelist()
            for record in records + [source_notice]:
                if names.count(record['archive_member']) != 1:
                    raise ValueError('Missing or duplicate exact gold ZIP member')
                data = source.read(record['archive_member'])
                _checked_bytes(data, record)
                contents[record['path']] = data
        origin = {'kind': 'verified_archived_source', 'path': str(archive), 'sha256': expected['sha256']}
    else:
        root = Path(data_root).resolve(strict=True)
        for record in records + [source_notice]:
            contents[record['path']] = _read_external(root, record)
        origin = {'kind': 'external_original_files', 'path': str(root)}
    results = []
    for record in records:
        stats = parse_gold(contents[record['path']].decode('utf-8'), record['expected_genes'])
        if any(stats[key] != record[key] for key in stats):
            raise ValueError('Gold topology counts differ from pinned source: ' + record['id'])
        results.append({'id': record['id'], 'sha256': record['sha256'], **stats})
    return {'dataset': metadata['dataset'], 'status': 'GOLD_VERIFIED',
            'gold_status': 'verified', 'expression_status': 'not_checked',
            'genotype_status': 'not_checked', 'origin': origin,
            'networks': results, 'inference_performed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--data-root', type=Path, help='External data root containing A100/, A300/, A999/ and the original gold README')
    source.add_argument('--archive', type=Path, help='Pinned original DREAM5_SysGenA_GoldStandard.zip')
    args = parser.parse_args()
    print(json.dumps(verify(data_root=args.data_root, archive=args.archive), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
