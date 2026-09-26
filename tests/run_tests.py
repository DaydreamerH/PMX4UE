"""No Blender/UE required. Run copied algorithm regressions and workbench tests."""
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / "tools/legacy")]
suite = unittest.TestSuite()
for folder in (root / "tests/inherited", root / "tests"):
    suite.addTests(unittest.TestLoader().discover(str(folder), pattern="test_*.py"))
raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
