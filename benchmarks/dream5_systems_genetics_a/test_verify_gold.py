"""Offline synthetic checks of gold-only integrity and scoring-universe rules."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import verify_gold as module


class GoldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.gold = b'G1\tG2\t1\nG2\tG3\t1\n'
        self.notice = b'Original source says missing non-self edges are negatives.\n'
        def record(name, data):
            return {'path': name, 'archive_member': 'source/' + name,
                    'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        row = record('A100/Network1/gold standard/edges.tsv', self.gold)
        row.update(id='synthetic', expected_genes=4, **module.parse_gold(self.gold.decode(), 4))
        self.metadata = {'dataset': 'synthetic', 'files': [row],
                         'source_notice': record('README.txt', self.notice), 'source': {}}
        for r, data in ((row, self.gold), (self.metadata['source_notice'], self.notice)):
            p = self.root / r['path']
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def tearDown(self):
        self.temp.cleanup()

    def test_portable_manifest_fixes_fifteen_graphs_and_pending_inputs(self):
        metadata = json.loads((module.HERE / 'data/provenance.json').read_text())
        self.assertEqual(metadata['status'], 'GOLD_AVAILABLE_INPUTS_PENDING')
        self.assertFalse(metadata['expression_audited'])
        self.assertEqual(metadata['source']['gold_archive']['sha256'], module.ARCHIVE_SHA256)
        rows = metadata['files']
        self.assertEqual({(r['group'], r['network']) for r in rows},
                         {(group, i) for group in ('A100', 'A300', 'A999') for i in range(1, 6)})
        self.assertEqual(len(rows), 15)
        for r in rows:
            self.assertFalse(Path(r['path']).is_absolute())
            self.assertEqual(r['full_directed_nonself_pairs'], 999000)
            self.assertEqual(r['positive_edges'] + r['negative_edges'], 999000)

    def test_complete_universe_includes_isolated_genes_and_absent_pairs(self):
        stats = module.parse_gold('G1\tG2\t1\n', 4)
        self.assertEqual(stats['unique_nodes_in_gold'], 2)
        self.assertEqual(stats['full_directed_nonself_pairs'], 12)
        self.assertEqual(stats['negative_edges'], 11)

    def test_invalid_gold_never_silently_changes_reference(self):
        for text in ('', 'G1\tG1\t1\n', 'G1\tG2\t0\n', 'G1\tG2\t-1\n',
                     'G0\tG2\t1\n', 'G01\tG2\t1\n', 'G1\tG5\t1\n',
                     'G1\tG2\n', 'G1\tG2\t1\nG1\tG2\t1\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                module.parse_gold(text, 4)

    def test_external_hash_and_topology_tampering_fail_closed(self):
        result = module.verify(data_root=self.root, manifest=self.metadata)
        self.assertEqual(result['gold_status'], 'verified')
        self.assertEqual(result['status'], 'GOLD_AVAILABLE_INPUTS_PENDING')
        self.assertFalse(result['inference_performed'])
        changed = copy.deepcopy(self.metadata)
        changed['files'][0]['positive_edges'] += 1
        with self.assertRaisesRegex(ValueError, 'topology counts'):
            module.verify(data_root=self.root, manifest=changed)
        (self.root / self.metadata['files'][0]['path']).write_bytes(b'changed\n')
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            module.verify(data_root=self.root, manifest=self.metadata)

    def test_exact_archive_members_verified_without_extraction(self):
        archive = self.root / 'source.zip'
        with zipfile.ZipFile(archive, 'w') as source:
            source.writestr(self.metadata['files'][0]['archive_member'], self.gold)
            source.writestr(self.metadata['source_notice']['archive_member'], self.notice)
            source.writestr('../not-extracted', 'unrelated data')
        self.metadata['source']['gold_archive'] = {'bytes': archive.stat().st_size, 'sha256': module.digest(archive)}
        result = module.verify(archive=archive, manifest=self.metadata)
        self.assertEqual(result['gold_status'], 'verified')
        self.assertFalse((self.root.parent / 'not-extracted').exists())
        self.metadata['source']['gold_archive']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'archive size/SHA256'):
            module.verify(archive=archive, manifest=self.metadata)

    def test_source_choice_and_path_traversal_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            module.verify(manifest=self.metadata)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            module.verify(data_root=self.root, archive=self.root / 'source.zip', manifest=self.metadata)
        self.metadata['files'][0]['path'] = '../outside.tsv'
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            module.verify(data_root=self.root, manifest=self.metadata)


if __name__ == '__main__':
    unittest.main()
