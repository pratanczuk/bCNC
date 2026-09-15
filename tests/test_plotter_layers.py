"""Layer lifecycle, object editing, persistence and cut-visibility contracts."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for directory in ('bCNC', 'bCNC/lib'):
    sys.path.insert(0, str(ROOT / directory))
import Helpers
from CNC import GCode, Block
from PlotterLayers import LayerManager, catalog, apply_visibility, layer_name
import PlotterProject as project


class LayerTest(unittest.TestCase):
    def setUp(self):
        self.job = GCode()
        self.job.headerFooter()
        for name in ('First', 'Second', 'Third'):
            block = Block(name)
            block.extend(['G0 X1 Y1', 'G1 X5 Y1', 'G1 X5 Y5', 'G1 X1 Y1'])
            block.foil = {'vector': True}
            self.job.blocks.insert(-1, block)
        self.manager = LayerManager(self.job)

    def state(self):
        return project.snapshot(self.job, (225, 300))

    def test_empty_layer_roundtrip_and_undo_redo(self):
        before = self.state()
        self.manager.add('Blue foil', '#345bb1')
        after = self.state()
        self.job.undo(); self.assertEqual(self.state(), before)
        self.job.redo(); self.assertEqual(self.state(), after)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'recovery.foil'
            project.write(path, after)
            blocks, mat = project.read(path)
        self.assertEqual(blocks.layers, catalog(self.job))
        self.assertEqual(mat, (225, 300))
        self.assertEqual(blocks.layers[-1]['name'], 'Blue foil')

    def test_rename_and_both_delete_modes_restore_objects(self):
        self.manager.add('Blue')
        ids = self.manager.move([1, 2], 'Blue')
        self.manager.rename_layer('Blue', 'Red')
        self.assertTrue(all(layer_name(self.job.blocks[i]) == 'Red' for i in ids))
        before = self.state()
        self.manager.delete_layer('Red')
        self.assertEqual(len(self.job.blocks), 5)
        self.assertTrue(all(layer_name(b) == 'Default' for b in self.job.blocks))
        self.job.undo(); self.assertEqual(self.state(), before)
        self.manager.delete_layer('Red', delete_objects=True)
        self.assertEqual([b.name() for b in self.job.blocks], ['Header', 'Third', 'Footer'])
        self.job.undo(); self.assertEqual(self.state(), before)

    def test_layer_exclusion_preserves_individual_choices_and_new_objects(self):
        self.manager.add('Blue')
        ids = self.manager.move([1, 2], 'Blue')
        self.manager.object_properties([ids[1]], enabled=False)
        self.manager.layer_properties('Blue', enabled=False)
        self.assertTrue(all(not self.job.blocks[i].enable for i in ids))
        new = Block('New'); new.foil['layer'] = 'Blue'
        self.job.blocks.insert(-1, new)
        apply_visibility(self.job)
        self.assertFalse(new.enable)
        self.assertTrue(new.foil['object_enabled'])
        self.manager.show_all()
        self.assertTrue(self.job.blocks[ids[0]].enable)
        self.assertFalse(self.job.blocks[ids[1]].enable)
        self.assertTrue(self.job.blocks[-2].enable)

    def test_move_between_excluded_and_included_layers_and_colors(self):
        self.manager.add('Blue', '#345bb1')
        self.manager.layer_properties('Blue', enabled=False)
        ids = self.manager.move([1], 'Blue')
        self.assertFalse(self.job.blocks[ids[0]].enable)
        self.assertEqual(self.job.blocks[ids[0]].color, '#345bb1')
        self.manager.object_properties(ids, color='#b23b3b')
        ids = self.manager.move(ids, 'Default')
        self.assertTrue(self.job.blocks[ids[0]].enable)
        self.assertEqual(self.job.blocks[ids[0]].color, '#b23b3b')
        self.manager.object_properties(ids, color='layer')
        self.assertEqual(self.job.blocks[ids[0]].color, '#166c5e')

    def test_object_properties_duplicate_groups_and_delete_undo(self):
        self.job.blocks[1].foil['text'] = {'text': 'Hello', 'height': 10}
        self.manager.group([1, 2])
        self.manager.object_properties([1], name='Title', passes='3', color='#345bb1')
        before = self.state()
        ids = self.manager.duplicate([1])
        self.assertEqual(len(ids), 2)
        copy = self.job.blocks[ids[0]]
        self.assertEqual(copy.name(), 'Title copy')
        self.assertEqual(copy.passes, 3)
        self.assertEqual(copy.foil['text']['text'], 'Hello')
        self.assertNotEqual(copy.foil['group'], self.job.blocks[1].foil['group'])
        self.assertEqual(copy.foil['group'], self.job.blocks[ids[1]].foil['group'])
        self.job.undo(); self.assertEqual(self.state(), before)
        self.manager.delete_objects([1]); self.job.undo()
        self.assertEqual(self.state(), before)

    def test_layer_object_order_and_drop_before_preserve_wrappers(self):
        self.manager.order_objects([3], -1)
        self.assertEqual([b.name() for b in self.job.blocks], ['Header','First','Third','Second','Footer'])
        self.manager.move([3], 'Default', before=1)
        self.assertEqual(self.job.blocks[1].name(), 'Second')
        self.manager.add('Blue')
        self.manager.move([2], 'Blue')
        self.manager.order_layer('Blue', -1)
        self.assertEqual(self.job.blocks[1].name(), 'First')
        self.assertEqual(self.job.blocks[0].name(), 'Header')
        self.assertEqual(self.job.blocks[-1].name(), 'Footer')

    def test_invalid_actions_and_running_never_mutate(self):
        self.manager.add('Blue')
        for action in (
            lambda: self.manager.add('blue'),
            lambda: self.manager.rename_layer('Blue', 'Default'),
            lambda: self.manager.rename_layer('Default', 'New'),
            lambda: self.manager.delete_layer('Default'),
            lambda: self.manager.delete_objects([0]),
            lambda: self.manager.object_properties([1], name='Header'),
            lambda: self.manager.object_properties([1], passes='1.5'),
            lambda: self.manager.object_properties([1], passes='0'),
            lambda: self.manager.move([1], 'Missing'),
        ):
            before = self.state()
            with self.assertRaises(ValueError): action()
            self.assertEqual(self.state(), before)
        self.manager.running = lambda: True
        before = self.state()
        with self.assertRaises(ValueError): self.manager.add('Blocked')
        self.assertEqual(self.state(), before)

    def test_legacy_migration_and_invalid_catalog(self):
        self.job.blocks[1].foil['layer'] = 'Legacy'
        legacy = self.state(); del legacy['layers']
        blocks, _ = project.decode(legacy)
        self.assertEqual(blocks.layers[-1]['name'], 'Legacy')
        bad = deepcopy(legacy)
        bad['layers'] = [{'name':'Default','color':'#166c5e','enabled':True}]
        with self.assertRaises(ValueError): project.decode(bad)
        bad['layers'][0]['enabled'] = 'yes'
        with self.assertRaises(ValueError): project.decode(bad)

    def test_object_enable_undo_preserves_job_wrappers(self):
        before = self.state()
        self.manager.object_properties([1], enabled=False)
        self.assertFalse(self.job.blocks[1].enable)
        self.job.undo(); self.assertEqual(self.state(), before)
        self.job.redo(); self.assertFalse(self.job.blocks[1].enable)
        with self.assertRaises(ValueError):
            self.manager.object_properties([0], enabled=False)
        self.assertTrue(self.job.blocks[0].enable)


if __name__ == '__main__':
    unittest.main()
