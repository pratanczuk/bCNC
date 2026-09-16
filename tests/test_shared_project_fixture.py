"""Compatibility contract used by both implementations."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "bCNC"), str(ROOT / "bCNC/lib")]
from PlotterProject import read

class SharedProjectFixtureTest(unittest.TestCase):
    def test_rectangle(self):
        blocks, mat = read(ROOT / "fixtures/projects/rectangle.foil")
        self.assertEqual(mat, (300, 300))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].name(), "Rectangle")
        self.assertEqual(list(blocks[0])[-1], "G1 X10 Y10")
