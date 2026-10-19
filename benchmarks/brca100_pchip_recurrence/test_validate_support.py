#!/usr/bin/env python3
"""Small adversarial fixtures for the independent support auditor."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location('independent_support_audit',
                                             Path(__file__).with_name('validate_support.py'))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class ValidateSupportTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.adjacency = self.root / 'adj'
        self.adjacency.mkdir()
        self.drivers = self.root / 'drivers.txt'
        # Deliberately not lexical: the auditor must use the pinned list,
        # while consensus output remains lexically sorted.
        self.drivers.write_text('X\nA\nB\n', encoding='utf-8')
        for run in range(1, 11):
            rows = []
            if run <= 8:
                rows.append('X\tY\t0.5')
            if run <= 6:
                rows.append('A\tB\t%.6f' % (run * 0.100001))
            if run <= 5:
                rows.append('A\tC\t0.2')
            if run <= 7:
                rows.append('B\tA\t0.123456')
            if run == 9:
                rows.append('A')  # Valid explicit zero-degree source row.
            (self.adjacency / ('TF_run_%03d.adj' % run)).write_text(
                '>  Input file fixture.exp\n' + '\n'.join(rows) + ('\n' if rows else ''),
                encoding='utf-8')
        self.k6 = self.root / 'k6' / 'consensus_network_3col_.txt'
        self.legacy = self.root / 'legacy_pc' / 'consensus_network_3col_.txt'
        self.k6_rows = {('A', 'B'): '0.3500', ('B', 'A'): '0.1235', ('X', 'Y'): '0.5000'}
        self.legacy_rows = {('B', 'A'): '0.1235', ('X', 'Y'): '0.5000'}
        self.write_network(self.k6, self.k6_rows)
        self.write_network(self.legacy, self.legacy_rows)
        self.write_metadata()

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def write_network(path, rows, *, enhanced=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('source\ttarget\tMI\n' + ''.join(
            '%s\t%s\t%s\n' % (source, target, rows[(source, target)])
            for source, target in sorted(rows)), encoding='utf-8')
        if enhanced:
            path.with_name('consensus_network_ncol_.txt').write_text(
                'source\ttarget\tsource.symbol\ttarget.symbol\tMI\n' + ''.join(
                    '%s\t%s\t%s\t%s\t%s\n' % (source, target, source, target, rows[(source, target)])
                    for source, target in sorted(rows)), encoding='utf-8')

    def write_metadata(self):
        (self.k6.parent / 'bootstrap_info_.txt').write_text(
            'Total edge tested: 4\nConsensus selection: minimum recurrence\n'
            'Bootstrap networks: 10\nMinimum recurrence: 6\nMinimum recurrence fraction: 0.6\n')
        (self.k6.parent / 'parameter_info_.txt').write_text(
            '>  Bootstrap No: 10\n>  Consensus selection minimum recurrence\n'
            '>  Minimum recurrence 6 of 10\n>  Minimum recurrence fraction 0.6\n')
        (self.legacy.parent / 'bootstrap_info_.txt').write_text(
            'Total edge tested: 4\nBonferroni corrected (0.05) alpha: 0.0125\n'
            'mu: 6.5\nsigma: %s\n' % math.sqrt(0.625))
        (self.legacy.parent / 'parameter_info_.txt').write_text('>  Bootstrap No: 10\n')

    def invoke(self, **overrides):
        arguments = dict(expected_runs=10, minimum_recurrence=6, legacy_p=0.5)
        arguments.update(overrides)
        return AUDIT.validate_support(self.adjacency, self.drivers, self.k6, self.legacy, **arguments)

    def test_exact_directed_membership_rounding_histogram_empty_runs_and_nesting(self):
        result = self.invoke()
        self.assertTrue(result['passed'], result['issues'])
        self.assertEqual(result['B'], 10)
        self.assertEqual(result['K'], 6)
        self.assertEqual(result['K_over_B'], 0.6)
        self.assertEqual(result['union_edges'], 4)
        self.assertEqual(result['pair_incidence'], 26)
        self.assertEqual(result['empty_adjacency_files'], 2)
        self.assertEqual(result['histogram'], {str(k): int(k in (5, 6, 7, 8)) for k in range(1, 11)})
        self.assertEqual(result['overlap'], {'shared': 2, 'k6_only': 1, 'legacy_pc_only': 0})
        self.assertTrue(result['legacy_is_subset_of_k6'])
        self.assertFalse(result['k6_is_subset_of_legacy'])
        self.assertEqual(result['legacy_minimum_eligible_support'], 7)
        self.assertEqual(result['legacy_observed_minimum_support'], 7)
        self.assertTrue(result['source_order_verified_for_all_files'])
        self.assertEqual(len(result['runs']), 10)
        self.assertTrue(all(len(run['sha256']) == 64 for run in result['runs']))

    def test_consistent_duplicates_across_rows_count_once_per_file(self):
        path = self.adjacency / 'TF_run_001.adj'
        text = path.read_text().replace('A\tB\t0.100001\n',
                                        'A\tB\t0.100001\tB\t0.100001\nA\tB\t0.100001\n')
        path.write_text(text)
        result = self.invoke()
        self.assertTrue(result['passed'], result['issues'])
        self.assertEqual(result['runs'][0]['duplicate_occurrences_ignored'], 2)
        self.assertEqual(result['runs'][0]['edge_count'], 4)
        self.assertEqual(result['pair_incidence'], 26)

    def test_conflicting_duplicate_fails_closed(self):
        path = self.adjacency / 'TF_run_001.adj'
        path.write_text(path.read_text().replace('A\tB\t0.100001', 'A\tB\t0.100001\tB\t0.3'))
        with self.assertRaisesRegex(AUDIT.AuditError, 'Conflicting duplicate'):
            self.invoke()

    def test_unknown_source_fails_closed(self):
        (self.adjacency / 'TF_run_010.adj').write_text('UNKNOWN\tY\t0.1\n')
        with self.assertRaisesRegex(AUDIT.AuditError, 'Unknown source'):
            self.invoke()

    def test_out_of_driver_order_fails_closed(self):
        (self.adjacency / 'TF_run_010.adj').write_text('B\tA\t0.1\nA\tB\t0.2\n')
        with self.assertRaisesRegex(AUDIT.AuditError, 'Out-of-order'):
            self.invoke()

    def test_nonadjacent_repeated_source_fails_closed(self):
        (self.adjacency / 'TF_run_010.adj').write_text('A\tB\t0.1\nB\tA\t0.2\nA\tC\t0.3\n')
        with self.assertRaisesRegex(AUDIT.AuditError, 'Out-of-order'):
            self.invoke()

    def test_malformed_rows_and_nonfinite_mi_fail_closed(self):
        path = self.adjacency / 'TF_run_010.adj'
        for body in ('A\tB\n', 'A\tB\tnan\n', 'A\tB\tinf\n', 'A\t\t0.1\n', 'A\tB\tnot-a-number\n'):
            with self.subTest(body=body):
                path.write_text(body)
                with self.assertRaises(AUDIT.AuditError):
                    self.invoke()

    def test_wrong_bootstrap_count_fails_closed(self):
        with self.assertRaisesRegex(AUDIT.AuditError, 'exactly 11'):
            self.invoke(expected_runs=11)

    def test_k6_off_by_one_is_detected(self):
        rows = dict(self.k6_rows)
        rows[('A', 'C')] = '0.2000'  # Actual support is five, not six.
        self.write_network(self.k6, rows)
        result = self.invoke()
        self.assertFalse(result['passed'])
        self.assertEqual(result['issues']['k6_membership_mismatch'], 1)

    def test_missing_k6_edge_is_detected(self):
        rows = dict(self.k6_rows)
        del rows[('A', 'B')]
        self.write_network(self.k6, rows)
        result = self.invoke()
        self.assertEqual(result['issues']['k6_membership_mismatch'], 1)

    def test_legacy_membership_uses_actual_normal_boundary_not_assumed_k9(self):
        rows = dict(self.legacy_rows)
        rows[('A', 'B')] = '0.3500'
        self.write_network(self.legacy, rows)
        result = self.invoke()
        self.assertFalse(result['passed'])
        self.assertEqual(result['legacy_minimum_eligible_support'], 7)
        self.assertEqual(result['issues']['legacy_pc_membership_mismatch'], 1)

    def test_network_edge_absent_from_union_is_detected(self):
        rows = dict(self.legacy_rows)
        rows[('Y', 'X')] = '0.5000'
        self.write_network(self.legacy, rows)
        result = self.invoke()
        self.assertEqual(result['issues']['legacy_pc_edges_absent_from_union'], 1)

    def test_mi_mean_or_rounding_change_is_detected_in_both_modes(self):
        for mode, path, original in (('k6', self.k6, self.k6_rows),
                                      ('legacy_pc', self.legacy, self.legacy_rows)):
            with self.subTest(mode=mode):
                rows = dict(original)
                rows[('B', 'A')] = '0.1234'
                self.write_network(path, rows)
                result = self.invoke()
                self.assertEqual(result['issues'][mode + '_mi_mismatch'], 1)
                self.write_network(path, original)

    def test_duplicate_unsorted_and_non_four_decimal_output_fail_closed(self):
        original = self.k6.read_text()
        for body in ('source\ttarget\tMI\nB\tA\t0.1235\nA\tB\t0.3500\n',
                     'source\ttarget\tMI\nA\tB\t0.3500\nA\tB\t0.3500\n',
                     'source\ttarget\tMI\nA\tB\t0.35\n'):
            with self.subTest(body=body):
                self.k6.write_text(body)
                with self.assertRaises(AUDIT.AuditError):
                    self.invoke()
        self.k6.write_text(original)

    def test_enhanced_projection_change_is_detected(self):
        path = self.k6.with_name('consensus_network_ncol_.txt')
        path.write_text(path.read_text().replace('0.3500', '0.3501'))
        result = self.invoke()
        self.assertEqual(result['issues']['enhanced_projection_mismatch'], 1)

    def test_wrong_k6_B_K_fraction_metadata_is_detected(self):
        path = self.k6.parent / 'bootstrap_info_.txt'
        path.write_text(path.read_text().replace('Bootstrap networks: 10', 'Bootstrap networks: 9')
                        .replace('Minimum recurrence: 6', 'Minimum recurrence: 5')
                        .replace('fraction: 0.6', 'fraction: 0.5'))
        result = self.invoke()
        self.assertEqual(result['issues']['k6_metadata_selection_mismatch'], 1)

    def test_wrong_legacy_moments_are_detected(self):
        path = self.legacy.parent / 'bootstrap_info_.txt'
        path.write_text(path.read_text().replace('mu: 6.5', 'mu: 6.4'))
        result = self.invoke()
        self.assertEqual(result['issues']['legacy_pc_metadata_mu_mismatch'], 1)

    def test_historical_sha_is_verified_without_retuning(self):
        historical = self.root / 'historical.txt'
        historical.write_bytes(self.legacy.read_bytes())
        result = self.invoke(historical_legacy_network=historical,
                             historical_legacy_sha256=AUDIT.sha256(historical))
        self.assertTrue(result['passed'])
        historical.write_text(historical.read_text().replace('0.5000', '0.5001'))
        result = self.invoke(historical_legacy_network=historical)
        self.assertEqual(result['issues']['historical_legacy_sha256_mismatch'], 1)

    def test_canonical_normal_tail_uses_strict_comparison(self):
        self.assertEqual(AUDIT.normal_tail(7, 7, 1), 0.5)
        self.assertEqual(AUDIT.normal_tail(1, 0, 0), 0.0)
        result = self.invoke(legacy_p=AUDIT.normal_tail(7, 6.5, math.sqrt(0.625)))
        self.assertFalse(result['passed'])  # Existing support-seven edge is exactly on the strict boundary.
        self.assertEqual(result['issues']['legacy_pc_membership_mismatch'], 1)

    def test_all_header_only_files_still_count_toward_B(self):
        for path in self.adjacency.glob('*.adj'):
            path.write_text('>  Empty but valid run\n')
        self.write_network(self.k6, {})
        self.write_network(self.legacy, {})
        result = self.invoke(check_metadata=False)
        self.assertTrue(result['passed'])
        self.assertEqual(result['B'], 10)
        self.assertEqual(result['empty_adjacency_files'], 10)
        self.assertEqual(result['union_edges'], 0)
        self.assertEqual(result['pair_incidence'], 0)

    def test_cli_writes_fresh_report_and_refuses_overwrite(self):
        output = self.root / 'audit.json'
        command = [sys.executable, str(Path(__file__).with_name('validate_support.py')),
                   '--adjacency-dir', str(self.adjacency), '--drivers', str(self.drivers),
                   '--k6-network', str(self.k6), '--legacy-network', str(self.legacy),
                   '--expected-runs', '10', '--legacy-p', '0.5', '--output', str(output)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn('SUPPORT_AUDIT_RESULT=', first.stdout)
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn('Refusing to overwrite', second.stderr)


if __name__ == '__main__':
    unittest.main()
