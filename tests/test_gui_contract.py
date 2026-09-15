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

    def test_connection_transport_form_switches_without_connecting(self):
        page=self.w.connection_settings();self.app.update()
        page.transport.set('Network');page.choose_transport();self.app.update()
        self.assertTrue(page.network_form.winfo_ismapped());self.assertFalse(page.usb_form.winfo_ismapped())
        page.host.set('plotter.local');page.network_port.set('99999')
        with patch.object(self.app.connection,'connect') as connect:
            page.connect();connect.assert_not_called()
        page.transport.set('USB');page.choose_transport();self.app.update()
        self.assertTrue(page.usb_form.winfo_ismapped());self.assertFalse(page.network_form.winfo_ismapped())
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
