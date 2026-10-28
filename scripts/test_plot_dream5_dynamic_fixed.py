"""Selection checks for the report-only figure. No inference or raw inputs."""
import csv
import math
from pathlib import Path
import tempfile
import unittest

from plot_dream5_dynamic_fixed import HUBS, select_cases


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'cases.tsv'
        self.rows = [dict(scope='trajectory', dataset=dataset, H=h,
                          panel=panel, seed=seed, annotation_mode='panel',
                          comparison='dynamic_vs_fixed', slope=0.05,
                          target_label='strict_count', available='True',
                          budget=100, TP_delta=0.0 if h == hubs[-1] else -2.0,
                          FP_delta=0.0 if h == hubs[-1] else 2.0)
                     for dataset, hubs in HUBS.items() for h in hubs
                     for panel in (1, 2, 3) for seed in (1, 2, 3)]

    def write(self):
        with self.path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]), delimiter='\t')
            writer.writeheader()
            writer.writerows(self.rows)

    def test_complete_cases_and_unrelated_rows(self):
        self.rows.append({**self.rows[0], 'scope': 'full'})
        self.write()
        groups = select_cases(self.path)
        self.assertEqual(6, len(groups))
        self.assertTrue(all(len(cases) == 9 for cases in groups.values()))

    def test_missing_case_rejected(self):
        self.rows.pop()
        self.write()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            select_cases(self.path)

    def test_duplicate_case_rejected(self):
        self.rows.append(self.rows[0].copy())
        self.write()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            select_cases(self.path)

    def test_unavailable_case_rejected(self):
        self.rows[0]['available'] = 'False'
        self.write()
        with self.assertRaisesRegex(ValueError, 'Unavailable'):
            select_cases(self.path)

    def test_invalid_numeric_values_rejected(self):
        self.rows[0]['TP_delta'] = math.nan
        self.write()
        with self.assertRaisesRegex(ValueError, 'Invalid numeric'):
            select_cases(self.path)

    def test_budget_conservation_and_full_endpoint(self):
        self.rows[0]['FP_delta'] = 3.0
        self.write()
        with self.assertRaisesRegex(ValueError, 'conserve'):
            select_cases(self.path)
        self.rows[0]['FP_delta'] = 2.0
        endpoint = next(r for r in self.rows if r['H'] == HUBS[r['dataset']][-1])
        endpoint['TP_delta'], endpoint['FP_delta'] = 1.0, -1.0
        self.write()
        with self.assertRaisesRegex(ValueError, 'Full-H'):
            select_cases(self.path)


if __name__ == '__main__':
    unittest.main()
