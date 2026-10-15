from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_pilot as pilot


class PlanningTests(unittest.TestCase):
    def test_prespecified_random_twenty(self):
        self.assertEqual(pilot.select_seeds(),
                         [2, 4, 6, 8, 25, 26, 28, 30, 51, 55, 57, 62, 64, 68, 74, 79, 81, 84, 88, 89])
        self.assertEqual(pilot.select_seeds(), pilot.select_seeds())
        self.assertEqual(pilot.select_seeds(100), list(range(1, 101)))
        for count in (0, 101):
            with self.assertRaises(ValueError):
                pilot.select_seeds(count)

    def test_raw_commands_change_only_sampling_and_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = {"seeds": [2], "execution": {"wsl_distro": "Ubuntu"},
                    "components": {arm: {"binary": {"path": str(root / arm)},
                                         "config_dir": str(root / "config")} for arm in pilot.ARMS},
                    "inputs": {"expression": {"path": str(root / "expression.exp")},
                               "full_sig_hubs": {"path": str(root / "all_hubs.txt")}},
                    "evaluated_sources": {"path": str(root / "eligible.txt")}}
            with patch.object(pilot, "wsl_path", side_effect=lambda p: str(p)):
                before = pilot.native_command(plan, "before", 2, root / "before_job")
                after = pilot.native_command(plan, "after", 2, root / "after_job")
            for command in (before, after):
                for flag, value in (("-p", "1"), ("-t", "0"), ("-e", "1"), ("-N", "40"), ("-n", "0")):
                    self.assertEqual(command[command.index(flag) + 1], value)
                self.assertEqual(command[command.index("-l") + 1], str(root / "all_hubs.txt"))
                self.assertEqual(command[command.index("-s") + 1], str(root / "eligible.txt"))
                self.assertNotIn("-c", command)
            self.assertEqual(before[before.index("-r") + 1], "1")
            self.assertNotIn("-u", before)
            self.assertEqual(after[after.index("-u") + 1], "80%")
            self.assertNotIn("-r", after)

    def test_log_requires_full_traversal_and_no_filters(self):
        good = "Marker No: 17971 (17971 active), Array No: 121\nGene: 272 Time: 10\nMaximum observed npar: 40\n"
        pilot.validate_log(good, sources=272, genes=17971, arm="before")
        for broken in (good.replace("17971 active", "17970 active"),
                       good.replace("Gene: 272", "Gene: 271"),
                       good.replace("Maximum observed npar:", "Incomplete:"),
                       good + "Applying DPI", good + "MI threshold determined",
                       good + "Cannot find probe: MISSING ... ignored."):
            with self.assertRaises(ValueError):
                pilot.validate_log(broken, sources=272, genes=17971, arm="before")
        with self.assertRaises(ValueError):
            pilot.validate_log(good, sources=272, genes=17971, arm="after")
        pilot.validate_log(good + "selected 97 of 121 eligible observations (request: 80%)",
                           sources=272, genes=17971, arm="after")

    def test_artifact_hash_rejects_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact"
            path.write_bytes(b"frozen")
            record = pilot.record(path)
            pilot.verify_record(record)
            path.write_bytes(b"altered")
            with self.assertRaises(ValueError):
                pilot.verify_record(record)


if __name__ == "__main__":
    unittest.main()
