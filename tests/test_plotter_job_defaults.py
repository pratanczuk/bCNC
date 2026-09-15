"""Generated vector jobs never depend on a pressure-bearing default header."""
import sys
from pathlib import Path
import unittest
from copy import deepcopy
ROOT = Path(__file__).resolve().parents[1] / 'bCNC'
for path in (ROOT, ROOT / 'lib', ROOT / 'controllers'):
    sys.path.insert(0, str(path))
import Helpers
from CNC import Block, GCode
from PlotterPlanning import JobParameters, prepare_job
from PlotterShapes import SimpleRectangle


class JobDefaultsTest(unittest.TestCase):
    def artwork(self):
        job = GCode(); job.headerFooter()
        shape = SimpleRectangle('Square').calc(10, 10, 20, 20, 0, True)
        for block in shape:
            block.foil['vector'] = True
        job.blocks[1:1] = shape
        return job.blocks

    def test_current_settings_generates_pressure_for_every_outline(self):
        for compensation in (False, True):
            blocks = self.artwork()
            before = deepcopy(blocks)
            result = prepare_job(blocks, JobParameters(speed=750, pressure=350, compensate=compensation))
            self.assertEqual([list(b) for b in blocks], [list(b) for b in before])
            self.assertEqual(result[-1][-1], 'M5')
            for block in result[1:-1]:
                self.assertEqual(block[0], 'M5')
                self.assertTrue(block[1].startswith('G0 X'))
                self.assertEqual(block[2], 'M3 S350')
                self.assertEqual(block[-1], 'M5')
                self.assertTrue(all('F750' in line for line in block if line.startswith(('G1 ', 'G2 ', 'G3 '))))
                self.assertFalse(any('Z' in line for line in block))
            self.assertFalse(any('$H' in line or '$G' in line for b in result for line in b))

    def test_current_settings_keeps_pass_count_and_disabled_objects(self):
        blocks = self.artwork(); blocks[1].passes = 3
        disabled = deepcopy(blocks[1]); disabled.enable = False
        blocks.insert(2, disabled)
        result = prepare_job(blocks, JobParameters())
        self.assertEqual(len(result), 3)
        self.assertEqual(result[1].passes, 3)

    def test_raw_machine_commands_are_retained(self):
        block = Block('Imported'); block.extend(['M5', 'G0 X10 Y10 Z3', 'M3 S350', 'G1 Z0', 'G1 X20 F750', 'M5'])
        result = prepare_job([block], JobParameters(speed=750, pressure=350), use_material=False)
        self.assertEqual(list(result[0]), list(block))

    def test_custom_job_header_footer_remain_explicit(self):
        blocks = self.artwork()
        blocks[0][:] = ['(custom header)', 'G90']
        blocks[-1][:] = ['M5', '(custom footer)']
        result = prepare_job(blocks, JobParameters())
        self.assertIn('(custom header)', result[0])
        self.assertIn('(custom footer)', result[-1])

    def test_mixed_raw_and_vector_job_requires_separate_execution(self):
        blocks = self.artwork()
        raw = Block('Machine commands'); raw.extend(['G1 X12 F500'])
        blocks.insert(2, raw)
        with self.assertRaisesRegex(ValueError, 'separate jobs'):
            prepare_job(blocks, JobParameters())

    def test_saved_old_templates_migrate_but_custom_commands_do_not(self):
        import configparser
        from PlotterPreferences import migrate_job_defaults
        config = configparser.ConfigParser(interpolation=None)
        config.read_dict({'CNC': {'header': '$H\n$G\nM3 S220 F1500',
                                  'footer': 'G4 P0.1\nM5\n$H\n$G\nG0 Y0'}})
        migrate_job_defaults(config)
        self.assertEqual(config.get('CNC', 'header'), 'M5\nG21 G90 G17 G94')
        self.assertEqual(config.get('CNC', 'footer'), 'M5')
        config.set('CNC', 'header', '(Custom machine)\nM3 S350')
        migrate_job_defaults(config)
        self.assertEqual(config.get('CNC', 'header'), '(Custom machine)\nM3 S350')
