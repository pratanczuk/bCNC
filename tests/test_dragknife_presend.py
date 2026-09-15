"""Exercise real compensation and placement services, without copied algorithms."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for directory in ('bCNC', 'bCNC/lib'):
    sys.path.insert(0, str(ROOT / directory))
import Helpers
from CNC import GCode, Block
from PlotterCompensation import compensate_blocks
from MatManager import snap_blocks_to_mat


def block(name, lines, enabled=True):
    result = Block(name); result.extend(lines); result.enable = enabled
    return result


class CompensationTests(unittest.TestCase):
    def source(self):
        return [block('Header', ['G21', 'G90']),
                block('Artwork', ['G0 X5 Y5', 'G1 X15 Y5', 'G1 X15 Y15', 'G1 X5 Y5']),
                block('Disabled', ['G0 X30 Y30', 'G1 X40 Y40'], False),
                block('Notes', ['(source notes)']),
                block('Footer', ['M5', 'G0 X0 Y0'])]

    def test_wrappers_disabled_blocks_and_notes_survive_compensation(self):
        source = self.source(); before = deepcopy(source)
        source[1].passes = 3; source[1].foil = {'layer': 'Vinyl'}
        result = compensate_blocks(source, .5, 500)
        self.assertEqual(result[0], before[0]); self.assertEqual(result[-1], before[-1])
        self.assertEqual(result[2:4], before[2:4])
        self.assertEqual(result[1].passes, 3); self.assertEqual(result[1].foil, {'layer': 'Vinyl'})
        self.assertNotEqual(result[1], source[1])
        self.assertEqual(source, before)

    def test_no_artwork_returns_no_cut_buffer(self):
        self.assertIsNone(compensate_blocks([block('Header', ['G21'])], .5, 500))

    def test_multiple_contours_are_all_compensated(self):
        source = self.source()[1]
        source.extend(['G0 X25 Y25', 'G1 X35 Y25', 'G1 X35 Y35', 'G1 X25 Y25'])
        result = compensate_blocks([source], .5, 500)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(any(line.startswith('g1') for line in item) for item in result))

    def test_import_placement_preserves_wrappers_and_undo(self):
        document = GCode(); document.blocks = self.source()
        before = deepcopy(document.blocks)
        app = SimpleNamespace(gcode=document, editor=Mock(), canvas=Mock(), drawAfter=Mock(),
                              after=Mock(), setStatus=Mock())
        snap_blocks_to_mat(app, [1])
        self.assertEqual(document.blocks[0], before[0]); self.assertEqual(document.blocks[-1], before[-1])
        for coordinate in document.toPath(1)[0].bbox()[:2]:
            self.assertAlmostEqual(coordinate, 0, places=4)
        document.undo(); self.assertEqual(document.blocks, before)


if __name__ == '__main__':
    unittest.main()
