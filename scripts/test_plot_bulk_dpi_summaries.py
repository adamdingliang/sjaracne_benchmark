import unittest
from plot_bulk_dpi_summaries import one, paired_increase


class PlotInputTests(unittest.TestCase):
    def test_one_unique_complete_summary(self):
        row = {'strategy': 'strict', 'comparisons': '3', 'available_comparisons': '3'}
        self.assertEqual(row, one([row], strategy='strict'))
        for rows in ([], [row, row], [{**row, 'available_comparisons': '2'}]):
            with self.assertRaises(ValueError):
                one(rows, strategy='strict')

    def rows(self):
        return [{'network': 'tf', 'seed': str(seed), 'H': str(h), 'strategy_label': 'strict',
                 'job_id': f'{seed}-{h}', 'pooled_pruning_fraction': str(value)}
                for seed in (1, 2, 3) for h, value in ((10, .1 * seed), (30, .2 * seed))
                for panel in (1, 2, 3)]

    def test_aliases_count_once_and_subtract_within_seed(self):
        result = paired_increase(self.rows(), 'tf', 10, 30, 'strict')
        self.assertEqual(3, len(result))
        for expected, actual in zip((10, 20, 30), result):
            self.assertAlmostEqual(expected, actual['increase_pp'])

    def test_inconsistent_alias_rejected(self):
        rows = self.rows()
        rows[0]['pooled_pruning_fraction'] = '.7'
        with self.assertRaises(ValueError):
            paired_increase(rows, 'tf', 10, 30, 'strict')

    def test_different_jobs_not_silently_deduplicated(self):
        rows = self.rows()
        rows[0]['job_id'] = 'different-job'
        with self.assertRaises(ValueError):
            paired_increase(rows, 'tf', 10, 30, 'strict')

    def test_missing_seed_rejected(self):
        with self.assertRaises(ValueError):
            paired_increase(self.rows()[:-3], 'tf', 10, 30, 'strict')

    def test_invalid_fraction_rejected(self):
        rows = self.rows()
        for row in rows[:3]:
            row['pooled_pruning_fraction'] = 'nan'
        with self.assertRaises(ValueError):
            paired_increase(rows, 'tf', 10, 30, 'strict')


if __name__ == '__main__':
    unittest.main()
