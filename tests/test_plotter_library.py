"""Profile lifecycle, portable layer setups and pen-safe compiled jobs."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch
from test_plotter_services import ROOT
from CNC import Block, GCode
from PlotterLibrary import ProfileLibrary, validate_profile, validate_process
from PlotterLayers import LayerManager, catalog
from PlotterPlanning import JobParameters, prepare_job
from PlotterProject import snapshot, decode
from PlotterCompilation import compile_buffer


def artwork(name='Artwork', layer='Default'):
    block = Block(name)
    block.extend(['G90 G21', 'G0 X10 Y10', 'G1 X20 Y10 F100', 'G1 X20 Y20', 'G1 X10 Y20', 'G1 X10 Y10'])
    block.foil = {'vector': True, 'layer': layer}
    return block


def process(kind='Pen', name='Fine black'):
    return validate_process({'operation': 'Draw' if kind=='Pen' else 'Cut',
        'tool': {'name':name,'kind':kind,'compensate':True,'offset':.5,'overcut':2},
        'material': {'name':'Paper','pressure':120,'speed':700,'passes':2,'compatible':'Both'}})


class ProfileLibraryTests(unittest.TestCase):
    def test_crud_rename_duplicate_and_reload(self):
        lib = ProfileLibrary()
        lib.save('materials', {'name':'Vinyl','pressure':350})
        lib.save('materials', {'name':'Matte vinyl','pressure':400}, 'Vinyl')
        copy = lib.duplicate('materials','Matte vinyl')
        lib.delete('materials','Matte vinyl')
        lib.save('tools',{'name':'Black fine','kind':'Pen'})
        restored = ProfileLibrary(json.loads(json.dumps(lib.snapshot())))
        self.assertEqual(restored.records, lib.records)
        self.assertEqual(restored.records['materials'][copy]['pressure'],400)
        with self.assertRaises(ValueError): restored.save('tools', {'name':'black FINE','kind':'Pen'})

    def test_invalid_edit_is_atomic_and_pen_values_are_forced_off(self):
        lib = ProfileLibrary(); lib.save('tools',{'name':'Knife'})
        before = lib.snapshot()
        for fields in ({'offset':float('nan')}, {'angle':100}, {'name':''}):
            with self.assertRaises(ValueError): lib.save('tools',dict({'name':'Knife'},**fields),'Knife')
            self.assertEqual(lib.snapshot(),before)
        pen = validate_profile('tools',{'name':'Pen','kind':'Pen','compensate':True,'offset':9,'overcut':19})
        self.assertFalse(pen['compensate'])
        self.assertEqual((pen['offset'],pen['overcut']), (0,0))
        for raw in ({'passes':1.5}, {'pressure':1001}, {'speed':0}, {'thickness':-1}):
            with self.assertRaises(ValueError): validate_profile('materials',dict(name='Test',**raw))

    def test_existing_presets_migrate_without_losing_calibration(self):
        lib = ProfileLibrary(materials={'Vinyl':{'speed':1200,'strength':350}},
            blades={'Holder':{'mat_knife_offset':.25,'mat_overcut':.4,'mat_auto_dragknife':True}})
        self.assertEqual(lib.records['materials']['Vinyl']['pressure'],350)
        self.assertEqual(lib.records['tools']['Holder']['offset'],.25)

    def test_layer_snapshots_survive_library_deletion_project_roundtrip_and_undo(self):
        doc = GCode(); doc.blocks=[artwork()]
        lib = ProfileLibrary(); lib.save('tools',{'name':'Pen','kind':'Pen'})
        assignment = {'operation':'Draw','tool':lib.records['tools']['Pen']}
        manager = LayerManager(doc); manager.set_process('Default',assignment)
        lib.delete('tools','Pen')
        data = snapshot(doc,(225,300))
        restored, mat = decode(json.loads(json.dumps(data)))
        self.assertEqual(restored.layers[0]['process']['tool']['name'],'Pen')
        self.assertEqual(restored.layers[0]['process']['tool']['offset'],0)
        doc.undo(); self.assertNotIn('process',catalog(doc)[0])
        doc.redo(); self.assertEqual(catalog(doc)[0]['process']['operation'],'Draw')
        data['layers'][0]['process']['operation']='Cut'
        with self.assertRaises(ValueError): decode(data)

    def test_operation_tool_and_material_compatibility(self):
        assignment = process()
        assignment['material']['compatible']='Knife'
        with self.assertRaises(ValueError): validate_process(assignment)
        assignment=process(); assignment['operation']='Cut'
        with self.assertRaises(ValueError): validate_process(assignment)

    def test_pen_never_calls_compensation_even_with_global_and_imported_flags(self):
        source=[artwork()]; original=deepcopy(source)
        assignment=process(); assignment['tool'].update(compensate=True,offset=5,overcut=10)
        params=JobParameters(compensate=True,knife_offset=5,overcut=10,processes={'Default':assignment})
        with patch('PlotterProcesses.compensate_path',side_effect=AssertionError('Pen compensation called')):
            prepared=prepare_job(source,params)
            commands=compile_buffer(prepared)
        body=[b for b in prepared if b.name()=='Artwork'][0]
        self.assertEqual(body.passes,2)
        self.assertTrue(any('S120' in str(line) for line in commands))
        self.assertTrue(any('F700' in str(line).upper() for line in commands))
        self.assertFalse(any('G2 ' in str(line).upper() or 'G3 ' in str(line).upper() for line in commands))
        self.assertEqual(list(source[0]),list(original[0]))
        self.assertEqual(source[0].foil,original[0].foil)
        self.assertEqual(str(commands[-1]).strip().upper(),'M5')

    def test_pen_travel_releases_tool_and_uses_no_z_axis(self):
        from CNC import CNC
        prepared=prepare_job([artwork()],JobParameters(processes={'Default':process()}))
        down=False; travelled=False; drew=False
        for command in compile_buffer(prepared):
            if not isinstance(command,str): continue
            words={word.upper() for word in (CNC.parseLine(command) or [])}
            self.assertFalse(any(word.startswith('Z') for word in words))
            if 'M5' in words: down=False
            if 'M3' in words: down=True
            if 'G0' in words and any(word.startswith(('X','Y')) for word in words):
                self.assertFalse(down); travelled=True
            if 'G1' in words:
                self.assertTrue(down); drew=True
        self.assertTrue(travelled and drew)
        self.assertFalse(down)

    def test_selected_material_passes_apply_to_current_settings_and_pen_compatibility(self):
        material=validate_profile('materials',{'name':'Vinyl','passes':3,'pressure':350,'speed':800})
        source=[artwork()]
        prepared=prepare_job(source,JobParameters(material=material))
        contours = [b for b in prepared if b.name() not in ('Header', 'Footer')]
        self.assertEqual(contours[0].passes,3)
        self.assertTrue(any('F800' in line.upper() for line in contours[0]))
        self.assertEqual(source[0].passes,1)
        material['compatible']='Knife'
        pen=process(); pen['material']=None
        with self.assertRaisesRegex(ValueError,'not compatible'):
            prepare_job(source,JobParameters(processes={'Default':pen},material=material))

    def test_mixed_tools_require_explicit_pass_and_only_selected_tool_is_prepared(self):
        blocks=[artwork('Drawing','Ink'),artwork('Cutout','Foil')]
        params=JobParameters(processes={'Ink':process(),'Foil':process('Knife','Swivel')})
        with self.assertRaisesRegex(ValueError,'several tools'): prepare_job(blocks,params)
        with patch('PlotterProcesses.compensate_path') as compensate:
            output=prepare_job(blocks,replace(params,tool_pass='Pen · Fine black'))
            compensate.assert_not_called()
        self.assertIn('Drawing',[b.name() for b in output])
        self.assertNotIn('Cutout',[b.name() for b in output])
        from PlotterKnife import compensate_path
        with patch('PlotterProcesses.compensate_path',wraps=compensate_path) as compensate:
            output=prepare_job(blocks,replace(params,tool_pass='Knife · Swivel'))
            compensate.assert_called()
        self.assertNotIn('Drawing',[b.name() for b in output])
        with self.assertRaisesRegex(ValueError,'no included objects'):
            prepare_job(blocks,replace(params,tool_pass='Deleted tool'))

    def test_layer_name_case_cannot_bypass_pen_protection(self):
        source=[artwork(layer='INK')]
        params=JobParameters(compensate=True,processes={'Ink':process()})
        with patch('PlotterProcesses.compensate_path',side_effect=AssertionError('Pen compensated')):
            prepared=prepare_job(source,params)
        self.assertIn('Artwork',[block.name() for block in prepared])

    def test_excluded_pen_layer_cannot_change_active_knife_pass(self):
        pen=artwork('Drawing','Ink'); pen.enable=False
        blocks=[pen,artwork('Cutout','Foil')]
        params=JobParameters(processes={'Ink':process(),'Foil':process('Knife','Swivel')})
        output=prepare_job(blocks,params)
        self.assertNotIn('Drawing',[b.name() for b in output])
