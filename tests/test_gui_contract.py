"""Real-widget acceptance checks for workspace pages and the shared visual system."""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_adaptive_gui as adaptive
from PlotterUI import descendants, RoundedButton, ChoiceButton, Field, fit_dialog


@unittest.skipUnless(os.environ.get('DISPLAY'), 'Requires Xvfb')
class VisualContractTest(unittest.TestCase):
    setUpClass = classmethod(adaptive.AdaptiveGUITest.setUpClass.__func__)
    tearDownClass = classmethod(adaptive.AdaptiveGUITest.tearDownClass.__func__)
    setUp = adaptive.AdaptiveGUITest.setUp
    tearDown = adaptive.AdaptiveGUITest.tearDown
    add_square_fixture = adaptive.AdaptiveGUITest.add_square_fixture

    def test_repeated_controls_reuse_font_measurements(self):
        from PlotterPages import WorkspacePage
        page = WorkspacePage(self.app)
        first = RoundedButton(page, text='Repeated action', font=('DejaVu Sans', 11))
        with patch('PlotterUI.tkfont.Font.measure', side_effect=AssertionError('Redundant font measurement')):
            second = RoundedButton(page, text='Repeated action', font=('DejaVu Sans', 11))
            second.configure(minimum_height=second._minimum_height)
        self.assertEqual(first.winfo_reqwidth(), second.winfo_reqwidth())

    def test_page_styling_is_scoped_and_presentation_is_idempotent(self):
        from PlotterPages import WorkspacePage
        from PlotterAppearance import apply_appearance
        page = WorkspacePage(self.app)
        RoundedButton(page, text='Local page action').pack()
        with patch('PlotterAppearance.system_dark') as system, patch.object(self.w.project_button, 'configure') as configure:
            fit_dialog(page, self.app)
            binding = page.bind('<Configure>')
            responsive = page._responsive_text
            fit_dialog(page, self.app)
            self.assertIs(page._responsive_text, responsive)
            self.assertEqual(page.bind('<Configure>'), binding)
            system.assert_not_called()
            configure.assert_not_called()
        self.assertEqual(self.app.workspace_pages.count(page), 1)

    def test_touch_exit_is_visible_and_uses_normal_quit(self):
        for size in ('320x600', '1280x900'):
            self.app.geometry(size); self.app.update()
            with patch.object(self.app, 'quit') as quit_app:
                page = self.w.open_menu(); self.app.update()
                button = next(w for w in descendants(page) if isinstance(w, RoundedButton) and w.cget('text') == 'Exit application')
                self.assertTrue(button.winfo_ismapped())
                self.assertGreaterEqual(button.winfo_height(), 48)
                self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), self.app.winfo_rooty()+self.app.winfo_height())
                button.invoke(); quit_app.assert_called_once()
                page.destroy()

    def test_exit_cancel_preserves_controls_and_motion_always_blocks_exit(self):
        widgets = list(self.app.widgets)
        with patch.object(self.app, 'destroy') as destroy, patch.object(self.app, 'saveConfig') as save, patch.object(self.app, 'fileModified', return_value=True):
            self.app.quit()
            self.assertEqual(self.app.widgets, widgets)
            destroy.assert_not_called(); save.assert_not_called()
        for service, attr in ((self.app.sender, 'running'), (self.app.mat_handling, 'active'), (self.app.tool_sequence, 'active')):
            with patch.object(service, attr, True), patch('bmain.messagebox.showinfo') as info, patch.object(self.app, 'destroy') as destroy:
                self.app.quit(); self.app.quit()
                self.assertEqual(info.call_count, 2); destroy.assert_not_called()
        with patch.object(self.app, 'destroy') as destroy, patch.object(self.app, 'saveConfig') as save, patch.object(self.app, 'fileModified', return_value=False), patch.object(self.w.project, 'clear_recovery') as clear:
            self.app.quit()
            destroy.assert_called_once(); save.assert_called_once(); clear.assert_called_once()
        self.app.widgets[:] = widgets

    def test_node_mouse_drag_updates_preview_then_apply_and_undo(self):
        self.w.select_all()
        before = [list(b) for b in self.app.gcode.blocks]
        page = self.w.design_dialog('ContourDialog'); self.app.update(); page.rebuild()
        x, y = page.node_positions[0]
        start_x, start_y = float(page.x.get()), float(page.y.get())
        a, b = page._preview_map((0,0)), page._preview_map((1,1))
        page.preview.event_generate('<Button-1>', x=round(x), y=round(y))
        page.preview.event_generate('<B1-Motion>', x=round(x)+20, y=round(y)-15)
        self.assertAlmostEqual(float(page.x.get()), start_x+20/(b[0]-a[0]), places=5)
        self.assertAlmostEqual(float(page.y.get()), start_y-15/(b[1]-a[1]), places=5)
        self.assertEqual([list(b) for b in self.app.gcode.blocks], before)
        self.assertAlmostEqual(page.node_positions[0][0], x+20, places=3)
        page.preview.event_generate('<ButtonRelease-1>', x=round(x)+20, y=round(y)-15)
        self.assertIsNone(page._drag_map)
        # The moved point remains pickable without snapping back to its original coordinates.
        moved = (page.x.get(), page.y.get()); x,y = page.node_positions[0]
        page.pick_node(SimpleNamespace(x=x, y=y))
        self.assertEqual((page.x.get(), page.y.get()), moved)
        page.release_node(SimpleNamespace(x=x, y=y))
        self.assertTrue(page.insert())
        self.assertNotEqual([list(b) for b in self.app.gcode.blocks], before)
        self.app.undo()
        self.assertEqual([list(b) for b in self.app.gcode.blocks], before)

    def test_node_drag_ignores_empty_space_other_operations_and_busy_machine(self):
        self.w.select_all()
        page = self.w.design_dialog('ContourDialog'); self.app.update(); page.rebuild()
        original = (page.x.get(), page.y.get())
        page.pick_node(SimpleNamespace(x=-100, y=-100))
        page.drag_node(SimpleNamespace(x=50, y=50))
        self.assertEqual((page.x.get(), page.y.get()), original)
        page.operation.set('Delete node'); page.rebuild()
        x,y = page.node_positions[0]; page.pick_node(SimpleNamespace(x=x,y=y))
        page.drag_node(SimpleNamespace(x=x+10,y=y+10))
        self.assertIsNone(page._drag_map)
        page.operation.set('Move node'); page.rebuild()
        x,y = page.node_positions[0]; page.pick_node(SimpleNamespace(x=x,y=y))
        with patch.object(self.app.sender, 'running', True):
            page.drag_node(SimpleNamespace(x=x+10,y=y+10))
        self.assertIsNone(page._drag_map)
        self.assertEqual((page.x.get(), page.y.get()), original)

    def test_phone_navigation_and_canvas_remain_visible(self):
        for width,height in ((320,600),(390,844),(600,600),(768,800),(840,700),(1024,600),(1280,900),(1440,900)):
            self.app.geometry(f'{width}x{height}');self.app.update()
            for button in self.w.tabs + ([self.w.more_tab] if width<600 else [self.w.menu_button]):
                self.assertTrue(button.winfo_ismapped())
                self.assertGreaterEqual(button.winfo_height(),48)
                self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.app.winfo_rootx()+width)
            self.assertGreater(self.app.canvasFrame.winfo_height(),75)
            self.assertGreaterEqual(self.w.next_button.winfo_height(),56)
            self.w.toggle_inspector();self.app.update()
            self.assertFalse(self.w.sidebar.winfo_ismapped())
            self.w.toggle_inspector();self.app.update()

    def test_pages_stack_preserves_draft_and_restores_workspace(self):
        from PlotterPages import WorkspacePage
        first=self.w.design_dialog('ShapeDialog');self.app.update()
        self.assertIsInstance(first,WorkspacePage)
        self.assertEqual(first.geometry(),f'{first.winfo_width()}x{first.winfo_height()}')
        self.assertTrue(first.title())
        self.assertEqual(first.resizable(),(True,True))
        self.assertIs(first.transient(),self.app)
        callback=lambda:None;first.protocol('WM_DELETE_WINDOW',callback)
        self.assertIs(first.protocol('WM_DELETE_WINDOW'),callback)
        second=self.w.settings('Appearance');self.app.update()
        self.assertEqual(self.app.workspace_pages[-2:],[first,second])
        self.assertFalse(self.w.action_area.winfo_ismapped())
        self.w.show_step(1);self.assertEqual(self.w.step,0)
        second.destroy();self.assertIs(self.app.workspace_pages[-1],first)
        first.destroy();self.app.update()
        self.assertTrue(self.w.action_area.winfo_ismapped())

    def test_palette_density_and_choice_controls(self):
        from PlotterAppearance import apply_appearance,LIGHT,DARK,system_dark,save_appearance
        import Utils
        old=(Utils.getStr('Plotter','appearance','System'),Utils.getStr('Plotter','density','Comfortable'))
        try:
            page=self.w.settings('Appearance');self.app.update()
            palette=apply_appearance(self.app,'Dark','Compact for mouse');self.app.update()
            self.assertEqual(palette,DARK)
            self.assertEqual(page.cget('bg'),DARK['surface'])
            self.assertGreaterEqual(self.w.next_button._minimum_height,56)
            self.assertEqual(page.apply_button._minimum_height,44)
            apply_appearance(self.app,'Light','Comfortable');self.assertEqual(page.cget('bg'),LIGHT['surface'])
            self.app.geometry('390x844');self.app.update()
            save_appearance(self.app,'Dark','Compact for mouse')
            self.assertEqual(page.apply_button._minimum_height,48)
            variable=tk.StringVar(page,'a')
            choice=ChoiceButton(page,text='Option',variable=variable,value='b');choice.pack()
            choice.invoke();self.assertEqual(variable.get(),'b')
            variable.set('a');choice.destroy()
            field=Field(page,bg='white');field.configure(fg='black');self.assertEqual(field.cget('fg'),'black');field.destroy()
            with patch.dict(os.environ,{'GTK_THEME':'Adwaita-dark'}):self.assertTrue(system_dark())
            with patch.dict(os.environ,{'GTK_THEME':''}),patch('PlotterAppearance.subprocess.run',side_effect=OSError):self.assertFalse(system_dark())
            with patch.dict(os.environ,{'GTK_THEME':''}),patch('PlotterAppearance.subprocess.run',return_value=SimpleNamespace(stdout="'prefer-dark'")):self.assertTrue(system_dark())
        finally:
            save_appearance(self.app,*old)

    def test_library_search_new_and_back_preserve_form(self):
        self.app.geometry('390x844');self.app.update()
        self.w.library.save('materials',dict(name='Acceptance vinyl'))
        page=self.w.open_library();self.app.update()
        page.searches['materials'].set('Acceptance');page.refresh('materials')
        self.assertEqual(page.lists['materials'].get(0,'end'),('Acceptance vinyl',))
        page.refresh('materials','Acceptance vinyl');self.app.update()
        self.assertTrue(page.details['materials'].detail)
        page.details['materials'].show_list();self.app.update()
        self.assertTrue(page.lists['materials'].winfo_ismapped())
        page.new('materials');self.app.update()
        self.assertTrue(page.details['materials'].detail)
        page.forms['materials']['name'].set('Draft')
        page.details['materials'].show_list();page.details['materials'].show_detail()
        self.assertEqual(page.forms['materials']['name'].get(),'Draft')
        page.use_on_layer('materials');self.assertIn('Select artwork',page.message.get())
        page.destroy()

    def test_library_use_on_layer_is_staged(self):
        self.w.select_all();self.w.library.save('materials',dict(name='Layer vinyl'))
        page=self.w.open_library();page.refresh('materials','Layer vinyl')
        before=[list(b) for b in self.app.gcode.blocks]
        page.use_on_layer('materials');self.app.update()
        layer=self.app.workspace_pages[-1]
        self.assertIsNot(layer,page);self.assertEqual(layer.material_profile.get(),'Layer vinyl')
        self.assertEqual(before,[list(b) for b in self.app.gcode.blocks])
        layer.destroy();page.destroy()

    def test_unsaved_prompt_has_explicit_results(self):
        from PlotterPages import WorkspacePage, ask_save_changes
        for label,result in [('Save project','yes'),('Discard changes','no'),('Keep editing','cancel')]:
            def choose(page):
                next(c for c in descendants(page) if isinstance(c,RoundedButton) and c.cget('text')==label).invoke()
            # Invoke only once the prompt has finished construction. The Tk
            # modal wait itself is platform behavior, not our decision logic.
            with patch.object(WorkspacePage,'wait_window',choose):
                self.assertEqual(ask_save_changes(self.app),result)

    def test_connection_disconnect_and_serial_labels(self):
        page = self.w.connection_settings()
        for size in ('320x600', '1280x900'):
            self.app.geometry(size); self.app.update()
            button = page.disconnect_button
            self.assertTrue(button.winfo_ismapped())
            self.assertGreaterEqual(button.winfo_height(), 48)
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(), self.app.winfo_rootx()+self.app.winfo_width())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), self.app.winfo_rooty()+self.app.winfo_height())
        labels = [str(w.cget('text')) for w in descendants(page) if isinstance(w, (tk.Label, RoundedButton))]
        self.assertIn('Serial port', labels)
        self.assertFalse(any('USB' in label for label in labels))
        with patch.object(self.app, 'close') as close, patch.object(self.app, 'open') as connect:
            self.assertTrue(page.disconnect())
            close.assert_not_called(); connect.assert_not_called()
        for service, attr in ((self.app.sender, 'running'), (self.app.mat_handling, 'active'), (self.app.tool_sequence, 'active')):
            with patch.object(service, attr, True), patch.object(self.app, 'close') as close:
                self.assertFalse(page.disconnect()); close.assert_not_called()
        self.app.sender.serial = object()
        with patch.object(self.app, 'close', side_effect=OSError('Port busy')):
            self.assertFalse(page.disconnect())
            self.assertIn('Could not disconnect', page.message.get())
        def close_port():
            self.app.sender.serial = None
            self.app.sender.firmware = None
        self.w.confirmed.set(True)
        with patch.object(self.app, 'close', side_effect=close_port) as close, patch.object(self.app, 'open') as connect:
            page.disconnect_button.invoke()
            close.assert_called_once(); connect.assert_not_called()
        self.assertIsNone(self.app.sender.serial)
        self.assertFalse(self.w.confirmed.get())
        self.assertIsNone(self.w._connection)
        self.assertTrue(page.winfo_exists())
        self.assertIn('Plotter disconnected', page.message.get())

    def test_connection_transport_form_switches_without_connecting(self):
        page=self.w.connection_settings();self.app.update()
        page.transport.set('Network');page.choose_transport();self.app.update()
        self.assertTrue(page.network_form.winfo_ismapped());self.assertFalse(page.serial_form.winfo_ismapped())
        page.host.set('plotter.local');page.network_port.set('99999')
        with patch.object(self.app.connection,'connect') as connect:
            page.connect();connect.assert_not_called()
        page.transport.set('Serial port');page.choose_transport();self.app.update()
        self.assertTrue(page.serial_form.winfo_ismapped());self.assertFalse(page.network_form.winfo_ismapped())
        page.destroy()

    def test_alarm_actions_stay_visible_on_short_phone(self):
        from PlotterErrorDialog import show_modal_error
        self.app.geometry('320x600');self.app.update()
        page=show_modal_error(self.w,self.app,'Controller alarm','ALARM:1 Hard limit triggered')
        self.app.update()
        buttons={c.cget('text'):c for c in descendants(page) if isinstance(c,RoundedButton)}
        buttons['Show details'].invoke();self.app.update()
        for button in buttons.values():
            self.assertTrue(button.winfo_ismapped())
            self.assertGreaterEqual(button.winfo_height(),48)
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),page.winfo_rooty()+page.winfo_height())
        page.destroy()

    def test_cut_preview_has_compact_legend_and_optional_details(self):
        self.w.clear_notice(); self.w._cut_started = False
        page = self.w.design_dialog('CutPreviewDialog')
        for size in ('1868x1060', '1280x900', '390x844', '320x600'):
            self.app.geometry(size); self.app.update(); page.rebuild(); self.app.update()
            self.assertFalse(page.details.winfo_manager())
            self.assertNotIn('add to your mat', page.subtitle.cget('text'))
            check = next(w for w in page.controls.winfo_children() if isinstance(w, tk.Checkbutton))
            self.assertGreaterEqual(float(check.cget('wraplength')), page.controls.winfo_width()-24)
            self.assertIn('of', page.position_text.get())
            with patch.object(self.app.sender, 'sendGCode') as send:
                page.position.set(0); page.draw_preview()
                self.assertEqual(page.position_text.get(), f'0 of {len(page.paths)} outlines')
                send.assert_not_called()
            page.details_button.invoke(); self.app.update()
            self.assertTrue(page.details.winfo_manager())
            self.assertGreaterEqual(float(page.details.cget('wraplength')), page.controls.winfo_width()-24)
            page.details_button.invoke(); self.app.update()
            self.assertFalse(page.details.winfo_manager())
        page.destroy()

    def test_cut_mat_layout_stays_mapped_during_idle_polling(self):
        from CNC import CNC
        self.w._cut_started = False
        self.w.show_step(2)
        self.app.sender.serial = object(); CNC.vars['state'] = 'Idle'
        self.w.update_state(); self.app.update()
        changes = []
        self.w.cut_mat_controls.bind('<Unmap>', lambda e: changes.append('hidden'), add='+')
        self.w.cut_mat_controls.bind('<Map>', lambda e: changes.append('shown'), add='+')
        layout = self.w.cut_mat_controls.pack_info()
        for _ in range(30):
            self.w.update_state(); self.app.update()
        self.assertEqual(changes, [])
        self.assertEqual(self.w.cut_mat_controls.pack_info(), layout)
        self.assertTrue(self.w.cut_mat_controls.winfo_ismapped())

    def test_finished_cut_exposes_unload_after_phone_preview(self):
        from CNC import CNC
        self.w.clear_notice()
        self.app.geometry('320x600'); self.w.show_step(2)
        self.app.sender.serial = object(); CNC.vars['state'] = 'Run'
        self.app.sender.running = True; self.w._cut_started = True
        self.w.update_state(); self.w.toggle_preview(); self.app.update()
        self.app.sender.running = False; CNC.vars['state'] = 'Idle'
        self.w.update_state(); self.app.update()
        self.assertEqual(self.w.job_state, 'Job ended')
        self.assertFalse(self.w.preview_visible)
        self.assertTrue(self.w.finished_unload.winfo_ismapped())
        self.assertLessEqual(self.w.finished_unload.winfo_rooty()+self.w.finished_unload.winfo_height(), self.w.scroll.winfo_rooty()+self.w.scroll.winfo_height())
        self.assertFalse(self.w.next_button.winfo_ismapped())
        self.assertFalse(self.w.cut_setup.winfo_ismapped())
        with patch.object(self.app, 'unloadMat') as unload:
            self.w.finished_unload.invoke(); unload.assert_called_once()
        self.assertFalse(self.w.confirmed.get())
        with patch.object(self.app.mat_handling, 'active', True), patch.object(self.app.mat_handling, 'loading', False):
            self.w.update_state(); self.app.update()
            self.assertEqual(self.w.job_heading.cget('text'), 'Unloading mat')
            self.assertTrue(self.w.stop_button.winfo_ismapped())

    def test_finished_cut_appears_above_open_page_without_losing_it(self):
        from CNC import CNC
        self.app.sender.serial = object(); CNC.vars['state'] = 'Idle'
        self.w._cut_started = False; self.w.update_state()
        draft = self.w.settings('Appearance'); self.app.update()
        self.w._cut_started = True; self.w.update_state(); self.app.update()
        page = self.app.workspace_pages[-1]
        self.assertIsNot(page, draft)
        self.assertEqual(page.title(), 'Job ended')
        self.assertTrue(draft.winfo_exists())
        button = next(w for w in descendants(page) if isinstance(w, RoundedButton) and w.cget('text') == 'Unload mat')
        with patch.object(self.app, 'unloadMat') as unload:
            button.invoke(); unload.assert_called_once()
        self.assertIs(self.app.workspace_pages[-1], draft)
        draft.destroy()
        self.w.update_state()
        self.w.report_error('Connection interrupted', 'Disconnected')
        self.w._cut_started = True; self.w.update_state(); self.app.update()
        page = self.app.workspace_pages[-1]
        self.assertEqual(page.title(), 'Job ended')
        self.assertTrue(self.w.notice.winfo_manager())
        page.destroy()

    def test_connection_status_visible_on_phone_desktop_and_pages(self):
        from CNC import CNC
        self.w._cut_started = False
        for size in ('320x600', '1280x900'):
            self.app.geometry(size); self.app.sender.serial = None
            self.w.update_state(); self.app.update()
            self.assertEqual(self.w.connection_status.cget('text'), 'Disconnected')
            self.app.sender.serial = object(); CNC.vars['state'] = 'Idle'
            self.w.update_state(); page = self.w.open_menu(); self.app.update()
            status = self.w.connection_status
            self.assertEqual(status.cget('text'), 'Connected · Idle')
            self.assertTrue(status.winfo_ismapped())
            self.assertLessEqual(status.winfo_rooty()+status.winfo_height(), page.winfo_rooty())
            page.destroy()

    def test_connection_loss_never_claims_physical_completion(self):
        self.w.show_step(2);self.w._cut_started=True
        self.app.sender.serial=None;self.w.update_state();self.app.update()
        self.assertEqual(self.w.job_heading.cget('text'),'Connection lost')
        self.assertIn('unknown',self.w.cut_message.cget('text'))
        self.assertTrue(self.w.reconnect_button.winfo_ismapped())
        self.w.another_job_button.invoke();self.app.update()
        self.assertEqual(self.w.step,1)
        self.assertFalse(self.w.confirmed.get())
        self.assertFalse(self.w._cut_started)

    def test_disabled_actions_remain_labeled_and_cannot_invoke(self):
        from unittest.mock import Mock
        from PlotterPages import WorkspacePage
        page=WorkspacePage(self.app)
        command=Mock();button=RoundedButton(page,text='Start cut',command=command)
        button.pack();fit_dialog(page,self.app)
        button.configure(state='disabled');self.app.update()
        self.assertTrue(button._disabled_cover.winfo_ismapped())
        self.assertEqual(button.cget('text'),'Start cut')
        button.invoke();command.assert_not_called()
        button.configure(state='normal');self.app.update()
        self.assertFalse(button._disabled_cover.winfo_ismapped())
        button.invoke();command.assert_called_once()
        page.destroy()

    def test_idle_inspector_does_not_repaint_reflow_or_disappear(self):
        from PIL import ImageTk
        for size in ('1280x900','840x700','390x844'):
            self.app.geometry(size);self.app.update()
            for selected in (False,True):
                (self.w.select_all if selected else self.w.select_none)()
                self.w.update_state();self.app.update()
                self.w.scroll.yview_moveto(1);self.app.update()
                controls=self.w.selection_actions+[self.w.more_tools]
                before=[(c.winfo_x(),c.winfo_y(),c.winfo_width(),c.winfo_height()) for c in controls]
                view=self.w.scroll.yview()
                callbacks=len(self.w.stop_button._tclCommands)
                images=self.app.tk.call('image','names')
                with patch('PlotterUI.ImageTk.PhotoImage',wraps=ImageTk.PhotoImage) as paint:
                    for _ in range(100):
                        self.w.update_state();self.app.update()
                    paint.assert_not_called()
                self.assertEqual(callbacks,len(self.w.stop_button._tclCommands))
                self.assertLessEqual(set(self.app.tk.call('image','names')),set(images))
                self.assertEqual(view,self.w.scroll.yview())
                self.assertEqual(before,[(c.winfo_x(),c.winfo_y(),c.winfo_width(),c.winfo_height()) for c in controls])
                for control in controls:self.assertTrue(control.winfo_ismapped())
                for control in self.w.selection_actions:
                    self.assertEqual(control.cget('state'),'normal' if selected else 'disabled')

    def test_repeated_command_configuration_keeps_one_callback(self):
        from PlotterPages import WorkspacePage
        from unittest.mock import Mock
        page=WorkspacePage(self.app);first=Mock();second=Mock()
        button=RoundedButton(page,text='Action',command=first);button.pack();fit_dialog(page,self.app)
        count=len(button._tclCommands)
        for _ in range(100):button.configure(command=first,text='Action')
        self.assertEqual(count,len(button._tclCommands))
        button.invoke();first.assert_called_once()
        button.configure(command=second);button.invoke();second.assert_called_once()
        count=len(button._tclCommands)
        for _ in range(100):button.configure(command=second)
        self.assertEqual(count,len(button._tclCommands))
        page.destroy()
