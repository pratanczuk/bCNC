"""Architectural regressions for the supported application, not callback guesses."""
import ast
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for directory in ('bCNC', 'bCNC/lib'):
    sys.path.insert(0, str(ROOT / directory))
import Helpers
from CNC import CNC, GCode, Block
from PlotterCompensation import compensate_blocks
from PlotterKnife import compensate_path
from PlotterPath import path_to_block
from bmath import Vector
from bpath import Path as Contour, Segment


class ArchitectureTests(unittest.TestCase):
    def test_unused_report_contains_only_required_font_callbacks(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('unused_audit', ROOT / 'tools/audit_unused.py')
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        found = {(str(path.relative_to(ROOT / 'bCNC')), name)
                 for path, line, name in audit.candidates(ROOT / 'bCNC', True)}
        self.assertEqual(found, {('lib/font_text.py', name) for name in
                                ('_moveTo', '_curveToOne', '_closePath', '_endPath')})

    def test_compilation_cancellation_and_transforms_preserve_source(self):
        from PlotterCompilation import compile_buffer
        from PlotterTransforms import transform_document
        document = GCode()
        block = Block('Artwork'); block.extend(['G0 X5 Y5', 'G1 X10 Y10'])
        document.blocks = [block]
        original = list(block)
        with self.assertRaises(InterruptedError):
            compile_buffer(document.blocks, lambda: True)
        self.assertEqual(block, original)
        commands = compile_buffer(document.blocks)
        self.assertTrue(any('G1' in line.upper() for line in commands if isinstance(line, str)))
        with self.assertRaises(ValueError):
            transform_document(document, [0], 'MOVE', float('nan'), 0, 0)
        self.assertEqual(block, original)
        transform_document(document, [0], 'MOVE', 2, 3, 0)
        self.assertNotEqual(block, original)
        document.undo()
        self.assertEqual(document.blocks[0], original)

    def test_parsers_keep_modes_and_bounds_separate_from_live_status(self):
        live = deepcopy(CNC.vars)
        first, second = CNC(), CNC()
        first.motionStart(CNC.parseLine('G93 G1 X10 F2'))
        second.motionStart(CNC.parseLine('G94 G1 X20 F300'))
        block = Block('Preview')
        block.xmin, block.ymin, block.zmin = 1, 2, 0
        block.xmax, block.ymax, block.zmax = 8, 9, 0
        first.pathMargins(block)
        self.assertEqual(first.feedmode, 93)
        self.assertEqual(second.feedmode, 94)
        self.assertEqual(first.bounds['xmin'], 1)
        self.assertFalse(second.isMarginValid())
        self.assertEqual(CNC.vars, live)

    def test_compensation_cannot_change_document_or_application_state(self):
        block = Block('Square')
        block.extend(['G0 X10 Y10', 'G1 X20 Y10', 'G1 X20 Y20', 'G1 X10 Y20', 'G1 X10 Y10'])
        source = deepcopy(block)
        before = deepcopy(CNC.vars)
        result = compensate_blocks([block], .5, 500, 1)
        self.assertTrue(result)
        self.assertEqual(block, source)
        self.assertEqual(CNC.vars, before)

    def test_geometry_has_no_application_or_controller_dependencies(self):
        for filename in ('PlotterKnife.py', 'PlotterGeometry.py'):
            tree = ast.parse((ROOT / 'bCNC' / filename).read_text())
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.add((node.module or '').split('.')[0])
            self.assertFalse(imports & {'CNC', 'Utils', 'tkinter', 'Sender', 'bmain', 'PlotterAdapters'})

    def test_open_contour_does_not_get_closed_path_overcut(self):
        path = Contour('Open')
        path.append(Segment(Segment.LINE, Vector(10, 10), Vector(20, 10)))
        a = compensate_path(path, .5, 0)
        b = compensate_path(path, .5, 2)
        self.assertAlmostEqual(a.length(), b.length())
        self.assertEqual(len(path), 1)
        with self.assertRaises(ValueError):
            compensate_path(path, float('nan'))

    def test_planar_serializer_preserves_arcs_and_explicit_parameters(self):
        path = Contour('Arc')
        path.append(Segment(Segment.CCW, Vector(20, 10), Vector(10, 20), Vector(10, 10)))
        result = path_to_block(path, feed=345, safe=2, digits=4)
        job = GCode(); job.blocks = [result]
        decoded = job.toPath(0)[0]
        self.assertEqual(decoded[0].type, Segment.CCW)
        self.assertAlmostEqual(decoded.length(), path.length())
        self.assertTrue(any('f345' in line for line in result))
        self.assertEqual(result[-1], 'g0 z2.0')

    def test_retired_plugin_and_command_shell_cannot_return(self):
        for name in ('tkExtra.py', 'tkDialogs.py', 'bFileDialog.py', 'rexx.py'):
            self.assertFalse((ROOT / 'bCNC' / 'lib' / name).exists())
        self.assertFalse(list((ROOT / 'bCNC' / 'plugins').glob('*.py')))
        self.assertFalse((ROOT / 'bCNC' / 'PlotterLegacy.py').exists())
        for filename in ('Sender.py', 'bmain.py'):
            tree = ast.parse((ROOT / 'bCNC' / filename).read_text())
            names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
            self.assertFalse(names & {'executeCommand', 'executeGcode', 'insertCommand'})


if __name__ == '__main__':
    unittest.main()
