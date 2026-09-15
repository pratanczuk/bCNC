from copy import deepcopy
"""Readiness and real Tk/editor integration, without connecting hardware.

Run GUI cases with xvfb-run -a python -m unittest tests.test_plotter_workflow.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock, PropertyMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bCNC"))
for sub in ("", "lib", "controllers"):
    sys.path.append(os.path.join(ROOT, sub))
import Helpers  # installs gettext before Tk modules are imported
from CNC import CNC, Block
from PlotterJob import bounds_fit, design_bounds, planned_cut_bounds, readiness, apply_cut_settings, SETTING_FIELDS, validate_settings


def block(name, lines):
    result = Block(name)
    result.extend(lines)
    return result


class ReadinessTest(unittest.TestCase):
    def test_retired_commands_rejected_before_compiler_queue_changes(self):
        from CNC import GCode
        from queue import Queue
        for command in ('G81 X10 Z-2', 'G38.2 Z-5', 'M6 T1', 'G98'):
            job = GCode()
            job.blocks = [block('Header', ['G90', 'M3 S300']), block('Old job', [command])]
            queue = Queue()
            with self.subTest(command=command), self.assertRaises(ValueError):
                job.compile(queue)
            self.assertTrue(queue.empty())

    def test_command_validation_preserves_blade_motion_and_ignores_comments(self):
        from PlotterPlanning import validate_plotter_commands
        ignored = block('Disabled old operation', ['G83 Z-5'])
        ignored.enable = False
        validate_plotter_commands([block('Cut', ['G80', 'G0 Z3', 'M3 S500',
            'G1 Z0 F80', 'G2 X20 Y10 I5 J0', '(M6 G81)', '; G38.2']), ignored])
        with self.assertRaises(ValueError):
            validate_plotter_commands([], 'G90\nM6')

    def test_plotter_controls_use_single_sender(self):
        from PlotterEngine import PlotterEngine
        app = Mock(sender=Mock(running=False))
        from PlotterAdapters import DocumentJobPort
        engine = PlotterEngine(DocumentJobPort(app))
        engine.pause()
        app.sender.pause.assert_not_called()
        engine.start()
        app.run.assert_called_once_with()
        app.sender.running = True
        engine.pause()
        engine.stop()
        app.sender.pause.assert_called_once_with()
        app.sender.stopRun.assert_called_once_with()

    def test_grblhal_alarms_and_unknown_codes_have_guidance(self):
        from PlotterErrors import friendly_error, can_unlock
        for code in range(1, 23):
            title, message, action, target = friendly_error('Controller fault', f'ALARM:{code}')
            self.assertNotIn('ALARM:', title + message)
            self.assertEqual(target, 'diagnostics')
        for state in ('ALARM:10', 'ALARM:17', 'ALARM:255', 'Alarm'):
            self.assertFalse(can_unlock(state))
        self.assertIn('Emergency stop', friendly_error('Fault', 'error:50')[0])
        self.assertIn('unfamiliar', friendly_error('Fault', 'ALARM:255')[1])
        self.assertEqual(friendly_error('Internal application error', 'Traceback USB failure')[0], 'This action couldn’t finish')

    def test_errors_have_specific_guidance_without_exposing_raw_details(self):
        from PlotterErrors import friendly_error
        for detail, title in [('[Errno 2] No such file or directory: /dev/ttyUSB0', 'find'),
                              ('Permission denied', 'allowed'), ('Port is busy', 'in use')]:
            heading, message, action, target = friendly_error('Could not connect', detail)
            self.assertIn(title, heading)
            self.assertNotIn(detail, message)
            self.assertEqual(target, 'connection')

    def test_compound_boolean_operations_and_holes(self):
        from PlotterDesign import shape_paths
        from PlotterGeometry import combine_paths, outlines_geometry
        a = shape_paths('Rectangle', 20, 20)
        from bmath import Vector
        from bpath import Path, Segment
        b = [Path('B')]
        points = [Vector(10, 0), Vector(30, 0), Vector(30, 20), Vector(10, 20)]
        for i, point in enumerate(points):
            b[0].append(Segment(Segment.LINE, point, points[(i+1)%4]))
        for op, area in [('union', 600), ('difference', 200), ('intersection', 200), ('symmetric_difference', 400)]:
            result = combine_paths([a, b], op)
            self.assertAlmostEqual(outlines_geometry(result).area, area)
        self.assertEqual(len(combine_paths([a, b], 'combine')), 2)
        self.assertEqual(combine_paths([a, a], 'difference'), [])
        hole = [Path('Hole')]
        points = [Vector(5, 5), Vector(10, 5), Vector(10, 10), Vector(5, 10)]
        for i, point in enumerate(points):
            hole[0].append(Segment(Segment.LINE, point, points[(i+1)%4]))
        ring = combine_paths([a, hole], 'difference')
        self.assertEqual(len(ring), 2)
        self.assertAlmostEqual(outlines_geometry(ring).area, 375)
        self.assertAlmostEqual(outlines_geometry(combine_paths([ring, hole], 'union')).area, 400)

    def test_basic_shapes_are_closed_and_have_requested_dimensions(self):
        from PlotterDesign import shape_paths, path_bounds
        for kind in ('Rectangle', 'Circle', 'Ellipse', 'Triangle', 'Star'):
            paths = shape_paths(kind, 40, 30)
            self.assertTrue(paths[0].isClosed())
            x0, y0, x1, y1 = path_bounds(paths)
            self.assertAlmostEqual(x1-x0, 40, delta=1e-5)
            self.assertAlmostEqual(y1-y0, 40 if kind == 'Circle' else 30, delta=1e-5)
        for invalid in ('nan', 'inf', '-2', '0'):
            with self.assertRaises(ValueError):
                shape_paths('Circle', invalid, 20)

    def test_settings_validate_entire_draft_and_reject_nonfinite_values(self):
        draft = {key: default for key, (_, default, _, _) in SETTING_FIELDS.items()}
        draft['mat_auto_dragknife'] = True
        self.assertEqual(validate_settings(draft)['mat_overcut'], 0)
        for key, value in [('mat_width', 0), ('mat_pressure', 1001),
                           ('mat_overcut', -1), ('mat_speed', 'nan'), ('mat_height', 'inf')]:
            invalid = dict(draft, **{key: value})
            with self.assertRaises(ValueError):
                validate_settings(invalid)

    def test_ready_requires_connection_idle_geometry_and_mat_confirmation(self):
        args = [True, "Idle", False, (5, 5, 15, 15), 300, 300, True]
        self.assertEqual(readiness(*args), "")
        for index, value in ((0, False), (1, "Alarm:1"), (2, True),
                             (3, None), (4, 10), (6, False)):
            invalid = args.copy()
            invalid[index] = value
            self.assertTrue(readiness(*invalid))

    def test_empty_invalid_and_outside_bounds(self):
        for bounds in (None, (-1, 0, 10, 10), (0, 0, 301, 10), (0, 0, float('nan'), 1)):
            self.assertFalse(bounds_fit(bounds, 300, 300))
        self.assertFalse(bounds_fit((0, 0, 10, 10), float('inf'), 300))
        self.assertTrue(bounds_fit((0, 0, 300, 300), 300, 300))

    def test_arc_extrema_are_checked_not_just_endpoints(self):
        blocks = [block("Arc", ["G21 G90", "G0 X5 Y5", "G2 X15 Y5 I5 J0"])]
        bounds = planned_cut_bounds(blocks)
        self.assertAlmostEqual(bounds[3], 10, delta=0.00001)
        self.assertFalse(bounds_fit(bounds, 20, 9))

    def test_units_relative_moves_and_disabled_blocks(self):
        excluded = block("Excluded", ["G0 X0 Y0", "G1 X1000 Y1000"])
        excluded.enable = False
        blocks = [block("Design", ["G20 G90", "G0 X1 Y1", "G91", "G1 X1 Y1"]), excluded]
        bounds = planned_cut_bounds(blocks)
        self.assertAlmostEqual(bounds[0], 25.4, delta=0.00001)
        self.assertAlmostEqual(bounds[2], 50.8, delta=0.00001)

    def test_relative_passes_and_modal_word_order(self):
        design = block("Design", ["G91", "G1 X10 Y10"])
        design.passes = 3
        self.assertAlmostEqual(planned_cut_bounds([design])[2], 30, delta=0.00001)
        design = block("Design", ["G0 X0 Y0", "X1 Y1 G20 G1"])
        self.assertAlmostEqual(planned_cut_bounds([design])[2], 25.4, delta=0.00001)

    def test_plan_uses_current_position_and_startup_mode(self):
        design = block("Design", ["G1 X10 Y10"])
        bounds = planned_cut_bounds([design], (100, 100, 0), "G91")
        self.assertAlmostEqual(bounds[2], 110, delta=0.00001)

    def test_unsupported_coordinate_changes_are_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            planned_cut_bounds([block("Design", ["G53 G0 X10", "G1 X20"])])
        with self.assertRaises(ValueError):
            planned_cut_bounds([block("Design", ["%wait", "G1 X10"])])

    def test_material_settings_apply_without_changing_source_and_convert_units(self):
        header = block("Header", ["M3 S100"])
        source = block("Design", ["G20", "G0 X0 Y0", "G1 X1 F1", "Y2"])
        result = apply_cut_settings([header, source], 254, 350)
        self.assertIn("S350", result[0][0])
        self.assertIn("F10.0000", result[1][2])
        self.assertIn("F10.0000", result[1][3])
        self.assertEqual(source[2], "G1 X1 F1")
        self.assertEqual(header[0], "M3 S100")
        with self.assertRaises(ValueError):
            apply_cut_settings([source], 0, 350)
        source = block("Design", ["G1 Z-1 F50", "G1 X1"])
        result = apply_cut_settings([source], 254, 350, "G20")
        self.assertEqual(result[0][0], source[0])
        self.assertIn("F10.0000", result[0][1])

    def test_compensation_overhang_does_not_fit_even_when_design_fits(self):
        self.assertTrue(bounds_fit((0, 0, 300, 100), 300, 300))
        actual = planned_cut_bounds([block("Compensated", ["G0 X0 Y10", "G1 X300.5 Y10"])])
        self.assertFalse(bounds_fit(actual, 300, 300))


@unittest.skipUnless(os.environ.get("DISPLAY"), "Requires an X display (use xvfb-run)")
class WorkflowGUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import Utils
        cls.temp = tempfile.TemporaryDirectory()
        cls.old_ini, cls.old_history = Utils.iniUser, Utils.hisFile
        Utils.iniUser = os.path.join(cls.temp.name, "settings.ini")
        Utils.hisFile = os.path.join(cls.temp.name, "history")
        import bmain
        Utils.loadConfiguration()
        # Startup must tolerate settings written by the retired interface.
        Utils.setBool("Connection", "pendant", True)
        Utils.setStr(Utils.__prg__, "file.ribbon", "File Pendant Options Close")
        Utils.setStr(Utils.__prg__, "ribbon", "File Probe Control CAM Editor Terminal>")
        Utils.setStr(Utils.__prg__, "page", "Probe")
        Utils.setStr(Utils.__prg__, "tool", "EndMill")
        Utils.setBool("Connection", "openserial", False)
        cls.app = bmain.Application()
        cls.app.geometry("1024x768")
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        import Utils
        cls.app.destroy()
        Utils.iniUser, Utils.hisFile = cls.old_ini, cls.old_history
        cls.temp.cleanup()

    def add_square_fixture(self):
        from PlotterShapes import SimpleRectangle
        a = self.app
        blocks = SimpleRectangle('Test square · 10 mm').calc(5, 5, 15, 15, 0, True)
        for block in blocks:
            block.foil['vector'] = True
        a.gcode.insBlocks(1, blocks, 'Test square fixture')
        a.refresh()

    def setUp(self):
        a = self.app
        for page in list(getattr(a, 'workspace_pages', []))[::-1]:
            page.destroy()
        a.sender.serial = None
        a.sender.firmware = None
        CNC.vars["mpg"] = False
        a.sender.running = False
        a.sender.emptyQueue()
        CNC.vars["state"] = "Not connected"
        CNC.vars["mat_auto_dragknife"] = False
        CNC.vars["mat_confirmation_invalid"] = False
        a.gcode.init()
        a.gcode.headerFooter()
        self.add_square_fixture()
        a.draw()
        a.workflow.update_state()

    def test_standard_file_dialog_cancel_and_planar_canvas(self):
        a = self.app
        with patch('bmain.filedialog.askopenfilename', return_value='') as choose, patch.object(a, 'load') as load:
            a.loadDialog()
            self.assertIs(choose.call_args.kwargs['parent'], a)
            load.assert_not_called()
        with patch('bmain.filedialog.asksaveasfilename', return_value='') as choose, patch.object(a, 'save') as save:
            a.saveDialog()
            self.assertIs(choose.call_args.kwargs['parent'], a)
            save.assert_not_called()
        a.canvas.zoom = 2
        self.assertEqual(a.canvas.plotCoords([(5, 7, 100)]), [(10, -14)])
        self.assertEqual(a.canvas.canvas2xyz(10, -14), (5, 7, 0))
        a.workflow.fit_mat()

    def test_closed_design_dialog_cannot_invoke_later_dialog_actions(self):
        a = self.app
        design = a.workflow.design_dialog('ShapeDialog')
        pending = design.controls_binding
        design.destroy()
        self.assertNotIn(pending, a.tk.call('after', 'info'))
        layers = a.workflow.design_dialog('LayersDialog')
        try:
            layers.refresh([1])
            before = list(a.gcode.undoredo.undoList)
            a.update()
            self.assertEqual(layers.ids, [1])
            self.assertEqual(a.gcode.undoredo.undoList, before)
        finally:
            layers.destroy()

    def test_application_composes_sender_and_canvas_shortcuts_use_advanced(self):
        from Sender import Sender
        from types import SimpleNamespace
        import CNCCanvas
        a = self.app
        self.assertNotIsInstance(a, Sender)
        self.assertIsInstance(a.sender, Sender)
        self.assertIs(a.sender.gcode, a.gcode)
        with patch.object(a.workflow, 'open_diagnostics') as advanced, patch.object(a.sender, 'sendGCode') as send:
            a.canvas.handleKey(SimpleNamespace(char='g'))
            a.canvas.click(SimpleNamespace(x=10, y=10, state=CNCCanvas.CONTROLSHIFT_MASK))
            self.assertEqual(advanced.call_count, 2)
            send.assert_not_called()
        with patch.object(a.sender, 'feedHold') as hold, patch.object(a.sender, 'resume') as resume:
            a.event_generate('<<FeedHold>>'); a.event_generate('<<Resume>>'); a.update()
            hold.assert_called_once(); resume.assert_called_once()

    def test_back_next_and_busy_navigation(self):
        a, w = self.app, self.app.workflow
        w.show_step(0)
        self.assertEqual(str(w.back_button['state']), 'disabled')
        w.next_button.invoke()
        self.assertEqual(w.step, 1)
        w.next_button.invoke()
        self.assertEqual(w.step, 2)
        w.back_button.invoke()
        self.assertEqual(w.step, 1)
        for component in (a.mat_handling, a.tool_sequence):
            with patch.object(type(component), 'active', new_callable=PropertyMock, return_value=True, create=True):
                w.update_state()
                self.assertEqual(str(w.back_button['state']), 'disabled')
                w.show_step(0)
                self.assertEqual(w.step, 1)
        w.show_step(-1)
        self.assertEqual(w.step, 1)
        w.show_step(0)

    def test_sidebar_content_stays_left_of_scrollbar_at_supported_sizes(self):
        a, w = self.app, self.app.workflow
        for size in ('1024x768', '1280x900'):
            a.geometry(size)
            for step in range(3):
                w.show_step(step)
                a.update()
                right = w.scroll.winfo_rootx() + w.scroll.winfo_width()
                self.assertLess(right, w.scrollbar.winfo_rootx())
                self.assertLessEqual(w.content.winfo_width(), w.scroll.winfo_width())
                def check(widget):
                    for child in widget.winfo_children():
                        if child.winfo_ismapped():
                            self.assertLessEqual(child.winfo_rootx() + child.winfo_width(), right,
                                                 str(child))
                            check(child)
                check(w.content)
                self.assertTrue(w.next_button.winfo_ismapped())
        a.geometry('1024x768')
        w.show_step(0)

    def test_outline_addition_preserves_source_position_and_undo(self):
        a = self.app
        a.workflow.show_step(0)
        source = [list(b) for b in a.gcode.blocks]
        a.editor.select([(1, None)], clear=True)
        dialog = a.workflow.design_dialog('OutlineDialog')
        dialog.mode.set('Weeding border')
        dialog.distance.set('1')
        with patch.object(a.sender, 'sendGCode') as send:
            self.assertTrue(dialog.insert())
            send.assert_not_called()
        self.assertEqual([list(b) for b in a.gcode.blocks[:-2]], source[:-1])
        self.assertEqual(a.gcode.blocks[-2].name(), 'Weeding border')
        a.undo()
        self.assertEqual([list(b) for b in a.gcode.blocks], source)

    def test_priority_dialog_controls_keep_usable_width(self):
        a=self.app
        for kind in ('LayoutDialog','LayersDialog','ContourDialog','WeedDialog','CutPreviewDialog','TextDialog'):
            with self.subTest(kind=kind):
                a.editor.select([(1,None)],clear=True)
                d=a.workflow.design_dialog(kind); a.update()
                self.assertGreater(d.controls.winfo_width(),230)
                self.assertTrue(d.insert_button.winfo_ismapped())
                self.assertLessEqual(d.insert_button.winfo_rooty()+d.insert_button.winfo_height(),d.winfo_rooty()+d.winfo_height())
                d.destroy()
        d=a.workflow.design_dialog('ProjectsDialog'); a.update()
        def buttons(widget):
            import tkinter
            for child in widget.winfo_children():
                if isinstance(child,tkinter.Button): yield child
                yield from buttons(child)
        for button in buttons(d):
            self.assertTrue(button.winfo_ismapped())
            # Project lists scroll; the fixed Close action must remain in view.
            if button.cget('text') == 'Close':
                self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),d.winfo_rooty()+d.winfo_height())
        d.destroy()

    def test_canvas_selection_expands_group_and_native_move_preserves_text(self):
        a=self.app
        a.editor.select([],clear=True)
        d=a.workflow.design_dialog('TextDialog')
        d.text.delete('1.0','end'); d.text.insert('1.0','A'); d.height.set('10')
        self.assertTrue(d.insert())
        index=a.editor.getSelectedBlocks()[0]
        a.gcode.blocks[1].foil['group']='group'
        a.gcode.blocks[index].foil['group']='group'
        a.editor.select([(index,None)],clear=True); a.selectionChange()
        self.assertEqual(set(a.editor.getSelectedBlocks()),{1,index})
        a.workflow.transform('MOVE',2,3,0)
        self.assertEqual(a.gcode.blocks[index].foil['rendered'],list(a.gcode.blocks[index]))
        a.undo()
        self.assertEqual(a.gcode.blocks[index].foil['rendered'],list(a.gcode.blocks[index]))

    def test_project_layout_repeat_and_undo(self):
        a=self.app
        source=[list(b) for b in a.gcode.blocks]
        a.editor.select([(1,None)],clear=True)
        d=a.workflow.design_dialog('LayoutDialog')
        d.operation.set('Repeat grid'); d.rows.set('2'); d.columns.set('3'); d.gap.set('4')
        with patch.object(a.sender,'sendGCode') as send:
            self.assertTrue(d.insert()); send.assert_not_called()
        self.assertEqual(len(a.gcode.blocks),8)
        a.undo(); self.assertEqual([list(b) for b in a.gcode.blocks],source)

    def test_attached_group_moves_as_unit_and_layers_filter_cut(self):
        a=self.app
        a.workflow.duplicate()
        ids=[i for i,b in enumerate(a.gcode.blocks) if b.name() not in ('Header','Footer')]
        a.editor.select([(i,None) for i in ids],clear=True)
        d=a.workflow.design_dialog('LayersDialog'); self.assertTrue(d.attach())
        a.editor.select([(ids[0],None)],clear=True)
        self.assertEqual(a.workflow.selection(),ids)
        self.assertTrue(d.add_layer('Blue foil'))
        d.refresh(ids)
        d.target_layer.set('Blue foil'); self.assertTrue(d.assign())
        ids=d.ids[:]
        self.assertTrue(d.exclude())
        self.assertTrue(all(not a.gcode.blocks[i].enable for i in ids))
        self.assertIsNone(design_bounds(a.gcode.blocks))
        d.history(False); self.assertTrue(all(a.gcode.blocks[i].enable for i in ids))
        d.destroy()

    def test_layer_manager_lifecycle_objects_and_drag_drop(self):
        from types import SimpleNamespace
        from PlotterLayers import catalog, layer_name
        from PlotterAdapters import DocumentJobPort
        from PlotterPlanning import prepare_job, JobParameters
        a = self.app
        d = a.workflow.design_dialog('LayersDialog')
        try:
            with patch.object(a.sender, 'sendGCode') as send:
                self.assertTrue(d.add_layer('Blue foil'))
                d.layer.set('Red foil'); self.assertTrue(d.rename_layer())
                self.assertEqual(catalog(a.gcode)[-1]['name'], 'Red foil')
                d.refresh([1]); d.object_name.set('My shape')
                self.assertTrue(d.rename_object())
                d.passes.set('3'); self.assertTrue(d.apply_passes())
                d.target_layer.set('Red foil'); self.assertTrue(d.assign())
                self.assertEqual(layer_name(a.gcode.blocks[d.ids[0]]), 'Red foil')
                self.assertTrue(d.duplicate()); self.assertEqual(len(a.gcode.blocks), 4)
                d.refresh('Red foil'); self.assertTrue(d.show_layer(False))
                self.assertTrue(all(not b.enable for b in DocumentJobPort(a).blocks()[1:-1]))
                d.refresh([1]); d.target_layer.set('Default'); self.assertTrue(d.assign())
                self.assertTrue(a.gcode.blocks[d.ids[0]].enable)
                prepared = prepare_job(DocumentJobPort(a).blocks(), JobParameters())
                self.assertEqual(sum(b.enable for b in prepared if b.name() not in ('Header','Footer')), 1)
                # Exercise the actual drag handler onto the excluded layer.
                a.update()
                source = d.tree.bbox(f'object:{d.ids[0]}'); target = d.tree.bbox('layer:1')
                d.press(SimpleNamespace(x=40, y=source[1]+10))
                d.release(SimpleNamespace(x=40, y=target[1]+10))
                self.assertEqual(layer_name(a.gcode.blocks[d.ids[0]]), 'Red foil')
                d.refresh('Red foil'); self.assertTrue(d.delete_layer())
                self.assertEqual(len(a.gcode.blocks), 4)
                self.assertTrue(all(b.enable for b in a.gcode.blocks[1:-1]))
                self.assertTrue(d.history(False)); self.assertEqual(len(catalog(a.gcode)), 2)
                d.refresh('Red foil'); d.delete_mode.set('Delete objects too')
                self.assertTrue(d.delete_layer()); self.assertEqual(len(a.gcode.blocks), 2)
                self.assertTrue(d.history(False)); self.assertEqual(len(a.gcode.blocks), 4)
                d.refresh([1]); self.assertTrue(d.delete_objects())
                self.assertTrue(d.history(False)); self.assertEqual(len(a.gcode.blocks), 4)
                send.assert_not_called()
        finally:
            d.destroy()

    def test_layer_manager_search_stale_guard_and_visible_controls(self):
        a = self.app
        d = a.workflow.design_dialog('LayersDialog')
        try:
            self.assertTrue(d.add_layer('Empty layer'))
            d.search.set('Empty'); a.update()
            self.assertEqual(len(d.tree.get_children()), 1)
            d.search.set(''); d.refresh([1]); a.update()
            def children(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from children(child)
            button = next(w for w in children(d) if w.winfo_class() == 'Button' and w.cget('text') == 'Apply object color')
            self.assertTrue(button.winfo_ismapped())
            # Comfortable controls may need scrolling; the last action stays reachable.
            button.master.master.yview_moveto(1); a.update()
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), d.insert_button.winfo_rooty())
            d.geometry('880x620'); a.update()
            button.master.master.yview_moveto(1); a.update()
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), d.insert_button.winfo_rooty())
            a.gcode.blocks[1]._name = 'Changed elsewhere'
            d.object_name.set('Stale rename'); self.assertFalse(d.rename_object())
            self.assertEqual(a.gcode.blocks[1].name(), 'Changed elsewhere')
        finally:
            d.destroy()

    def test_existing_text_reopens_after_transform_and_is_undoable(self):
        a=self.app
        a.editor.select([],clear=True)
        d=a.workflow.design_dialog('TextDialog')
        d.text.delete('1.0','end'); d.text.insert('1.0','OO')
        d.height.set('10'); d.letter_spacing.set('1'); d.radius.set('30')
        self.assertTrue(d.insert())
        ids=a.editor.getSelectedBlocks(); self.assertEqual(len(ids),1); index=ids[0]
        self.assertIn('text',a.gcode.blocks[index].foil)
        a.workflow.transform('MOVE',20,20,0)
        a.workflow.transform('ROTATE',30,30,30)
        before=list(a.gcode.blocks[index]); old=a.gcode.blocks[index].foil['matrix'][:]
        d=a.workflow.design_dialog('TextDialog')
        self.assertEqual(d.edit_id,index)
        self.assertEqual(d.text.get('1.0','end-1c'),'OO')
        d.text.delete('1.0','end'); d.text.insert('1.0','OB')
        self.assertTrue(d.insert())
        self.assertEqual(a.gcode.blocks[index].foil['matrix'],old)
        a.undo(); self.assertEqual(list(a.gcode.blocks[index]),before)
        self.assertEqual(a.gcode.blocks[index].foil['text']['text'],'OO')

    def test_cut_export_preserves_editable_project_and_sends_nothing(self):
        a=self.app
        a.gcode.filename='original.foil'
        before=[list(b) for b in a.gcode.blocks]; modified=a.gcode.isModified()
        path=os.path.join(self.temp.name,'export.ngc')
        with patch.object(a.sender,'sendGCode') as send:
            self.assertTrue(a.workflow.project.export_cut(path)); send.assert_not_called()
        self.assertTrue(os.path.exists(path))
        self.assertEqual(a.gcode.filename,'original.foil')
        self.assertEqual([list(b) for b in a.gcode.blocks],before)
        self.assertEqual(a.gcode.isModified(),modified)

    def test_mat_dimension_change_marks_project_for_save_and_recovery(self):
        a=self.app
        width=CNC.vars['mat_width']
        a.gcode._modified=False
        d=a.workflow.settings('Mat'); d.values['mat_width'].set(str(width+1))
        self.assertTrue(d.apply())
        self.assertTrue(a.gcode.isModified())
        self.assertEqual(a.workflow.project.data()['mat'][0],width+1)
        CNC.vars['mat_width']=width

    def test_project_roundtrip_and_recovery_never_start_motion(self):
        a=self.app
        path=os.path.join(self.temp.name,'roundtrip.foil')
        a.gcode.blocks[1].foil.update({'group':'test','layer':'Blue'})
        from PlotterLayers import LayerManager, catalog
        LayerManager(a.gcode).add('Empty material')
        saved_layers = catalog(a.gcode)
        source=[list(b) for b in a.gcode.blocks]
        with patch.object(a.sender,'sendGCode') as send, patch.object(a,'run') as run:
            self.assertTrue(a.workflow.project.save(path))
            a.gcode.blocks=[]
            self.assertTrue(a.workflow.project.open(path,recovery=True))
            send.assert_not_called(); run.assert_not_called()
        self.assertEqual([list(b) for b in a.gcode.blocks],source)
        self.assertEqual(a.gcode.blocks[1].foil['layer'],'Blue')
        self.assertEqual(catalog(a.gcode), saved_layers)
        self.assertFalse(a.workflow.confirmed.get())
        self.assertTrue(a.gcode.isModified())
        self.assertEqual(a.gcode.filename,'')

    def test_recovery_snapshot_and_corrupt_load_preserve_current_design(self):
        a=self.app; session=a.workflow.project
        session.last_check=0; session.tick()
        self.assertTrue(session.recovery.exists())
        source=[list(b) for b in a.gcode.blocks]
        path=os.path.join(self.temp.name,'bad.foil')
        with open(path,'w') as f: f.write('{broken')
        with patch.object(a,'fileModified',return_value=False):
            self.assertFalse(session.open(path))
        self.assertEqual([list(b) for b in a.gcode.blocks],source)
        a.workflow.clear_notice(); session.clear_recovery()

    def test_contour_node_change_and_weed_addition_are_undoable(self):
        a=self.app; source=[list(b) for b in a.gcode.blocks]
        a.editor.select([(1,None)],clear=True)
        d=a.workflow.design_dialog('ContourDialog')
        d.operation.set('Move node'); d.node.set('0'); d.x.set('6'); d.y.set('5')
        self.assertTrue(d.insert()); a.undo()
        self.assertEqual([list(b) for b in a.gcode.blocks],source)
        a.editor.select([(1,None)],clear=True)
        d=a.workflow.design_dialog('WeedDialog'); d.spacing.set('3'); d.margin.set('2')
        self.assertTrue(d.insert()); self.assertEqual(a.gcode.blocks[-2].name(),'Weeding cuts')
        a.undo(); self.assertEqual([list(b) for b in a.gcode.blocks],source)

    def test_cut_preview_prepares_only_and_order_does_not_modify_artwork(self):
        a=self.app; source=[list(b) for b in a.gcode.blocks]
        with patch.object(a,'run') as run, patch.object(a.sender,'sendGCode') as send:
            d=a.workflow.design_dialog('CutPreviewDialog'); d.order.set(True); d.change_order(); d.rebuild()
            self.assertTrue(d.paths); run.assert_not_called(); send.assert_not_called()
            d.destroy()
        self.assertEqual([list(b) for b in a.gcode.blocks],source)
        CNC.vars['mat_inner_first']=False

    def test_compound_compensation_covers_each_contour_and_preserves_passes(self):
        from PlotterAdapters import DocumentJobPort
        from PlotterGeometry import geometry_paths
        from shapely.geometry import box
        a=self.app
        paths=geometry_paths(box(10,10,40,40).difference(box(20,20,30,30)))
        compound=a.gcode.fromPath(paths,z=0); compound._name='Compound'; compound.passes=2
        a.gcode.blocks[1]=compound
        before=[list(b) for b in a.gcode.blocks]
        result=DocumentJobPort(a).compensate(DocumentJobPort(a).parameters())
        artwork=[b for b in result if b.name() not in ('Header','Footer')]
        self.assertEqual(len(artwork),2); self.assertTrue(all(b.passes==2 for b in artwork))
        self.assertEqual([list(b) for b in a.gcode.blocks],before)

    def test_advanced_header_button_opens_every_tab_without_callback_errors(self):
        a, w = self.app, self.app.workflow
        with patch.object(a, 'report_callback_exception') as errors:
            dialog = w.settings('Advanced')
            a.update()
            try:
                panel = dialog.advanced
                self.assertEqual(set(panel.pages), {'Job G-code', 'Configuration', 'Controller', 'Machine control', 'System'})
                for name, page in panel.pages.items():
                    panel.notebook.select(page)
                    a.update()
                    self.assertTrue(page.winfo_ismapped(), name)
                self.assertIn('travel_x', panel.values)
                self.assertEqual(set(dialog.gcode_editors), {'Header', 'Footer'})
                for source in ('Connection log', 'User configuration', 'System defaults'):
                    panel.source.set(source)
                    panel.buttons['Show'].invoke()
                    self.assertTrue(panel.system_text.get('1.0', 'end-1c'))
                self.assertEqual(str(panel.buttons['Home machine']['state']), 'disabled')
                errors.assert_not_called()
            finally:
                dialog.cancel()
            self.assertIsNone(panel.poll_id)

    def test_advanced_saved_configuration_reopens_after_filtered_disk_save(self):
        import Utils, configparser
        a = self.app
        original = a.tools['CNC']['travel_x']
        try:
            dialog = a.workflow.settings('Advanced')
            dialog.advanced.values['travel_x'].set('321')
            self.assertTrue(dialog.apply())
            with patch.object(Utils, 'delIcons'):
                Utils.saveConfiguration()
            restored = configparser.ConfigParser(interpolation=None)
            restored.read([Utils.iniSystem, Utils.iniUser])
            self.assertEqual(restored.getfloat('CNC', 'travel_x'), 321)
            dialog = a.workflow.settings('Advanced')
            self.assertEqual(float(dialog.advanced.values['travel_x'].get()), 321)
            self.assertTrue(dialog.advanced.validate())
            dialog.cancel()
        finally:
            a.tools['CNC']['travel_x'] = original
            a.tools['CNC'].save()
            CNC.loadConfig(Utils.config)

    def test_advanced_apply_rejects_mat_and_tool_transactions(self):
        a = self.app
        dialog = a.workflow.settings('Advanced')
        try:
            for component in (a.mat_handling, a.tool_sequence):
                with patch.object(type(component), 'active', new_callable=PropertyMock, return_value=True, create=True), patch.object(a.configuration, 'apply') as apply:
                    self.assertFalse(dialog.apply())
                    self.assertIn('finishes', dialog.error.get())
                    apply.assert_not_called()
        finally:
            dialog.cancel()

    def test_advanced_config_cancel_validation_and_apply_do_not_send(self):
        a = self.app
        old = a.tools['CNC']['travel_x']
        dialog = a.workflow.settings('Advanced')
        dialog.advanced.values['travel_x'].set('456')
        dialog.cancel()
        self.assertEqual(a.tools['CNC']['travel_x'], old)
        dialog = a.workflow.settings('Advanced')
        dialog.advanced.values['travel_x'].set('nan')
        self.assertFalse(dialog.apply())
        self.assertIn('travel', dialog.error.get())
        self.assertEqual(a.tools['CNC']['travel_x'], old)
        dialog.advanced.values['travel_x'].set('456')
        with patch.object(a.sender, 'sendGCode') as send:
            self.assertTrue(dialog.apply())
            send.assert_not_called()
        self.assertEqual(CNC.travel_x, 456)
        a.tools['CNC']['travel_x'] = old
        a.tools['CNC'].save()
        import Utils
        CNC.loadConfig(Utils.config)

    def test_manual_jog_is_bounded_and_uses_existing_sender(self):
        a = self.app
        a.sender.serial = Mock(); CNC.vars['state'] = 'Idle'
        dialog = a.workflow.settings('Advanced')
        panel = dialog.advanced
        a.workflow.confirmed.set(True)
        panel.step.set('1'); panel.feed.set('250')
        panel.jog('X', -1)
        self.assertEqual(a.sender.queue.get_nowait(), '$J=G91 G21 X-1 F250\n')
        self.assertFalse(a.workflow.confirmed.get())
        panel.feed.set('not a speed')
        with self.assertRaisesRegex(ValueError, 'number'): panel.jog('Y', 1)
        panel.feed.set('3001')
        with self.assertRaises(ValueError): panel.jog('Y', 1)
        panel.feed.set('250')
        CNC.vars['state'] = 'Alarm'
        with self.assertRaises(ValueError): panel.jog('Y', 1)
        CNC.vars['state'] = 'Idle'; a.sender.queue.put('pending')
        with self.assertRaises(ValueError): panel.origin()
        a.sender.emptyQueue(); a.sender.serial = None
        with self.assertRaises(ValueError): panel.home()
        self.assertTrue(a.sender.queue.empty())
        dialog.cancel()

    def test_grbl0_jog_restores_distance_and_units(self):
        a = self.app
        a.sender.serial = Mock(); CNC.vars['state'] = 'Idle'
        previous = a.sender.controller
        a.sender.controllerSet('GRBL0')
        old = {key: CNC.vars.get(key) for key in ('units', 'distance', 'feed')}
        CNC.vars.update(units='G20', distance='G90', feed=12)
        dialog = a.workflow.settings('Advanced')
        try:
            dialog.advanced.jog('Z', 1)
            self.assertEqual(list(a.sender.queue.queue), ['G21 G91 G1 Z1 F300\n', 'G20 G90 F12\n'])
        finally:
            dialog.cancel(); a.sender.controllerSet(previous); CNC.vars.update(old); a.sender.emptyQueue(); a.sender.serial = None

    def test_firmware_requires_read_and_sends_only_selected_value(self):
        a = self.app
        a.sender.serial = Mock(); CNC.vars['state'] = 'Idle'
        dialog = a.workflow.settings('Advanced'); panel = dialog.advanced
        with self.assertRaises(ValueError): panel.write_firmware()
        panel.read_firmware()
        self.assertEqual(a.sender.queue.get_nowait(), '$$\n')
        CNC.vars['grbl_100'] = '250'; CNC.vars['grbl_101'] = '250'
        # Refresh the asynchronous settings list without creating another timer.
        a.after_cancel(panel.poll_id); panel.poll()
        panel.firmware.selection_set('grbl_100'); panel.select_firmware()
        panel.firmware_value.set('275')
        panel.write_firmware()
        self.assertEqual(list(a.sender.queue.queue), ['$100=275\n'])
        self.assertEqual(CNC.vars['grbl_100'], '250')  # no false acknowledgement
        a.sender.emptyQueue()
        with self.assertRaises(ValueError): panel.write_firmware()
        panel.firmware.selection_set('grbl_101'); panel.select_firmware()
        a.sender.serial = Mock()
        with self.assertRaises(ValueError): panel.write_firmware()
        self.assertTrue(a.sender.queue.empty())
        dialog.cancel(); a.sender.serial = None

    def test_system_views_and_retired_keyboard_controls(self):
        a = self.app
        import Utils
        dialog = a.workflow.settings('Advanced')
        panel = dialog.advanced
        panel.source.set('System defaults'); panel.show_system()
        self.assertIn(Utils.iniSystem, panel.system_text.get('1.0', 'end'))
        self.assertEqual(str(panel.system_text['state']), 'disabled')
        self.assertFalse(a.bind('<Right>'))
        self.assertFalse(a.bind('<Prior>'))
        self.assertFalse(hasattr(a, 'ribbon'))
        dialog.cancel()

    def test_advanced_controls_cannot_edit_during_cut(self):
        a = self.app
        a.sender.serial = Mock(); a.sender.running = True; CNC.vars['state'] = 'Run'
        dialog = a.workflow.settings('Advanced')
        self.assertIsNotNone(dialog)
        self.assertFalse(dialog.apply())
        with self.assertRaises(ValueError): dialog.advanced.home()
        with self.assertRaises(ValueError): dialog.advanced.reset()
        with patch.object(a.sender, 'stopRun') as stop:
            dialog.advanced.stop_motion()
            stop.assert_called_once_with()
        dialog.cancel(); a.sender.running = False; a.sender.serial = None

    def test_cleanup_registry_and_stale_tool_selection(self):
        a = self.app
        for name in ('Stock', 'Material', 'EndMill', 'Cut', 'Drill', 'Pocket', 'Profile', 'Tabs', 'Text'):
            self.assertNotIn(name.upper(), a.tools.tools)
        self.assertFalse(hasattr(a.gcode, 'probe'))
        self.assertFalse(hasattr(a.gcode, 'orient'))
        self.assertEqual(set(a.tools.tools), {'CNC', 'CONTROLLER'})

    def test_retired_files_leave_current_design_and_queue_untouched(self):
        a = self.app
        source = [list(b) for b in a.gcode.blocks]
        for extension in ('probe', 'orient', 'xyz', 'stl', 'ply'):
            with self.subTest(extension=extension), patch.object(a, 'fileModified') as modified, patch.object(a, 'reportPlotterError') as error:
                a.load('/tmp/retired.' + extension)
                modified.assert_not_called()
                error.assert_called_once()
                self.assertEqual([list(b) for b in a.gcode.blocks], source)
                self.assertTrue(a.sender.queue.empty())

    def test_mat_pin_and_position_telemetry_need_no_probe_map(self):
        a = self.app
        controller = a.sender.controllers['GRBL1']
        controller.parseBracketAngle('<Idle|MPos:0,0,0|WCO:0,0,0|Pn:P>', [])
        self.assertEqual(CNC.vars['pins'], 'P')
        controller.parseInformation('[PRB:1,2,3:1]')
        self.assertEqual([CNC.vars[key] for key in ('prbx', 'prby', 'prbz')], [1, 2, 3])
        controller.parseBracketAngle('<Idle|MPos:0,0,0|WCO:0,0,0>', [])
        self.assertEqual(CNC.vars['pins'], '')

    def test_retired_operation_cannot_start_machine(self):
        a = self.app
        self.ready_machine()
        a.gcode.blocks[-1].append('M6 T1')
        with patch.object(a, 'reportPlotterError') as error:
            a.plotter.start()
        error.assert_called_once()
        self.assertFalse(a.sender.running)
        self.assertTrue(a.sender.queue.empty())
        a.sender.serial = None

    def test_diagnostics_use_modern_text_and_trace_dialogs(self):
        from PlotterDesign import TextDialog
        from PlotterTrace import TraceDialog
        a = self.app
        try:
            for callback, expected in ((a.showTextInsertion, TextDialog), (a.showImageTrace, TraceDialog)):
                callback()
                dialog = a.workflow._design_dialog
                self.assertIsInstance(dialog, expected)
                dialog.destroy()
        finally:
            pass

    def test_steps_diagnostics_and_saving_with_single_pane(self):
        a = self.app
        for step in range(3):
            a.workflow.show_step(step)
            a.update()
            self.assertTrue(a.workflow.panels[step].winfo_ismapped())
        self.assertEqual(len(a.paned.panes()), 1)
        dialog = a.workflow.open_diagnostics()
        self.assertEqual(len(a.paned.panes()), 1)
        self.assertFalse(hasattr(a.workflow, "diagnostics"))
        self.assertIn('Machine', dialog.title())
        self.assertIs(dialog.machine, a.machine)
        dialog.destroy()
        a.saveConfig()
        self.assertEqual(len(a.paned.panes()), 1)

    def test_shape_preview_insertion_and_undo_preserve_artwork(self):
        a = self.app
        source = [list(b) for b in a.gcode.blocks]
        dialog = a.workflow.add_shape()
        dialog.kind.set('Star')
        dialog.rebuild()
        self.assertTrue(dialog.paths)
        self.assertTrue(dialog.insert())
        self.assertEqual(len(a.gcode.blocks), len(source)+1)
        self.assertEqual([list(b) for b in a.gcode.blocks[:-2]], source[:-1])
        a.undo()
        self.assertEqual([list(b) for b in a.gcode.blocks], source)

    def test_invalid_or_oversize_shape_does_not_change_artwork(self):
        a = self.app
        source = [list(b) for b in a.gcode.blocks]
        dialog = a.workflow.add_shape()
        for width in ('nan', '1000'):
            dialog.width.set(width)
            self.assertFalse(dialog.insert())
            self.assertEqual([list(b) for b in a.gcode.blocks], source)
        dialog.destroy()

    def test_text_font_search_preview_and_insert(self):
        a = self.app
        dialog = a.workflow.add_text()
        if not dialog.fonts:
            dialog.destroy()
            self.skipTest('No fonts installed')
        dialog.rebuild()
        self.assertTrue(dialog.paths, dialog.message.get())
        dialog.search.set('no-such-font-1234')
        dialog.rebuild()
        self.assertFalse(dialog.paths)
        self.assertFalse(dialog.insert())
        dialog.search.set('')
        dialog.text.delete('1.0', 'end')
        dialog.text.insert('1.0', 'Foil')
        self.assertTrue(dialog.insert())
        self.assertTrue(any(b.name() == 'Text: Foil' for b in a.gcode.blocks))

    def test_modern_trace_inserts_vectors_and_undo_restores_design(self):
        from PIL import Image, ImageDraw
        from imagetrace import trace_image
        a = self.app
        source = [list(b) for b in a.gcode.blocks]
        with tempfile.TemporaryDirectory() as folder:
            filename = os.path.join(folder, 'trace.png')
            bitmap = Image.new('RGB', (1600, 800), 'white')
            ImageDraw.Draw(bitmap).rectangle((160, 160, 1440, 640), fill='black')
            bitmap.save(filename)
            dialog = a.workflow.design_dialog('TraceDialog')
            with patch('imagetrace.trace_image', wraps=trace_image) as trace:
                dialog.load_image(filename)
                self.assertTrue(dialog.paths, dialog.message.get())
                self.assertEqual(trace.call_args.args[0].width, 760)
                self.assertTrue(dialog.insert())
                self.assertEqual(trace.call_args.args[0].width, 1600)
        self.assertEqual(len(a.gcode.blocks), len(source)+1)
        a.undo()
        self.assertEqual([list(b) for b in a.gcode.blocks], source)

    def test_trace_invalid_image_and_settings_cannot_insert_stale_preview(self):
        from PIL import Image, ImageDraw
        a = self.app
        source = [list(b) for b in a.gcode.blocks]
        with tempfile.TemporaryDirectory() as folder:
            filename = os.path.join(folder, 'trace.png')
            bitmap = Image.new('RGB', (100, 100), 'white')
            ImageDraw.Draw(bitmap).ellipse((10, 10, 90, 90), fill='black')
            bitmap.save(filename)
            dialog = a.workflow.design_dialog('TraceDialog')
            dialog.load_image(filename)
            dialog.settings['size'].set('nan')
            self.assertFalse(dialog.insert())
            dialog.settings['size'].set('50')
            dialog.load_image(os.path.join(folder, 'missing.png'))
            self.assertFalse(dialog.insert())
            self.assertEqual([list(b) for b in a.gcode.blocks], source)
            dialog.destroy()

    def test_arrange_resizes_and_places_selection(self):
        a = self.app
        a.workflow.select_all()
        dialog = a.workflow.arrange()
        dialog.width.set('20')
        before = [list(b) for b in a.gcode.blocks]
        dialog.rebuild()
        from PlotterEditing import bounds as preview_bounds
        bounds = preview_bounds(dialog.paths)
        self.assertAlmostEqual(bounds[2]-bounds[0], 20, places=5)
        dialog.x.set('25')
        dialog.y.set('35')
        dialog.rebuild()
        self.assertEqual(before, [list(b) for b in a.gcode.blocks])
        self.assertTrue(dialog.insert())
        self.assertAlmostEqual(design_bounds(a.gcode.blocks)[0], 25)
        self.assertAlmostEqual(design_bounds(a.gcode.blocks)[1], 35)

    def test_combine_and_break_apart_are_single_undo_operations(self):
        a = self.app
        self.add_square_fixture()
        a.editor.select([(1, None), (2, None)], clear=True)
        source = [list(b) for b in a.gcode.blocks]
        dialog = a.workflow.design_dialog('CombineDialog')
        dialog.operation.set('Combine outlines')
        self.assertTrue(dialog.insert())
        self.assertEqual(len(a.gcode.blocks), len(source)-1)
        a.workflow.break_apart()
        self.assertEqual(len(a.gcode.blocks), len(source))
        a.undo()
        self.assertEqual(len(a.gcode.blocks), len(source)-1)
        a.undo()
        self.assertEqual([list(b) for b in a.gcode.blocks], source)

    def test_empty_boolean_result_is_explicit_and_undoable(self):
        a = self.app
        self.add_square_fixture()
        a.editor.select([(1, None), (2, None)], clear=True)
        source = [list(b) for b in a.gcode.blocks]
        dialog = a.workflow.design_dialog('CombineDialog')
        dialog.operation.set('Subtract')
        dialog.rebuild()
        self.assertIn('Empty result', dialog.message.get())
        self.assertTrue(dialog.insert())
        self.assertEqual(len(a.gcode.blocks), 2)
        a.undo()
        self.assertEqual([list(b) for b in a.gcode.blocks], source)

    def test_pressure_adjustment_is_staged_and_bounded(self):
        original = CNC.vars['mat_pressure']
        dialog = self.app.workflow.settings('Material')
        dialog.values['mat_pressure'].set('990')
        dialog.adjust_pressure(25)
        self.assertEqual(dialog.values['mat_pressure'].get(), '1000')
        dialog.values['mat_pressure'].set('10')
        dialog.adjust_pressure(-25)
        self.assertEqual(dialog.values['mat_pressure'].get(), '0')
        dialog.values['mat_pressure'].set('nan')
        dialog.adjust_pressure(25)
        self.assertTrue(dialog.error.get())
        self.assertEqual(CNC.vars['mat_pressure'], original)
        dialog.cancel()

    def test_library_editor_and_pen_layer_assignment(self):
        from PlotterLibrary import ProfileLibrary
        from PlotterLayers import catalog
        from PlotterLayersUI import LayersDialog
        w = self.app.workflow
        original = w.library
        w.library = ProfileLibrary(); w.refresh_library()
        dialog = w.open_library()
        try:
            dialog.forms['materials']['name'].set('Test paper')
            dialog.forms['materials']['pressure'].set('125')
            dialog.save('materials')
            dialog.forms['materials']['name'].set('Drawing paper')
            dialog.save('materials')
            self.assertNotIn('Test paper',w.library.records['materials'])
            dialog.duplicate('materials')
            with patch('PlotterLibraryUI.messagebox.askyesno',return_value=True): dialog.delete('materials')
            self.assertEqual(list(w.library.records['materials']),['Drawing paper'])
            dialog.forms['tools']['name'].set('Fine pen')
            dialog.forms['tools']['kind'].set('Pen')
            dialog.tool_changed()
            self.assertEqual(str(dialog.widgets['tools']['compensate'].cget('state')),'disabled')
            dialog.save('tools')
            self.assertFalse(w.library.records['tools']['Fine pen']['compensate'])
            dialog.destroy()
            layer = LayersDialog(w)
            try:
                layer.tree.selection_set('layer:0'); layer.selected()
                layer.operation.set('Draw'); layer.process_choices()
                layer.tool_profile.set('Fine pen'); layer.material_profile.set('Drawing paper')
                self.assertTrue(layer.apply_process())
                saved = catalog(self.app.gcode)[0]['process']
                self.assertEqual(saved['operation'],'Draw')
                self.assertEqual(saved['material']['pressure'],125)
                self.assertFalse(saved['tool']['compensate'])
                self.app.update()
                self.assertIn('Pen · Fine pen',w.pass_choice.cget('values'))
            finally: layer.destroy()
            with patch('PlotterProcesses.compensate_path', side_effect=AssertionError('Pen compensated')):
                self.app.plotter.prepare()
        finally:
            if dialog.winfo_exists(): dialog.destroy()
            w.library=original; w.save_library()
            w.tool_pass.set('All included layers')

    def test_blade_presets_apply_and_cancel_independently_of_pressure(self):
        workflow = self.app.workflow
        original = dict(workflow.blade_profiles)
        for apply in (False, True):
            dialog = workflow.settings('Blade')
            pressure = dialog.values['mat_pressure'].get()
            dialog.values['mat_knife_offset'].set('0.35')
            dialog.values['mat_overcut'].set('0.6')
            dialog.compensation.set(True)
            with patch('PlotterSettings.simpledialog.askstring', return_value='Test holder'):
                dialog.save_blade()
            self.assertEqual(workflow.blade_profiles, original)
            dialog.values['mat_knife_offset'].set('0')
            dialog.choose_blade()
            self.assertEqual(dialog.values['mat_knife_offset'].get(), '0.35')
            self.assertEqual(dialog.values['mat_pressure'].get(), pressure)
            if apply:
                self.assertTrue(dialog.apply())
                self.assertEqual(workflow.blade_profiles['Test holder']['mat_overcut'], 0.6)
            else:
                dialog.cancel()
                self.assertEqual(workflow.blade_profiles, original)
        workflow.blade_profiles = original
        CNC.vars['mat_overcut'] = 0

    def test_calibration_is_separate_and_cancel_preserves_artwork(self):
        a = self.app
        source = [list(b) for b in a.gcode.blocks]
        with patch.object(a, 'fileModified', return_value=True):
            self.assertFalse(a.workflow.new_calibration())
        self.assertEqual([list(b) for b in a.gcode.blocks], source)
        with patch.object(a, 'fileModified', return_value=False):
            self.assertTrue(a.workflow.new_calibration())
        shapes = a.gcode.blocks[1:-1]
        self.assertEqual(len(shapes), 3)
        for index in range(1, 4):
            self.assertTrue(a.gcode.toPath(index)[0].isClosed())
        self.assertTrue(bounds_fit(planned_cut_bounds(a.gcode.blocks), 300, 300))
        from PlotterAdapters import DocumentJobPort
        self.assertTrue(DocumentJobPort(a).compensate(DocumentJobPort(a).parameters()))
        self.assertTrue(a.sender.queue.empty())

    def test_settings_cancel_and_invalid_apply_preserve_live_values(self):
        a = self.app
        self.ready_machine()
        original = {key: CNC.vars.get(key) for key in SETTING_FIELDS}
        dlg = a.workflow.settings()
        a.update_idletasks()
        for page in ('Blade', 'Mat', 'Material'):
            dlg.show_page(page)
            a.update_idletasks()
            self.assertTrue(dlg.pages[page].winfo_ismapped())
        dlg.values['mat_speed'].set('700')
        dlg.values['mat_width'].set('bad')
        self.assertFalse(dlg.apply())
        self.assertIn('Mat width', dlg.error.get())
        self.assertEqual({key: CNC.vars.get(key) for key in SETTING_FIELDS}, original)
        dlg.cancel()
        self.assertEqual({key: CNC.vars.get(key) for key in SETTING_FIELDS}, original)
        self.assertTrue(a.workflow.confirmed.get())
        a.sender.serial = None

    def test_advanced_header_footer_edit_is_undoable_and_sends_nothing(self):
        a = self.app
        source = [list(b) for b in a.gcode.blocks]
        dialog = a.workflow.settings('Advanced')
        for name, text in [('Header', 'G90\nG21\nM3 S123'), ('Footer', 'M5\nG4 P0.25')]:
            dialog.gcode_editors[name].delete('1.0', 'end')
            dialog.gcode_editors[name].insert('1.0', text)
        with patch.object(a.sender, 'sendGCode') as send:
            self.assertTrue(dialog.apply())
            send.assert_not_called()
        self.assertEqual(list(a.gcode.blocks[0]), ['G90', 'G21', 'M3 S123'])
        self.assertEqual(list(a.gcode.blocks[-1]), ['M5', 'G4 P0.25'])
        self.assertEqual([list(b) for b in a.gcode.blocks[1:-1]], source[1:-1])
        self.assertTrue(a.sender.queue.empty())
        a.undo()
        self.assertEqual([list(b) for b in a.gcode.blocks], source)

    def test_advanced_defaults_survive_config_roundtrip(self):
        import Utils
        a = self.app
        old = (a.gcode.header, a.gcode.footer)
        try:
            dialog = a.workflow.settings('Advanced')
            for name, text in [('Header', 'G90\nG21'), ('Footer', 'M5')]:
                dialog.gcode_editors[name].delete('1.0', 'end')
                dialog.gcode_editors[name].insert('1.0', text)
            dialog.save_code_defaults.set(True)
            self.assertTrue(dialog.apply())
            self.assertEqual(Utils.getStr('CNC', 'header'), 'G90\nG21')
            import io
            import configparser
            stream = io.StringIO()
            Utils.config.write(stream)
            restored = configparser.ConfigParser(interpolation=None)
            restored.read_string(stream.getvalue())
            self.assertEqual(restored.get('CNC', 'header'), 'G90\nG21')
            a.gcode.init()
            a.gcode.headerFooter()
            self.assertEqual(list(a.gcode.blocks[0]), ['G90', 'G21'])
            self.assertEqual(list(a.gcode.blocks[-1]), ['M5'])
        finally:
            a.gcode.header, a.gcode.footer = old
            a.tools['CNC']['header'], a.tools['CNC']['footer'] = old
            a.tools['CNC'].save()

    def test_advanced_cancel_and_enter_do_not_apply_draft(self):
        a = self.app
        source = [list(b) for b in a.gcode.blocks]
        dialog = a.workflow.settings('Advanced')
        editor = dialog.gcode_editors['Header']
        editor.focus_force()
        editor.mark_set('insert', 'end-1c')
        a.update()
        editor.event_generate('<Return>')
        a.update()
        self.assertTrue(dialog.winfo_exists())
        self.assertTrue(editor.get('1.0', 'end-1c').endswith('\n'))
        dialog.cancel()
        self.assertEqual([list(b) for b in a.gcode.blocks], source)

    def test_footer_precedes_wait_with_and_without_compensation(self):
        from CNC import WAIT
        a = self.app
        for compensate in (False, True):
            with self.subTest(compensate=compensate):
                self.ready_machine()
                CNC.vars['mat_auto_dragknife'] = compensate
                a.gcode.blocks[-1][:] = ['M5', 'G4 P0.789']
                source = [list(b) for b in a.gcode.blocks]
                with patch('Sender.time.sleep'):
                    a.run()
                queued = list(a.sender.queue.queue)
                self.assertEqual(queued[-1], (WAIT,))
                self.assertTrue(any(isinstance(line, str) and '0.789' in line for line in queued[:-1]))
                self.assertEqual([list(b) for b in a.gcode.blocks], source)
                a.sender.running = False; a.sender.serial = None; a.sender.emptyQueue()
                CNC.vars['running'] = False

    def test_edited_header_footer_reach_the_cut_buffer(self):
        a = self.app
        dialog = a.workflow.settings('Advanced')
        for name, text in [('Header', 'G90\nG21\nG4 P0.123'), ('Footer', 'M5\nG4 P0.456')]:
            dialog.gcode_editors[name].delete('1.0', 'end')
            dialog.gcode_editors[name].insert('1.0', text)
        self.assertTrue(dialog.apply())
        self.ready_machine()
        with patch('Sender.time.sleep'):
            a.run()
        queued = [line.lower().replace(' ', '') for line in a.sender.queue.queue if isinstance(line, str)]
        first = next(i for i, line in enumerate(queued) if 'p0.123' in line)
        last = next(i for i, line in enumerate(queued) if 'p0.456' in line)
        self.assertLess(first, last)
        self.assertTrue(any('g1' in line for line in queued[first:last]))
        a.sender.serial = None
        a.sender.firmware = None
        CNC.vars["mpg"] = False
        a.sender.running = False
        a.sender.emptyQueue()
        a.enable()

    def test_retired_mesh_import_does_not_change_the_design(self):
        a = self.app
        source = [list(b) for b in a.gcode.blocks]
        with patch.object(a, 'fileModified') as modified:
            a.load('/tmp/unsupported.STL')
        modified.assert_not_called()
        self.assertEqual([list(b) for b in a.gcode.blocks], source)
        self.assertEqual(sorted(a.sender.controllers), ['GRBL0', 'GRBL1'])

    def test_settings_cannot_apply_during_a_cut(self):
        a = self.app
        original = CNC.vars['mat_speed']
        dlg = a.workflow.settings()
        dlg.values['mat_speed'].set('123')
        a.sender.running = True
        self.assertFalse(dlg.apply())
        self.assertEqual(CNC.vars['mat_speed'], original)
        a.sender.running = False
        dlg.cancel()

    def test_settings_apply_changes_configuration_without_modifying_artwork(self):
        a = self.app
        original = [list(b) for b in a.gcode.blocks]
        self.ready_machine()
        dlg = a.workflow.settings()
        dlg.values['mat_width'].set('310')
        dlg.values['mat_overcut'].set('0.8')
        dlg.compensation.set(True)
        self.assertTrue(dlg.apply())
        self.assertEqual(CNC.vars['mat_overcut'], 0.8)
        self.assertEqual(CNC.vars['mat_width'], 310)
        self.assertFalse(a.workflow.confirmed.get())
        self.assertEqual([list(b) for b in a.gcode.blocks], original)
        CNC.vars['mat_width'] = 300
        CNC.vars['mat_overcut'] = 0
        a.sender.serial = None

    def test_import_then_immediate_center_and_fit_mat(self):
        a = self.app
        CNC.vars.update(mat_width=300, mat_height=300)
        path = os.path.join(ROOT, '..', 'docs', 'examples', 'leaf-decals.svg')
        a.gcode._modified = False
        a.load(path)
        a.workflow.select_all()
        a.workflow.center()
        a.draw()
        a.workflow.update_state()
        bounds = design_bounds(a.gcode.blocks)
        self.assertAlmostEqual((bounds[0]+bounds[2])/2, 150, places=2)
        self.assertAlmostEqual((bounds[1]+bounds[3])/2, 150, places=2)
        a.workflow.fit_mat()
        a.update_idletasks()
        box = a.canvas.bbox('CuttingMat')
        self.assertLessEqual(box[2]-box[0], a.canvas.winfo_width())
        self.assertLessEqual(box[3]-box[1], a.canvas.winfo_height())

    def test_mirror_and_duplicate_keep_header_footer_unchanged(self):
        a = self.app
        header = list(a.gcode.blocks[0])
        footer = list(a.gcode.blocks[-1])
        a.editor.select([(1, None)], clear=True)
        dialog = a.workflow.design_dialog("ArrangeDialog")
        dialog.horizontal.set(True)
        self.assertTrue(dialog.insert())
        a.draw()
        self.assertEqual(design_bounds(a.gcode.blocks), (5, 5, 15, 15))
        a.workflow.duplicate()
        a.draw()
        self.assertEqual(design_bounds(a.gcode.blocks), (5, 5, 25, 25))
        self.assertEqual(list(a.gcode.blocks[0]), header)
        self.assertEqual(list(a.gcode.blocks[-1]), footer)

    def test_keyboard_start_is_blocked_without_ready_machine(self):
        with patch.object(self.app, "reportPlotterError") as info:
            self.app.run()
        info.assert_called_once()
        self.assertFalse(self.app.sender.running)
        self.assertTrue(self.app.sender.queue.empty())

    def test_boot_hold_explains_recovery_without_automatic_reset(self):
        a = self.app
        a.sender.serial = Mock()
        CNC.vars['state'] = 'Hold:0'
        with patch.object(a.sender, 'softReset') as reset, patch.object(a.sender, 'resume') as resume:
            reason = a.workflow.start_reason()
            self.assertIn('Advanced settings', reason)
            self.assertIn('discard the queued job', reason)
            reset.assert_not_called()
            resume.assert_not_called()

    def ready_machine(self):
        a = self.app
        a.sender.serial = Mock()
        CNC.vars['state'] = 'Idle'
        a.workflow.update_state()
        a.workflow.confirmed.set(True)

    def test_valid_cut_compiles_material_settings_without_modifying_artwork(self):
        a = self.app
        self.ready_machine()
        original = [list(b) for b in a.gcode.blocks]
        CNC.vars['mat_speed'] = 420
        CNC.vars['mat_pressure'] = 350
        with patch('Sender.time.sleep'):
            a.run()
        self.assertTrue(a.sender.running)
        queued = list(a.sender.queue.queue)
        self.assertTrue(any(isinstance(line, str) and 'f420' in line.lower() for line in queued))
        self.assertTrue(any(isinstance(line, str) and 's350' in line.lower() for line in queued))
        self.assertEqual([list(b) for b in a.gcode.blocks], original)
        a.sender.serial = None
        a.sender.firmware = None
        CNC.vars["mpg"] = False
        a.sender.running = False
        a.sender.emptyQueue()
        a.enable()

    def test_overhanging_compensation_is_rejected_before_starting_sender(self):
        a = self.app
        self.ready_machine()
        CNC.vars['mat_auto_dragknife'] = True
        from bpath import Path, Segment
        from bmath import Vector
        outside = Path('Outside')
        outside.append(Segment(Segment.LINE, Vector(0, 5), Vector(301, 5)))
        with patch('PlotterProcesses.compensate_path', return_value=outside), \
                patch.object(a, 'reportPlotterError') as error:
            a.run()
        error.assert_called_once()
        self.assertFalse(a.sender.running)
        self.assertTrue(a.sender.queue.empty())
        a.sender.serial = None

    def test_hidden_views_removed_and_selection_clipboard_undo_preserved(self):
        from pathlib import Path
        from PlotterSelection import DocumentEditor
        from PlotterSession import DiagnosticLog
        a = self.app
        self.assertIsInstance(a.editor, DocumentEditor)
        for name in ('ribbon','legacyPane','legacyStatus','matPanel','dro','gstate','control','terminal','buffer'):
            self.assertFalse(hasattr(a, name), name)
        self.assertFalse(hasattr(a.canvasFrame, 'toolbar'))
        for name in ('CNCList','CNCRibbon','Ribbon','ToolsPage','FilePage','EditorPage','ControlPage','TerminalPage'):
            self.assertFalse((Path(ROOT)/(name+'.py')).exists())
        a.gcode.blocks[1].foil.update(layer='Blue', group='original')
        a.gcode.blocks[1].passes = 3
        a.editor.selectBlocks([1]); a.editor.copy(); a.editor.paste()
        self.assertEqual(len(a.gcode.blocks), 4)
        self.assertEqual(a.gcode.blocks[2].passes, 3)
        self.assertEqual(a.gcode.blocks[2].foil['layer'], 'Blue')
        self.assertNotEqual(a.gcode.blocks[2].foil['group'], 'original')
        a.undo(); self.assertEqual(len(a.gcode.blocks),3)
        a.redo(); self.assertEqual(len(a.gcode.blocks),4)
        a.diagnostic_log.record(2, 'Firmware connected')
        self.assertIn('Firmware connected', a.configuration.describe('Connection log'))
        history = DiagnosticLog(2)
        for i in range(3): history.record(2,str(i))
        self.assertEqual(history.text(), '1\n2')

    def test_autoconnect_toggle_persists_without_opening_connection(self):
        import Utils
        import configparser
        a = self.app
        original = a.connection.autoconnect()
        dialog = None
        try:
            a.connection.set_autoconnect(False)
            dialog = a.workflow.connection_settings()
            self.assertFalse(dialog.autoconnect.get())
            with patch.object(a, 'open') as connect, patch.object(a.sender, 'sendGCode') as send:
                dialog.autoconnect_check.invoke()
                self.assertTrue(a.connection.autoconnect())
                self.assertTrue(Utils.getBool('Connection', 'openserial'))
                a.update()
                self.assertLessEqual(dialog.winfo_height(), 740)
                dialog.destroy()
                dialog = a.workflow.connection_settings()
                self.assertTrue(dialog.autoconnect.get())
                # The legacy shutdown writer must retain the modern setting.
                a.connection_preferences.save()
                path = os.path.join(self.temp.name, 'startup-preference.ini')
                with open(path, 'w') as stream:
                    Utils.config.write(stream)
                saved = configparser.ConfigParser(); saved.read(path)
                self.assertTrue(saved.getboolean('Connection', 'openserial'))
                dialog.autoconnect_check.invoke()
                a.connection_preferences.save()
                self.assertFalse(Utils.getBool('Connection', 'openserial'))
                connect.assert_not_called(); send.assert_not_called()
        finally:
            if dialog is not None and dialog.winfo_exists(): dialog.destroy()
            a.connection.set_autoconnect(original)

    def test_tcp_selector_preserves_address_and_disables_baud(self):
        a = self.app
        dialog = a.workflow.connection_settings()
        from PlotterUI import descendants
        self.assertIn('Refresh serial ports', [w.cget('text') for w in descendants(dialog) if w.winfo_class() == 'Button'])
        dialog.port.set('socket://plotter.local:8888')
        self.assertEqual(str(dialog.baud_combo['state']), 'disabled')
        self.assertIn('TCP', dialog.transport_hint.get())
        with patch('serial.tools.list_ports.comports', return_value=[]):
            dialog.refresh()
        self.assertEqual(dialog.port.get(), 'socket://plotter.local:8888')
        self.assertIn(dialog.port.get(), dialog.ports['values'])
        dialog.port.set('/dev/ttyUSB0')
        self.assertEqual(str(dialog.baud_combo['state']), 'normal')
        dialog.port.set('socket://192.168.1.50:8888')
        dialog.baud.set('115200')
        with patch.object(a, 'open', return_value=True) as connect:
            self.assertTrue(dialog.connect())
            connect.assert_called_once_with('socket://192.168.1.50:8888', 115200)
        reopened = a.workflow.connection_settings()
        self.assertEqual(reopened.port.get(), 'socket://192.168.1.50:8888')
        self.assertEqual(str(reopened.baud_combo['state']), 'disabled')
        reopened.destroy()

    def test_connection_validation_and_success_use_existing_sender(self):
        a = self.app
        dialog = a.workflow.connection_settings()
        dialog.port.set('')
        with patch.object(a, 'open') as connect:
            self.assertFalse(dialog.connect())
            connect.assert_not_called()
        dialog.port.set('/dev/test-plotter')
        dialog.baud.set('115200')
        with patch.object(a, 'open', return_value=True) as connect:
            self.assertTrue(dialog.connect())
            connect.assert_called_once_with('/dev/test-plotter', 115200)
        self.assertFalse(hasattr(a.workflow, "diagnostics"))

    def test_connection_failure_is_inline_and_closes_partial_port(self):
        a = self.app
        port = Mock()
        def failure(*args):
            a.sender.serial = port
            raise OSError('Port is busy')
        with patch('bmain.Sender.open', side_effect=failure), patch('bmain.messagebox.showerror') as popup:
            self.assertFalse(a.open('/dev/test', 115200))
            popup.assert_not_called()
        port.close.assert_called_once()
        self.assertIsNone(a.sender.serial)
        self.assertIn('Port is busy', a.workflow.technical_error.get())
        self.assertNotIn('Port is busy', a.workflow.notice_text.get())

    def test_error_details_are_hidden_until_requested(self):
        workflow = self.app.workflow
        workflow.report_error('Could not connect', '[Errno 2] No such file: /dev/ttyUSB0')
        self.assertFalse(workflow.error_details.winfo_manager())
        self.assertNotIn('/dev/', workflow.notice_text.get())
        self.assertEqual(workflow.notice_action.cget('text'), 'Choose plotter')
        workflow.toggle_error_details()
        self.assertTrue(workflow.error_details.winfo_manager())
        self.assertIn('/dev/ttyUSB0', workflow.technical_error.get())
        workflow.report_error('Could not connect', 'Permission denied')
        self.assertFalse(workflow.error_details.winfo_manager())
        workflow.clear_notice()

    def test_internal_callback_errors_use_unified_presenter(self):
        import Utils
        a = self.app
        def broken():
            raise RuntimeError('private diagnostic detail')
        import tkinter
        wrapper = tkinter.CallWrapper(broken, None, a)
        wrapper()
        self.assertIn('couldn’t finish', a.workflow.notice_title.get())
        self.assertNotIn('private diagnostic', a.workflow.notice_text.get())
        self.assertIn('RuntimeError', a.workflow.technical_error.get())

    def test_serial_monitor_failure_reaches_unified_presenter(self):
        a = self.app
        with patch.object(a, '_monitorSerial', side_effect=RuntimeError('monitor failure')), \
                patch.object(a, 'after') as schedule:
            a.monitorSerial()
        self.assertIn('monitor failure', a.workflow.technical_error.get())
        schedule.assert_called_once()

    def test_modal_internal_error_keeps_parent_draft(self):
        a = self.app
        dialog = a.workflow.add_shape()
        dialog.width.set('73')
        a.reportPlotterError('Internal application error', 'RuntimeError: unexpected')
        error = a._error_dialog
        self.assertTrue(error.winfo_exists())
        self.assertEqual(dialog.width.get(), '73')
        error.destroy()
        dialog.destroy()

    def test_internal_cut_error_requests_hold_without_claiming_completion(self):
        a = self.app
        a.sender.running = True
        a.sender.queue.put('G1 X10')
        with patch.object(a.sender, 'feedHold') as hold:
            a.report_callback_exception(RuntimeError, RuntimeError('unexpected'), None)
        hold.assert_called_once()
        self.assertTrue(a.sender.queue.empty())
        self.assertTrue(a.sender._stop)
        a.sender.running = False
        a.sender._stop = False

    def test_internal_preview_error_keeps_draft_and_hides_exception(self):
        a = self.app
        dialog = a.workflow.add_shape()
        with patch.object(dialog, 'make_paths', side_effect=RuntimeError('private trace detail')):
            dialog.rebuild()
        self.assertNotIn('private trace detail', dialog.message.get())
        self.assertIn('private trace detail', dialog.preview_error_detail)
        self.assertEqual(dialog.width.get(), '40')
        dialog.destroy()

    def test_alarm_recovery_is_explicit_and_invalidates_mat(self):
        a = self.app
        self.ready_machine()
        CNC.vars['state'] = 'Alarm:8'
        with patch.object(a.sender, 'unlock') as unlock:
            a.workflow.update_state()
            unlock.assert_not_called()
            self.assertIn('switch', a.workflow.notice_title.get())
            self.assertFalse(a.workflow.confirmed.get())
            a.workflow.unlock_plotter()
            unlock.assert_called_once()
            a.sender.running = True
            a.workflow.unlock_plotter()
            unlock.assert_called_once()
        a.sender.running = False
        a.sender.serial = None

    def test_transport_failure_drains_queue_and_reports_without_tk(self):
        from Sender import Sender
        a = self.app
        a.sender.serial = port = Mock()
        a.sender.thread = object()
        a.sender.running = True
        a.sender.queue.put('G1 X10')
        with patch.object(a.sender, '_serialIOLoop', side_effect=OSError('USB removed')), \
                patch.object(a, 'close') as ui_close:
            a.sender.serialIO()
            ui_close.assert_not_called()
        port.close.assert_called_once()
        self.assertFalse(a.sender.running)
        self.assertIsNone(a.sender.serial)
        self.assertTrue(a.sender.queue.empty())
        self.assertTrue(CNC.vars['mat_confirmation_invalid'])
        self.assertTrue(any('USB removed' in str(item) for item in a.sender.log.queue))

    def test_guided_pen_and_knife_sequence_requires_each_tool_confirmation(self):
        import Utils
        from PlotterLayers import LayerManager
        from PlotterProtocol import Firmware
        from test_plotter_library import process
        a, w = self.app, self.app.workflow
        a.sender.serial=Mock()
        a.sender.firmware=Firmware(board='GRBLFilmCut',family='grblHAL',identified=True)
        a.sender.firmware.units_known=True; a.sender.firmware.last_wpos=(0,0,0)
        a.sender._sumcline=0; a.sender._status_sequence=0
        CNC.vars.update(state='Idle',pins='YZP',mx=-215,my=0,mz=0,wx=0,wy=0,wz=0)
        Utils.setStr('Plotter','load_mode','auto')
        manager=LayerManager(a.gcode)
        manager.set_process('Default',process('Pen','Black'))
        manager.add('Knife')
        a.gcode.insBlocks(2,[deepcopy(a.gcode.blocks[1])],'Second pass')
        a.gcode.blocks[2].foil['layer']='Knife'
        manager.set_process('Knife',process('Knife','Swivel'))
        a.refresh(); w.tool_pass.set('All included layers'); w.show_step(2); w.confirmed.set(True)
        w.update_state()
        self.assertFalse(w.start_reason())
        def finish_homing():
            for index in range(3):
                a.sender.emptyQueue()
                a.tool_sequence.receive('ok')
                a.sender._status_sequence+=1
                a.tool_sequence.tick()
            w.update_state()
        try:
            with patch('Sender.time.sleep'):
                a.run()
                self.assertTrue(a.tool_sequence.active)
                self.assertFalse(a.sender.running)
                self.assertEqual(str(w.cut_mat_button.cget('state')),'disabled')
                for tool in ('Pen · Black','Knife · Swivel'):
                    finish_homing()
                    self.assertEqual(a.tool_sequence.phase,'waiting')
                    self.assertIn(tool,w.sequence_message.cget('text'))
                    self.assertEqual(str(w.tool_continue.cget('state')),'disabled')
                    w.continue_tool(); self.assertFalse(a.sender.running)
                    w.tool_check.invoke()
                    self.assertEqual(str(w.tool_continue.cget('state')),'normal')
                    w.tool_continue.invoke()
                    self.assertTrue(a.sender.running)
                    self.assertEqual(a.tool_sequence.phase,'running')
                    a.sender.emptyQueue(); a.sender._gcount=a.sender._runLines
                    a._monitorSerial(); w.update_state()
                    self.assertFalse(a.sender.running)
                self.assertFalse(a.tool_sequence.active)
                self.assertEqual(a.tool_sequence.phase,'complete')
                self.assertFalse(w.confirmed.get())
        finally:
            a.tool_sequence.active=False; a.tool_sequence.phase='idle'
            a.sender.emptyQueue(); a.sender.running=False
            a.sender.serial=None; a.sender.firmware=None

    def test_cut_completion_then_unload_never_resets_controller(self):
        import Utils
        from PlotterProtocol import Firmware
        a, w = self.app, self.app.workflow
        Utils.setStr('Plotter','load_mode','auto')
        a.sender.serial = Mock()
        a.sender.firmware = Firmware(board='GRBLFilmCut',family='grblHAL',identified=True)
        a.sender.firmware.units_known=True
        a.sender.firmware.last_wpos=(0,0,0)
        a.sender._sumcline=0
        a.sender.sio_wait=False
        CNC.vars.update(state='Idle',pins='YZP')
        w.update_state(); w.confirmed.set(True)
        def status(state):
            a.sender.mcontrol.parseStatus(f'<{state}|MPos:0,0,0|WCO:0,0,0|Pn:YZP>', [])
        try:
            with patch.object(a.sender.firmware,'queries_due',return_value=[]), \
                    patch.object(a.sender,'purgeController') as purge, \
                    patch('Sender.time.sleep'):
                # Use the real job entry point and normal completion monitor.
                a.run()
                self.assertTrue(a.sender.running)
                status('Run'); a.sender.emptyQueue()
                a.sender._gcount=a.sender._runLines
                status('Idle'); a._monitorSerial()
                self.assertFalse(a.sender.running)
                self.assertTrue(a.machine.snapshot().ready)
                with patch.object(a.sender,'sendGCode') as send:
                    a.unloadMat()
                    self.assertTrue(a.mat_handling.active)
                    a.mat_handling.receive('ok'); status('Idle'); a.mat_handling.tick()
                    self.assertEqual(a.mat_handling.command,'$HX')
                    status('Home')
                    a.mat_handling.receive('ok'); status('Idle'); a.mat_handling.tick()
                    self.assertEqual(a.mat_handling.command,'$UNLOAD_MATERIAL')
                    a.mat_handling.receive('[MSG:UNLOAD_MATERIAL: done. material ejected]')
                    a.mat_handling.receive('ok'); status('Idle'); a.mat_handling.tick()
                    a.mat_handling.receive('ok'); status('Idle'); a.mat_handling.tick()
                    self.assertFalse(a.mat_handling.active)
                    self.assertFalse(a.mat_handling.positioned)
                    purge.assert_not_called()
                    self.assertEqual([call.args[0] for call in send.call_args_list],
                                     ['M5','$HX','$UNLOAD_MATERIAL','G92.1'])
                purge.assert_not_called()
                a.sender.serial.write.assert_not_called()
        finally:
            a.mat_handling.active=False
            a.sender.emptyQueue(); a.sender.running=False
            a.sender.serial=None; a.sender.firmware=None

    def test_final_step_load_unload_reload_and_confirmation(self):
        import Utils
        from PlotterProtocol import Firmware
        a, w = self.app, self.app.workflow
        Utils.setStr('Plotter', 'load_mode', 'auto')
        a.sender.serial = object()
        a.sender.firmware = Firmware(board='GRBLFilmCut', family='grblHAL', identified=True)
        a.sender.firmware.units_known = True
        a.sender.firmware.last_wpos = (0,0,0)
        a.sender._sumcline = 0
        a.sender._status_sequence = 0
        CNC.vars.update(state='Idle', pins='YZ')
        w.show_step(2)
        self.assertEqual(w.cut_mat_button.cget('text'),'Load mat')
        self.assertEqual(str(w.cut_confirm_check.cget('state')),'disabled')
        self.assertEqual(str(w.next_button.cget('state')),'disabled')
        with patch.object(a.sender, 'sendGCode') as send:
            w.cut_mat_action()
            send.assert_not_called()
            for loading in (True,False,True):
                CNC.vars['pins']='YZP'
                w.update_state()
                self.assertEqual(w.cut_mat_button.cget('text'),'Load mat' if loading else 'Unload mat')
                w.cut_mat_action()
                self.assertTrue(a.mat_handling.active)
                self.assertFalse(w.confirmed.get())
                self.assertEqual(str(w.cut_mat_button.cget('state')),'disabled')
                self.assertEqual(str(w.next_button.cget('state')),'disabled')
                for step in range(4):
                    command=a.mat_handling.command
                    if 'MATERIAL' in command:
                        a.mat_handling.receive('[MSG:' + ('LOAD' if loading else 'UNLOAD') + '_MATERIAL: done. material moved]')
                        if not loading: CNC.vars['pins']='YZ'
                    a.mat_handling.receive('ok')
                    a.sender._status_sequence += 1
                    a.mat_handling.tick()
                    w.update_state()
                self.assertFalse(a.mat_handling.active)
                self.assertEqual(w.cut_mat_button.cget('text'),'Unload mat' if loading else 'Load mat')
                self.assertEqual(str(w.next_button.cget('state')),'disabled')
                if loading:
                    w.cut_confirm_check.invoke(); w.update_state()
                    self.assertTrue(w.confirmed.get())
                    self.assertEqual(str(w.next_button.cget('state')),'normal')
            CNC.vars['pins']='YZ'
            w.update_state()
            self.assertFalse(w.confirmed.get())
            self.assertFalse(a.mat_handling.positioned)
            self.assertEqual(w.cut_mat_button.cget('text'),'Load mat')
            self.assertEqual(str(w.next_button.cget('state')),'disabled')
        a.sender.serial=None; a.sender.firmware=None

    def test_settings_library_access_preserves_drafts_and_refreshes_presets(self):
        from PlotterLibrary import ProfileLibrary
        w = self.app.workflow
        original = w.library
        w.library = ProfileLibrary(); w.refresh_library()
        w.library.save('tools', {'name':'Old holder'})
        w.save_library()
        dialog = w.settings('Material')
        dialog.values['mat_pressure'].set('321')
        def edit_library(child):
            child.library.delete('tools','Old holder')
            child.library.save('tools',{'name':'New holder','offset':.3})
            child.workflow.save_library()
            child.destroy()
        try:
            with patch.object(dialog,'wait_window',side_effect=edit_library):
                dialog.library_button.invoke()
            self.assertEqual(dialog.values['mat_pressure'].get(),'321')
            self.assertNotIn('Old holder',dialog.blade_profiles)
            self.assertIn('New holder',dialog.blade_profiles)
            self.assertIs(self.app.workspace_pages[-1], dialog)
            self.assertIsNone(dialog.grab_current())
        finally:
            dialog.cancel()
            w.library=original; w.save_library()

    def test_load_does_not_claim_success_and_cannot_run_disconnected(self):
        a = self.app
        with patch.object(a.sender, "sendGCode") as send:
            a.loadMat()
        send.assert_not_called()
        self.assertFalse(CNC.vars["mat_loaded"])

    def test_manual_loading_does_not_send_custom_firmware_commands(self):
        import Utils
        a = self.app
        a.sender.serial = object()
        CNC.vars["state"] = "Idle"
        Utils.addSection("Plotter")
        Utils.setStr("Plotter", "load_mode", "manual")
        with patch.object(a.sender, "sendGCode") as send:
            a.loadMat()
        send.assert_called_once_with("G92 X0 Y0")
        self.assertFalse(CNC.vars["mat_loaded"])
        a.sender.serial = None

    def test_detected_loader_and_mat_controls(self):
        import Utils
        from PlotterProtocol import Firmware
        a = self.app
        Utils.setStr("Plotter", "load_mode", "auto")
        self.assertFalse(a.automaticMatLoading())
        a.sender.firmware = Firmware()
        a.sender.firmware.observe('[BOARD:GRBLFilmCut]')
        self.assertTrue(a.automaticMatLoading())
        a.mat_handling.active = True
        a.workflow.update_state()
        self.assertEqual(str(a.workflow.load_button.cget("state")), "disabled")
        self.assertEqual(str(a.workflow.loading_mode.cget("state")), "disabled")
        self.assertEqual(str(a.workflow.mat_stop.cget("state")), "normal")
        self.assertIn('mat loading', a.workflow.start_reason())
        a.mat_handling.active = False
        a.sender.firmware = None

    def test_cutting_controls_lock_while_running(self):
        a = self.app
        a.sender.running = True
        a.workflow.update_state()
        self.assertEqual(str(a.workflow.material.cget("state")), "disabled")
        self.assertEqual(str(a.workflow.load_button.cget("state")), "disabled")
        self.assertEqual(str(a.workflow.next_button.cget("state")), "disabled")
        a.sender.running = False

    def test_disconnect_invalidates_mat_confirmation(self):
        w = self.app.workflow
        self.app.sender.serial = object()
        CNC.vars["state"] = "Idle"
        w.update_state()
        w.confirmed.set(True)
        self.assertTrue(CNC.vars["mat_loaded"])
        self.app.sender.serial = None
        w.update_state()
        self.assertFalse(w.confirmed.get())

    def test_compensation_restores_source_and_undo_on_failure(self):
        from PlotterAdapters import DocumentJobPort
        a = self.app
        original = a.gcode.blocks
        snapshot = [(list(b), b.enable) for b in original]
        undo = list(a.gcode.undoredo.undoList)
        def fail(path, *args):
            path.clear()
            raise RuntimeError("compensation failure")
        with patch("PlotterCompensation.compensate_path", fail):
            with self.assertRaises(RuntimeError):
                DocumentJobPort(a).compensate(DocumentJobPort(a).parameters())
        self.assertIs(a.gcode.blocks, original)
        self.assertEqual([(list(b), b.enable) for b in original], snapshot)
        self.assertEqual(a.gcode.undoredo.undoList, undo)

    def test_real_compensation_preserves_source(self):
        from PlotterAdapters import DocumentJobPort
        a = self.app
        original = [(list(b), b.enable) for b in a.gcode.blocks]
        result = DocumentJobPort(a).compensate(DocumentJobPort(a).parameters())
        self.assertIsNotNone(result)
        self.assertIsNotNone(planned_cut_bounds(result))
        self.assertEqual([(list(b), b.enable) for b in a.gcode.blocks], original)

    def test_overcut_setting_extends_the_compensated_path(self):
        from PlotterAdapters import DocumentJobPort
        a = self.app
        original = a.gcode.blocks
        previous = CNC.vars.get('mat_overcut', 0)
        lengths = []
        try:
            for overcut in (0, 2):
                CNC.vars['mat_overcut'] = overcut
                result = DocumentJobPort(a).compensate(DocumentJobPort(a).parameters())
                a.gcode.blocks = result
                lengths.append(sum(path.length() for i, b in enumerate(result)
                    if b.enable and b.name() not in ('Header', 'Footer') for path in a.gcode.toPath(i)))
                a.gcode.blocks = original
        finally:
            a.gcode.blocks = original
            CNC.vars['mat_overcut'] = previous
        self.assertGreater(lengths[1], lengths[0])


if __name__ == "__main__":
    unittest.main()
