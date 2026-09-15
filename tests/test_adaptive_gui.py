"""Real-widget regression tests for adaptive editing and machine controls."""
import os
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests import test_plotter_workflow as baseline
from CNC import CNC
from PlotterJob import design_bounds
from PlotterUI import layout_for, SplitPanel, ScrollFrame, fit_dialog


class LayoutPolicyTest(unittest.TestCase):
    def test_breakpoints_and_short_windows_keep_useful_space(self):
        for width in (320, 390, 600, 759, 760, 840, 1024, 1440):
            for height in (540, 600, 844, 1080):
                layout = layout_for(width, height)
                self.assertEqual(layout.compact, width < 760)
                self.assertLessEqual(layout.panel_height, height // 2)
                self.assertGreaterEqual(layout.panel_width, 280)


@unittest.skipUnless(os.environ.get('DISPLAY'), 'Requires Xvfb')
class AdaptiveGUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        baseline.WorkflowGUITest.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        baseline.WorkflowGUITest.tearDownClass.__func__(cls)

    add_square_fixture = baseline.WorkflowGUITest.add_square_fixture

    def setUp(self):
        baseline.WorkflowGUITest.setUp(self)
        self.w = self.app.workflow
        self.app.geometry('1024x768')
        self.w.show_step(0)
        self.w.aspect.set(True)
        self.w.select_none()
        self.app.update()

    def tearDown(self):
        for child in self.app.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
        self.app.sender.serial = None
        self.app.sender.running = False
        self.app.sender.emptyQueue()
        self.app.update()

    def test_application_uses_new_workspace_and_resizes_without_losing_document(self):
        from PlotterAdaptive import AdaptiveWorkflow
        self.assertIsInstance(self.w, AdaptiveWorkflow)
        before = [list(b) for b in self.app.gcode.blocks]
        for width, height in ((1280, 900), (840, 700), (390, 844), (320, 600), (1024, 600)):
            self.app.geometry(f'{width}x{height}')
            self.app.update()
            for step in range(3):
                self.w.show_step(step)
                self.app.update()
                for control in self.w.tabs + [self.w.next_button, self.w.back_button]:
                    self.assertTrue(control.winfo_ismapped())
                    self.assertGreaterEqual(control.winfo_rootx(), self.app.winfo_rootx())
                    self.assertLessEqual(control.winfo_rootx() + control.winfo_width(), self.app.winfo_rootx() + width)
                    self.assertLessEqual(control.winfo_rooty() + control.winfo_height(), self.app.winfo_rooty() + height)
        self.assertEqual(before, [list(b) for b in self.app.gcode.blocks])

    def test_no_selection_never_transforms_or_deletes_entire_design(self):
        before = [list(b) for b in self.app.gcode.blocks]
        self.w.remove()
        self.w.center()
        self.assertFalse(self.w.apply_dimensions())
        self.assertEqual(self.w.selection_error.get(), 'Select artwork first.')
        self.assertEqual(before, [list(b) for b in self.app.gcode.blocks])
        self.assertEqual(str(self.w.apply_size['state']), 'disabled')

    def test_numeric_edit_is_one_undo_and_accepts_decimal_comma(self):
        self.w.select_all()
        before = [list(b) for b in self.app.gcode.blocks]
        history_size = len(self.app.gcode.undoredo.undoList)
        self.w.dimensions['width'].set('20,5')
        self.w.dimensions['x'].set('25')
        self.w.dimensions['y'].set('35')
        self.assertTrue(self.w.apply_dimensions())
        bounds = design_bounds(self.app.gcode.blocks)
        self.assertAlmostEqual(bounds[0], 25)
        self.assertAlmostEqual(bounds[1], 35)
        self.assertAlmostEqual(bounds[2] - bounds[0], 20.5)
        self.assertAlmostEqual(bounds[3] - bounds[1], 20.5)
        self.assertEqual(len(self.app.gcode.undoredo.undoList), history_size + 1)
        self.app.undo()
        self.assertEqual(before, [list(b) for b in self.app.gcode.blocks])

    def test_height_drives_locked_scaling_and_unlocked_dimensions_are_independent(self):
        self.w.select_all()
        self.w.dimensions['height'].set('30')
        self.assertTrue(self.w.apply_dimensions())
        bounds = design_bounds(self.app.gcode.blocks)
        self.assertAlmostEqual(bounds[2] - bounds[0], 30)
        self.w.aspect.set(False)
        self.w.dimensions['width'].set('15')
        self.w.dimensions['height'].set('20')
        self.assertTrue(self.w.apply_dimensions())
        bounds = design_bounds(self.app.gcode.blocks)
        self.assertAlmostEqual(bounds[2] - bounds[0], 15)
        self.assertAlmostEqual(bounds[3] - bounds[1], 20)

    def test_rounded_display_does_not_override_height_driven_aspect_lock(self):
        self.w.select_all()
        self.w.dimensions['width'].set('10.1234')
        self.assertTrue(self.w.apply_dimensions())
        self.w.dimensions['height'].set('20')
        self.assertTrue(self.w.apply_dimensions())
        bounds = design_bounds(self.app.gcode.blocks)
        self.assertAlmostEqual(bounds[2] - bounds[0], 20, places=3)
        self.assertAlmostEqual(bounds[3] - bounds[1], 20, places=3)

    def test_invalid_draft_remains_visible_and_does_not_change_artwork(self):
        self.w.select_all()
        before = [list(b) for b in self.app.gcode.blocks]
        for value in ('nan', 'inf', '-1', '0', 'letters'):
            self.w.dimensions['width'].set(value)
            self.assertFalse(self.w.apply_dimensions())
            self.assertTrue(self.w.selection_error.get())
            self.w.update_state()
            self.assertEqual(self.w.dimensions['width'].get(), value)
            self.assertEqual(before, [list(b) for b in self.app.gcode.blocks])

    def test_busy_machine_blocks_dimension_changes_and_tool_launch(self):
        self.w.select_all()
        self.app.sender.running = True
        self.w.update_state()
        self.assertFalse(self.w.apply_dimensions())
        self.assertEqual(str(self.w.apply_size['state']), 'disabled')
        self.assertIsNone(self.w.design_dialog('ShapeDialog'))
        self.assertIsNone(self.w.open_library())
        self.assertIsNone(self.w.settings('Material'))

    def test_job_actions_stay_visible_without_competing_navigation_on_phone(self):
        self.app.geometry('390x844')
        self.app.sender.running = True
        self.w.update_state()
        self.app.update()
        self.assertFalse(self.w.next_button.winfo_ismapped())
        for button in (self.w.stop_button, self.w.pause_button):
            self.assertTrue(button.winfo_ismapped())
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), self.app.winfo_rootx() + 390)
        self.app.sender.running = False
        with patch.object(self.app.mat_handling, 'active', True), \
                patch.object(self.app.mat_handling, 'cancel') as cancel:
            self.w.update_state()
            self.w.stop_button.invoke()
            cancel.assert_called_once()
        self.w.update_state()
        self.app.update()
        self.assertTrue(self.w.next_button.winfo_ismapped())

    def test_zero_extent_reports_a_useful_message(self):
        self.w.select_all()
        with patch('PlotterAdaptive.design_bounds', return_value=(5, 5, 5, 15)):
            self.assertFalse(self.w.apply_dimensions())
        self.assertIn('Contours', self.w.selection_error.get())

    def test_touch_selection_is_explicit_and_panel_switch_preserves_it(self):
        self.add_square_fixture()
        self.w.update_state()
        self.w.show_inspector('Layers')
        self.w.multiple.set(True)
        self.w.multi_selection()
        self.assertEqual(self.w.objects['selectmode'], 'multiple')
        self.w.select_all()
        selected = self.app.editor.getSelectedBlocks()
        self.assertEqual(len(selected), 2)
        self.w.inspector_tabs['Properties'].invoke()
        self.app.update()
        self.assertTrue(self.w.selection_panel.winfo_ismapped())
        self.assertFalse(self.w.layer_panel.winfo_ismapped())
        self.assertEqual(self.app.editor.getSelectedBlocks(), selected)
        self.w.multiple.set(False)
        self.w.multi_selection()
        self.w.select_none()
        self.assertFalse(self.w.selection())

    def test_collapse_panel_and_grid_controls_are_real(self):
        for width, height in ((1024, 768), (840, 700), (390, 844)):
            with self.subTest(width=width):
                self.app.geometry(f'{width}x{height}')
                self.app.update()
                visible_size = (self.app.canvasFrame.winfo_width(),
                                self.app.canvasFrame.winfo_height())
                self.w.inspector_button.invoke()
                self.app.update()
                self.assertFalse(self.w.sidebar.winfo_ismapped())
                self.assertEqual(self.w.inspector_button['text'], 'Show panel')
                axis = 1 if width < 760 else 0
                hidden_size = (self.app.canvasFrame.winfo_width(),
                               self.app.canvasFrame.winfo_height())
                self.assertGreater(hidden_size[axis], visible_size[axis])
                # Crossing the breakpoint must not reopen a hidden panel.
                self.app.geometry('1024x768' if width < 760 else '390x844')
                self.app.update()
                self.assertFalse(self.w.sidebar.winfo_ismapped())
                self.w.inspector_button.invoke()
                self.app.update()
                self.assertTrue(self.w.sidebar.winfo_ismapped())
                self.assertEqual(self.w.inspector_button['text'], 'Hide panel')
        before = self.app.canvasFrame.draw_grid.get()
        self.w.toggle_grid()
        self.assertNotEqual(self.app.canvasFrame.draw_grid.get(), before)
        self.w.toggle_grid()
        self.assertEqual(self.app.canvasFrame.draw_grid.get(), before)
        self.w.resize_workspace(SimpleNamespace(widget=self.w.sidebar))

    def test_all_editing_tools_remain_reachable(self):
        from PlotterAdaptive import EDIT_TOOLS
        self.w.select_all()
        with patch.object(self.w, 'design_dialog') as launch:
            for label, kind in EDIT_TOOLS.items():
                self.w.more_tools.set(label)
                self.w.choose_tool()
                launch.assert_called_with(kind)
        with patch.object(self.w, 'break_apart') as split:
            self.w.more_tools.set('Split outlines')
            self.w.choose_tool()
            split.assert_called_once()
        self.w.more_tools.set('Unknown')
        self.w.choose_tool()

    def test_menu_routes_are_available_without_machine_motion(self):
        with patch('tkinter.Menu.tk_popup'), patch.object(self.app.sender, 'sendGCode') as send:
            menu = self.w.open_menu()
            labels = [menu.entrycget(i, 'label') for i in range(menu.index('end') + 1)]
            self.assertIn('Projects & recovery', labels)
            self.assertIn('Materials & tools', labels)
            self.assertIn('Settings', labels)
            send.assert_not_called()
            menu.destroy()

    def test_machine_window_reuses_service_and_closes_polling(self):
        dialog = self.w.open_machine()
        self.assertIs(self.w.open_machine(), dialog)
        self.assertIs(dialog.machine, self.app.machine)
        self.assertEqual(str(dialog.buttons['X +']['state']), 'disabled')
        self.assertFalse(dialog.jog('X', 1))
        self.assertTrue(dialog.error.get())
        pending = dialog.pending
        dialog.destroy()
        self.assertNotIn(pending, self.app.tk.call('after', 'info'))
        self.assertIsNone(dialog.pending)

    def test_machine_jog_uses_single_sender_and_validates_numeric_input(self):
        self.app.sender.serial = Mock()
        CNC.vars['state'] = 'Idle'
        dialog = self.w.open_machine()
        dialog.step.set('1')
        dialog.speed.set('250')
        dialog.jog('X', -1)
        self.assertEqual(self.app.sender.queue.get_nowait(), '$J=G91 G21 X-1 F250\n')
        dialog.speed.set('bad')
        self.assertFalse(dialog.jog('Y', 1))
        self.assertTrue(self.app.sender.queue.empty())
        for state, running in (('Idle', False), ('ALARM:11', False), ('Run', True)):
            CNC.vars['state'] = state
            self.app.sender.running = running
            dialog.after_cancel(dialog.pending)
            dialog.poll()
            self.assertEqual(str(dialog.buttons['Reset controller']['state']), 'disabled' if running else 'normal')

    def test_settings_flat_categories_and_library_keep_all_original_features(self):
        dialog = self.w.settings('Advanced')
        for label, (page, section) in dialog.categories.items():
            dialog.category.set(label)
            dialog.choose_category()
            self.app.update()
            self.assertEqual(dialog.category.get(), label)
            if section:
                self.assertEqual(dialog.advanced.notebook.select(), str(dialog.advanced.pages[section]))
        self.assertIs(self.w.settings('Mat'), dialog)
        dialog.cancel()
        library = self.w.open_library()
        self.assertEqual(set(library.forms), {'materials', 'tools'})
        library.destroy()

    def test_preview_dialog_reflows_without_discarding_draft(self):
        dialog = self.w.design_dialog('ShapeDialog')
        dialog.kind.set('Star')
        dialog.width.set('25')
        for size in ('900x700', '390x760', '840x700'):
            dialog.geometry(size)
            self.app.update()
            self.assertEqual(dialog.kind.get(), 'Star')
            self.assertEqual(dialog.width.get(), '25')
            self.assertTrue(dialog.insert_button.winfo_ismapped())
            self.assertGreater(dialog.controls.winfo_width(), 230)
        dialog.rebuild()
        self.assertTrue(dialog.paths)

    def test_shared_scroll_and_split_ignore_child_events_and_retain_content(self):
        win = tk.Toplevel(self.app)
        win.geometry('900x700')
        body = tk.Frame(win)
        body.pack(fill='both', expand=True)
        first = tk.Frame(body)
        second = ScrollFrame(body)
        tk.Label(first, text='Preview').pack()
        entry = tk.ttk.Entry(second.body)
        entry.insert(0, 'Draft')
        entry.pack(fill='x')
        split = SplitPanel(body, first, second)
        for size in ('390x700', '900x700', '390x700'):
            win.geometry(size)
            self.app.update()
            split.resize(SimpleNamespace(widget=first, width=1))
            self.assertEqual(entry.get(), 'Draft')
        fit_dialog(win, self.app, 600, 600)

    def test_first_cut_guide_never_starts_motion_and_resumes_at_next_step(self):
        from PlotterStudio import FirstCutDialog
        commands = ('connection_settings', 'settings', 'new_calibration', 'show_step')
        with patch.object(self.app.plotter, 'start') as start:
            for step in range(5):
                self.w.guide_step = step
                dialog = FirstCutDialog(self.w)
                dialog.move(-10)
                self.assertEqual(dialog.step, 0)
                dialog.move(step)
                self.assertEqual(dialog.step, step)
                if step < 4:
                    with patch.object(self.w, commands[step]) as action:
                        dialog.perform()
                        action.assert_called_once()
                else:
                    dialog.perform()
                self.assertEqual(self.w.guide_step, min(4, step + 1))
            start.assert_not_called()

    def test_project_dialog_cancel_keeps_window_and_success_closes_it(self):
        from pathlib import Path
        import tempfile
        from PlotterStudio import ProjectsDialog
        with tempfile.TemporaryDirectory() as folder:
            recovery = Path(folder) / 'recover.foil'
            recovery.write_text('{}')
            with patch.object(self.w.project, 'recent', return_value=['recent.foil']), \
                    patch.object(self.w.project, 'recoveries', return_value=[recovery]):
                for method in ('open', 'save', 'open_recent', 'recover'):
                    dialog = ProjectsDialog(self.w)
                    service = 'save' if method == 'save' else 'open'
                    with patch.object(self.w.project, service, return_value=False) as action:
                        if method in ('open_recent', 'recover'):
                            getattr(dialog, method)()
                            action.assert_not_called()
                            (dialog.list if method == 'open_recent' else dialog.recovery_list).selection_set(0)
                        getattr(dialog, method)()
                        self.assertTrue(dialog.winfo_exists())
                    with patch.object(self.w.project, service, return_value=True):
                        getattr(dialog, method)()
                        self.assertFalse(dialog.winfo_exists())
                dialog = ProjectsDialog(self.w)
                with patch('PlotterStudio.FirstCutDialog') as guide:
                    dialog.guide()
                    guide.assert_called_once_with(self.w)

    def test_project_save_open_export_cancellation_and_errors_preserve_source(self):
        from PlotterProjectUI import ProjectSession
        import tempfile
        from pathlib import Path
        session = ProjectSession(self.w)
        before = [list(b) for b in self.app.gcode.blocks]
        with patch('PlotterProjectUI.filedialog.asksaveasfilename', return_value=''), \
                patch('PlotterProjectUI.filedialog.askopenfilename', return_value=''):
            self.assertFalse(session.save())
            self.assertFalse(session.open())
            self.assertFalse(session.export_cut())
        with tempfile.TemporaryDirectory() as directory, patch.object(self.app, 'reportPlotterError') as error:
            self.assertFalse(session.save(str(Path(directory) / 'bad.ngc')))
            self.assertFalse(session.export_cut(str(Path(directory) / 'bad.foil')))
            with patch('PlotterProjectUI.project.write', side_effect=OSError('Disk full')):
                self.assertFalse(session.save(str(Path(directory) / 'valid.foil')))
                self.app.gcode._modified = True
                session.last_check = 0
                session.tick()
                self.assertTrue(session.failed)
                count = error.call_count
                session.last_check = 0
                session.tick()
                self.assertEqual(error.call_count, count)
        self.assertEqual(before, [list(b) for b in self.app.gcode.blocks])
        self.app.sender.running = True
        self.assertFalse(session.save())
        self.assertFalse(session.open())
        self.assertFalse(session.export_cut())

    def test_connection_scan_failure_and_rejected_connection_keep_dialog_open(self):
        from PlotterConnection import ConnectionDialog
        with patch('serial.tools.list_ports.comports', side_effect=OSError('Unavailable')), \
                patch.object(self.app, 'reportPlotterError'):
            dialog = ConnectionDialog(self.w)
            self.assertIn('couldn’t list', dialog.message.get())
        with patch.object(self.app.connection, 'connect', return_value=False):
            self.assertFalse(dialog.connect())
            self.assertTrue(dialog.winfo_exists())
        with patch.object(self.app.connection, 'connect', side_effect=ValueError('Invalid host')):
            self.assertFalse(dialog.connect())
            self.assertEqual(dialog.message.get(), 'Invalid host')

    def test_palette_color_choice_and_busy_library_save(self):
        dialog = self.w.open_library()
        with patch('PlotterLibraryUI.colorchooser.askcolor', return_value=((0, 0, 0), '#123456')):
            dialog.pick_color()
            self.assertEqual(dialog.forms['tools']['color'].get(), '#123456')
        self.app.sender.running = True
        dialog.save('tools')
        self.assertIn('Wait', dialog.message.get())

    def test_secondary_screens_fit_compact_width_and_preserve_primary_actions(self):
        from PlotterUI import descendants
        self.app.geometry('390x844')
        self.app.update()
        self.w.select_all()
        for kind in ('TextDialog', 'ShapeDialog', 'TraceDialog', 'CombineDialog',
                     'OutlineDialog', 'LayoutDialog', 'ContourDialog', 'WeedDialog',
                     'CutPreviewDialog', 'LayersDialog'):
            with self.subTest(kind=kind):
                dialog = self.w.design_dialog(kind)
                self.app.update()
                self.assertLessEqual(dialog.winfo_width(), 390)
                self.assertTrue(dialog.insert_button.winfo_ismapped())
                self.assertLessEqual(dialog.insert_button.winfo_rootx() + dialog.insert_button.winfo_width(),
                                     dialog.winfo_rootx() + dialog.winfo_width())
                self.assertLessEqual(dialog.insert_button.winfo_rooty() + dialog.insert_button.winfo_height(),
                                     dialog.winfo_rooty() + dialog.winfo_height())
                dialog.destroy()
        library = self.w.open_library()
        self.app.update()
        visible_add = [b for b in descendants(library) if isinstance(b, tk.Button)
                       and b['text'] == 'Add' and b.winfo_ismapped()]
        self.assertTrue(visible_add)
        for b in visible_add:
            self.assertLessEqual(b.winfo_rooty() + b.winfo_height(), library.winfo_rooty() + library.winfo_height())
        library.destroy()

    def test_error_details_toggle_and_close_return_to_editor(self):
        from PlotterErrorDialog import show_modal_error
        from PlotterUI import descendants
        dialog = show_modal_error(self.w, self.app, 'Could not connect', 'Port is busy')
        self.app.update()
        buttons = {b['text']: b for b in descendants(dialog) if isinstance(b, tk.Button)}
        buttons['Show details'].invoke()
        self.app.update()
        self.assertEqual(buttons['Show details']['text'], 'Hide details')
        buttons['Show details'].invoke()
        self.assertEqual(buttons['Show details']['text'], 'Show details')
        buttons['Back to editing'].invoke()
        self.assertFalse(dialog.winfo_exists())


if __name__ == '__main__':
    unittest.main()
