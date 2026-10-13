#!/usr/bin/env python3
"""Isolate imported tests and bind optional external fixtures without editing them."""
from __future__ import annotations

import argparse
import importlib
from pathlib import Path
import sys
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", nargs="+")
    parser.add_argument("--engine-repo", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    suite = unittest.TestSuite()
    for name in args.modules:
        module = importlib.import_module(name)
        if name == "test_pilot":
            if args.engine_repo:
                module.REPO_ROOT = args.engine_repo.resolve()
            else:
                method = module.PanelTests.test_real_brca100_panels_are_nested_balanced_and_full_exact
                module.PanelTests.test_real_brca100_panels_are_nested_balanced_and_full_exact = unittest.skip(
                    "Original BRCA100 engine fixtures are external; supply --engine-repo")(method)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    return int(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())


if __name__ == "__main__":
    sys.exit(main())
