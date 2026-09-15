"""Adaptive Foil Studio workspace, reusing the existing document/job services."""
import math
import tkinter as tk
from PlotterUI import Field
from tkinter import ttk

from CNC import CNC
from PlotterJob import design_bounds
from PlotterTheme import BG, PANEL, INK, MUTED, ACCENT, SOFT
from PlotterUI import DANGER, BORDER, FOCUS, install_theme, layout_for, polish, fit_dialog
from PlotterWorkflow import PlotterWorkflow


EDIT_TOOLS = {
    'Combine': 'CombineDialog', 'Offset & border': 'OutlineDialog',
    'Layout & repeat': 'LayoutDialog', 'Contours & nodes': 'ContourDialog',
    'Weeding lines': 'WeedDialog', 'Cut sequence preview': 'CutPreviewDialog',
}


class AdaptiveWorkflow(PlotterWorkflow):
    def __init__(self, app):
        self.adaptive_ready = False
        self.layout = None
        self.inspector_mode = 'Properties'
        self.selection_signature = None
        self.inspector_visible = True
        install_theme(app)
        super().__init__(app)
        self.brand_subtitle.pack_forget()
        self.diagnostics_button.configure(text='Machine', command=self.open_machine)
        self.menu_button = self.button(self.header, 'More ▾', self.open_menu)
        self.menu_button.pack(side='right', padx=8)
        self.project_button = self.button(self.header, 'Projects', lambda: self.design_dialog('ProjectsDialog'), edit=True)
        self.project_button.pack(side='left', fill='x', expand=True)
        for child in self.header.winfo_children():
            if isinstance(child, tk.Label):
                child.pack_forget()
        self.nav.destroy()
        self.nav = tk.Frame(app, bg=PANEL, padx=12, pady=6)
        self.tabs = []
        for i, label in enumerate(('1  Design', '2  Prepare', '3  Cut')):
            tab = self.button(self.nav, label, lambda step=i: self.show_step(step))
            tab.pack(side='left', fill='x', expand=True, padx=3)
            self.tabs.append(tab)
        self.more_tab = self.button(self.nav, 'More', self.open_menu)
        for child in self.toolbar.winfo_children():
            child.destroy()
        self.filename = self.label(self.toolbar, 'Untitled design', bg=BG, size=10)
        # Project name and save state live in the header.
        self.tool_row = tk.Frame(self.toolbar, bg=BG)
        self.tool_row.pack(fill='x', pady=(6, 0))
        self.tool_buttons = []
        for label, command in [('Select', app.canvas.setActionSelect), ('Pan', app.canvas.setActionPan),
                               ('Move', app.canvas.setActionMove), ('Fit mat', self.fit_mat),
                               ('Undo', app.undo), ('Redo', app.redo)]:
            button = self.button(self.tool_row, label, command, edit=label in ('Move', 'Undo', 'Redo'))
            self.tool_buttons.append(button)
        self.grid_button = self.button(self.tool_row, 'Grid', self.toggle_grid)
        self.tool_buttons.append(self.grid_button)
        self.inspector_button = self.button(self.tool_row, 'Inspector', self.toggle_inspector)
        self.tool_buttons.append(self.inspector_button)
        self.stop_button.configure(bg=DANGER, fg='white', text='Stop job', activebackground=DANGER, activeforeground='white')
        self.preview_visible = False
        self.preview_button = self.button(self.toolbar, 'Show preview', self.toggle_preview)
        for button in (self.pause_button, self.stop_button, self.next_button, self.tool_continue, self.tool_cancel):
            button.configure(minimum_height=56)
        self.adaptive_ready = True
        app.widgets[:] = [w for w in app.widgets if w.winfo_exists()]
        app.minsize(320, 540)
        self.resize_binding = app.bind('<Configure>', self.resize_workspace, add='+')
        self.resize_workspace()
        polish(app)
        from PlotterAppearance import apply_appearance
        apply_appearance(app)
        self.update_state()

    def resize_header(self, event):
        # The adaptive workspace owns the compact header; no subtitle reappears.
        self.brand_subtitle.pack_forget()

    def button(self, parent, text, command, primary=False, edit=False, machine=False):
        b = super().button(parent, text, command, primary, edit, machine)
        b.configure(padx=12, pady=10, font=('DejaVu Sans', 11), takefocus=True,
                    highlightcolor=FOCUS, highlightbackground=BORDER,
                    disabledforeground='#63757d')
        return b

    def build_design(self, p):
        self.label(p, 'Artwork', size=16, bold=True).pack(fill='x', pady=(0, 8))
        self.button_grid(p, [('Import…', self.import_artwork), ('Save project', lambda: self.project.save())], edit=True)
        self.projects_button = self.button(p, 'Projects & recovery…', lambda: self.design_dialog('ProjectsDialog'), edit=True)
        # Available from the header menu; retained for recovery notification.
        self.button_grid(p, [('Text', self.add_text), ('Shape', self.add_shape), ('Trace', self.app.showImageTrace)], edit=True)
        self.size_label = self.label(p, '', muted=True, size=10)
        self.size_label.pack(fill='x', pady=8)
        nav = tk.Frame(p, bg=PANEL)
        nav.pack(fill='x', pady=6)
        self.inspector_tabs = {}
        for name in ('Properties', 'Layers'):
            b = self.button(nav, name, lambda n=name: self.show_inspector(n))
            b.pack(side='left', fill='x', expand=True, padx=2)
            self.inspector_tabs[name] = b
        self.selection_panel = tk.Frame(p, bg=PANEL)
        self.layer_panel = tk.Frame(p, bg=PANEL)
        self.objects = tk.Listbox(self.layer_panel, height=5, selectmode=tk.EXTENDED,
                                 exportselection=False, font=('DejaVu Sans', 12), bg=BG,
                                 fg=INK, selectbackground=SOFT, selectforeground=INK)
        self.objects.pack(fill='x')
        self.objects.bind('<<ListboxSelect>>', self.select_objects)
        self.object_ids = []
        self.multiple = tk.BooleanVar(self.app, False)
        tk.Checkbutton(self.layer_panel, text='Select multiple', variable=self.multiple,
                       command=self.multi_selection, bg=PANEL, fg=INK).pack(fill='x')
        self.button_grid(self.layer_panel, [('Select all', self.select_all), ('Clear', self.select_none)], edit=True)
        self.button(self.layer_panel, 'Layer materials & tools…', lambda: self.design_dialog('LayersDialog'), edit=True).pack(fill='x', pady=8)
        self.selection_title = self.label(self.selection_panel, 'Select an object on the mat', bold=True)
        self.selection_title.pack(fill='x', pady=6)
        self.dimensions = {}
        form = tk.Frame(self.selection_panel, bg=PANEL)
        form.pack(fill='x')
        for index, (key, label) in enumerate((('width', 'Width · mm'), ('height', 'Height · mm'),
                                            ('x', 'X · mm'), ('y', 'Y · mm'))):
            cell = tk.Frame(form, bg=PANEL)
            cell.grid(row=index // 2, column=index % 2, sticky='ew', padx=(0, 6), pady=4)
            form.columnconfigure(index % 2, weight=1, uniform='dimensions')
            self.label(cell, label, size=10).pack(anchor='w')
            var = tk.StringVar(self.app)
            entry = Field(cell, textvariable=var, width=8, font=('DejaVu Sans', 12), relief='flat')
            entry.pack(fill='x')
            entry.bind('<Return>', lambda e: self.apply_dimensions())
            self.dimensions[key] = var
        self.aspect = tk.BooleanVar(self.app, True)
        tk.Checkbutton(self.selection_panel, text='Lock proportions', variable=self.aspect,
                       bg=PANEL, fg=INK).pack(fill='x')
        self.selection_error = tk.StringVar(self.app)
        tk.Label(self.selection_panel, textvariable=self.selection_error, fg=DANGER,
                 bg=PANEL, wraplength=260, justify='left').pack(fill='x')
        self.selection_actions = []
        self.apply_size = self.button(self.selection_panel, 'Apply size & position', self.apply_dimensions, edit=True)
        self.apply_size.pack(fill='x', pady=4)
        self.selection_actions.append(self.apply_size)
        for actions in ([('Rotate 90°', self.rotate), ('Center', self.center)],
                        [('Duplicate', self.duplicate), ('Delete', self.remove)]):
            row = self.button_grid(self.selection_panel, actions, edit=True)
            self.selection_actions.extend(row.winfo_children())
        self.more_tools = ttk.Combobox(self.selection_panel, state='readonly',
                                      values=list(EDIT_TOOLS) + ['Split outlines'], style='Foil.TCombobox')
        self.more_tools.set('More editing tools…')
        self.more_tools.pack(fill='x', pady=8)
        self.more_tools.bind('<<ComboboxSelected>>', self.choose_tool)
        self.show_inspector('Properties')

    def show_inspector(self, name):
        self.inspector_mode = name
        self.selection_panel.pack_forget()
        self.layer_panel.pack_forget()
        (self.layer_panel if name == 'Layers' else self.selection_panel).pack(fill='both', expand=True)
        for key, button in self.inspector_tabs.items():
            button.configure(bg=SOFT if key == name else BG)

    def multi_selection(self):
        self.objects.configure(selectmode=tk.MULTIPLE if self.multiple.get() else tk.EXTENDED)

    def select_all(self):
        self.app.editor.select([(i, None) for i in self.object_ids], clear=True)
        self.app.selectionChange()
        self.update_state()

    def select_none(self):
        self.app.editor.select([], clear=True)
        self.app.selectionChange()
        self.update_state()

    def selection(self):
        ids = [i for i in self.app.editor.getSelectedBlocks()
               if 0 <= i < len(self.app.gcode.blocks) and self.app.gcode.blocks[i].name() not in ('Header', 'Footer')]
        ids = self.expand_groups(ids)
        self.app.editor.select([(i, None) for i in ids], clear=True)
        return ids

    def apply_dimensions(self):
        if self.app.sender.running or self.app.mat_handling.active or self.app.tool_sequence.active:
            return False
        ids = self.selection()
        bounds = design_bounds([self.app.gcode.blocks[i] for i in ids])
        if not bounds:
            self.selection_error.set('Select artwork first.')
            return False
        try:
            values = {key: float(var.get().replace(',', '.')) for key, var in self.dimensions.items()}
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError('Enter finite numbers for size and position.')
            if min(values['width'], values['height']) <= 0:
                raise ValueError('Width and height must be greater than zero.')
            x, y, right, top = bounds
            if right == x or top == y:
                raise ValueError('Use Contours to edit a zero-width or zero-height path.')
            sx, sy = values['width'] / (right - x), values['height'] / (top - y)
            if values['width'] == round(right - x, 3):
                sx = 1
            if values['height'] == round(top - y, 3):
                sy = 1
            if self.aspect.get():
                # The changed dimension drives locked scaling; width wins if both changed.
                if abs(sx - 1) < 1e-8:
                    sx = sy
                sy = sx
            from PlotterTransforms import transform_document
            history = self.app.gcode.undoredo.undoList
            start = len(history)
            transform_document(self.app.gcode, ids, 'SCALE', sx, sy, x, y)
            dx = 0 if values['x'] == round(x, 3) else values['x'] - x
            dy = 0 if values['y'] == round(y, 3) else values['y'] - y
            transform_document(self.app.gcode, ids, 'MOVE', dx, dy, 0)
            changes = history[start:]
            del history[start:]
            self.app.gcode.addUndo(changes, 'Size & position')
            self.app.editor.changed()
            self.selection_signature = None
            self.update_state()
            self.selection_error.set('')
            return True
        except ValueError as error:
            self.selection_error.set(str(error))
            return False

    def choose_tool(self, event=None):
        choice = self.more_tools.get()
        self.more_tools.set('More editing tools…')
        if choice == 'Split outlines':
            self.break_apart()
        elif choice in EDIT_TOOLS:
            self.design_dialog(EDIT_TOOLS[choice])

    def toggle_grid(self):
        self.app.canvasFrame.draw_grid.set(not self.app.canvasFrame.draw_grid.get())
        self.app.canvasFrame.drawGrid()
        self.app.draw()

    def toggle_inspector(self):
        self.inspector_visible = not self.inspector_visible
        self.layout = None
        self.resize_workspace()

    def toggle_preview(self):
        self.preview_visible = not self.preview_visible
        self.layout = None
        self.resize_workspace()

    def resize_workspace(self, event=None):
        if not self.adaptive_ready or (event is not None and event.widget is not self.app):
            return
        width, height = self.app.winfo_width(), self.app.winfo_height()
        layout = layout_for(width, height)
        signature = (width, height, layout, self.step, self.preview_visible, self.inspector_visible)
        if signature == self.layout:
            return
        self.layout = signature
        self.header.configure(padx=layout.padding, pady=8)
        self.nav.pack_forget()
        self.nav.pack(side='bottom' if width < 600 else 'top', fill='x', before=self.app.paned)
        self.more_tab.pack_forget()
        if width < 600:
            self.more_tab.pack(side='left', fill='x', expand=True, padx=2)
            self.menu_button.pack_forget()
        else:
            self.menu_button.pack(side='right', padx=8)
        for i, tab in enumerate(self.tabs):
            tab.configure(text=('Design', 'Prepare', 'Cut')[i] if width < 600 else ('1  Design', '2  Prepare', '3  Cut')[i], padx=6 if width < 600 else 12, font=('DejaVu Sans', 10 if width < 600 else 11))
        self.more_tab.configure(padx=6, font=('DejaVu Sans', 10))
        self.nav.configure(padx=8 if width < 600 else 12)
        self.project_button.pack(side='left', fill='x', expand=True)
        self.project_button.configure(font=('DejaVu Sans', 10), padx=4)
        self.sidebar.pack_forget()
        self.app.canvasFrame.pack_forget()
        self.toolbar.pack_forget()
        self.tool_row.pack_forget()
        self.preview_button.pack_forget()
        editing = self.step == 0
        if editing:
            self.toolbar.configure(padx=4 if width >= 1200 else layout.padding, pady=8)
            self.toolbar.pack(side='left' if width >= 1200 else 'top', fill='y' if width >= 1200 else 'x')
            self.tool_row.pack(fill='both')
            columns = 1 if width >= 1200 else 4 if width < 600 else 8
            from PlotterTk import Balloon
            for index, button in enumerate(self.tool_buttons):
                label = ('Select', 'Pan', 'Move', 'Fit mat', 'Undo', 'Redo', 'Grid', 'Panel')[index]
                button.configure(icon=label if width >= 1200 else None)
                Balloon.set(button, label)
                button.grid(row=index // columns, column=index % columns, sticky='ew', padx=2, pady=4)
                self.tool_row.columnconfigure(index % columns, weight=1, uniform='toolbar')
            for index in range(columns, 8):
                self.tool_row.columnconfigure(index, weight=0, minsize=0, uniform='')
        elif layout.compact:
            self.toolbar.configure(padx=layout.padding, pady=4)
            self.toolbar.pack(side='top', fill='x')
            self.preview_button.configure(text='Back to setup' if self.preview_visible else 'Show preview')
            self.preview_button.pack(anchor='e')
        if layout.compact:
            self.mat_label.pack_forget()
            if editing:
                self.sidebar.configure(height=min(layout.panel_height, max(130, (height - 350) // 2)), width=width)
                if self.inspector_visible:
                    self.sidebar.pack(side='bottom', fill='x')
                self.app.canvasFrame.pack(fill='both', expand=True)
            elif self.preview_visible:
                self.app.canvasFrame.pack(fill='both', expand=True)
            else:
                self.sidebar.configure(width=width)
                self.sidebar.pack(fill='both', expand=True)
        else:
            self.sidebar.configure(width=layout.panel_width if editing else 400)
            if self.inspector_visible or not editing:
                self.sidebar.pack(side='right', fill='y')
            self.app.canvasFrame.pack(fill='both', expand=True)
            self.mat_label.pack(side='right')
        self.inspector_button.configure(text=('Hide' if self.inspector_visible else 'Panel') if width < 600 else ('Hide panel' if self.inspector_visible else 'Show panel'))
        self.update_project_title()
        for page in getattr(self.app, 'workspace_pages', []):
            page.after_idle(page._resize)

    def show_step(self, step):
        if getattr(self.app, 'workspace_pages', []):
            return
        super().show_step(step)
        if self.adaptive_ready:
            self.inspector_visible = True
            self.preview_visible = False
            self.layout = None
            self.resize_workspace()

    def update_state(self):
        # Toolbar replacement destroys original registered edit buttons.
        self.edit_widgets[:] = [w for w in self.edit_widgets if w.winfo_exists()]
        if self.adaptive_ready and not self.cut_setup.winfo_manager():
            self.cut_setup.pack(fill='x')
        super().update_state()
        if not self.adaptive_ready:
            return
        ids = self.selection()
        bounds = design_bounds([self.app.gcode.blocks[i] for i in ids])
        signature = (tuple(ids), bounds)
        if signature != self.selection_signature:
            self.selection_signature = signature
            self.selection_title.configure(text=(f'{len(ids)} objects selected' if len(ids) != 1
                                            else self.app.gcode.blocks[ids[0]].name()) if ids else 'Select an object on the mat')
            values = dict(width=bounds[2] - bounds[0], height=bounds[3] - bounds[1], x=bounds[0], y=bounds[1]) if bounds else {}
            for key, var in self.dimensions.items():
                var.set(f'{values[key]:.3f}'.rstrip('0').rstrip('.') if key in values else '')
            self.selection_error.set('')
        busy = self.app.sender.running or self.app.mat_handling.active or self.app.tool_sequence.active
        for button in self.selection_actions:
            button.configure(state='normal' if ids and not busy else 'disabled')
        self.more_tools.configure(state='readonly' if ids and not busy else 'disabled')
        self.grid_button.configure(bg=SOFT if self.app.canvasFrame.draw_grid.get() else BG)
        for index, button in enumerate(self.tabs):
            button.configure(bg=SOFT if index == self.step else PANEL)
        pages_open = bool(getattr(self.app, 'workspace_pages', []))
        if pages_open and not busy:
            self.action_area.pack_forget()
        elif not self.action_area.winfo_manager():
            self.action_area.pack(side='bottom', fill='x', before=self.app.paned)
        if busy or pages_open:
            self.next_button.pack_forget()
            self.back_button.pack_forget()
        else:
            self.next_button.pack(side='right')
            self.back_button.pack(side='left')
        self.update_project_title()
        self.update_job_presentation()
        self.stop_button.configure(command=self.stop, text='Stop job')
        if self.app.mat_handling.active:
            self.stop_button.configure(command=self.app.mat_handling.cancel, text='Stop movement')
            self.stop_button.pack(side='left', padx=8)
        if self.app.tool_sequence.active and not self.app.sender.running:
            self.stop_button.configure(text='Stop job')
            self.stop_button.pack(side='left', padx=8)

    def update_project_title(self):
        project_name = self.filename.cget('text') or 'Untitled'
        save_state = 'Unsaved changes' if self.app.gcode.isModified() else 'Saved' if str(self.app.gcode.filename).endswith('.foil') else 'Not saved as project'
        from tkinter import font
        from PlotterTk import Balloon
        full = project_name
        if self.app.winfo_width() >= 600:
            project_name = 'Foil Studio · ' + project_name
        available = max(80, self.app.winfo_width() - (150 if self.app.winfo_width() < 600 else 270))
        measure = font.Font(self.app, font=('DejaVu Sans', 10)).measure
        for value_name in ('project_name', 'save_state'):
            value = project_name if value_name == 'project_name' else save_state
            while measure(value) > available and len(value) > 2:
                value = value[:-2] + '…'
            if value_name == 'project_name': project_name = value
            else: save_state = value
        self.project_button.configure(text=project_name + '\n' + save_state, bg=PANEL)
        Balloon.set(self.project_button, full)

    def build_cut(self, parent):
        super().build_cut(parent)
        children = parent.winfo_children()
        self.review_widgets = children[:4] + [self.cut_setup, self.checks, self.cut_mat_controls]
        self.review_layout = {w: w.pack_info() for w in self.review_widgets if w.winfo_manager()}
        for widget in children[:2]:
            widget.pack_forget()
        self.job_heading = self.label(parent, 'Review job', size=20, bold=True)
        self.job_heading.pack(fill='x', before=children[2], pady=(0, 16))
        self.job_state = None
        self.reconnect_button = self.button(parent, 'Connection setup', self.connection_settings)
        self.another_job_button = self.button(parent, 'Prepare another job', self.prepare_another_job)

    def prepare_another_job(self):
        self._cut_started = self._stopped = False
        self.confirmed.set(False)
        self.show_step(1)
        self.update_state()

    def update_job_presentation(self):
        a = self.app
        sequence = a.tool_sequence
        phase = ('Tool change' if sequence.active and sequence.phase == 'waiting' else
                 'Loading mat' if a.mat_handling.active else
                 'Paused' if a.sender.running and a.sender._pause else
                 'Running' if a.sender.running else
                 'Connection lost' if self._cut_started and a.sender.serial is None else
                 'Stopped' if self._cut_started and self._stopped else
                 'Job ended' if self._cut_started else 'Review job')
        self.job_heading.configure(text=phase)
        changed = phase != self.job_state
        self.job_state = phase
        for widget in self.review_widgets:
            widget.pack_forget()
        if phase == 'Review job':
            for widget in self.review_widgets[2:]:
                if widget in self.review_layout:
                    widget.pack(**self.review_layout[widget])
        if phase == 'Tool change':
            self.cut_message.pack_forget()
        else:
            self.cut_message.pack(fill='x', after=self.job_heading, pady=12)
        self.cut_message.configure(font=('DejaVu Sans', 11 if phase == 'Review job' else 14))
        self.reconnect_button.pack_forget()
        self.another_job_button.pack_forget()
        if phase == 'Connection lost':
            self.cut_message.configure(text='The connection was lost. The physical job state is unknown. Check the plotter and material before reconnecting or preparing another job.')
            self.reconnect_button.pack(fill='x', pady=8)
        if phase in ('Stopped', 'Job ended', 'Connection lost'):
            self.another_job_button.pack(fill='x', pady=8)
        if phase == 'Loading mat':
            self.cut_message.configure(text=a.mat_handling.message)
        if self.step == 2 and changed:
            self.scroll.yview_moveto(0)

    def open_menu(self):
        from PlotterPages import WorkspacePage
        from PlotterUI import ScrollFrame
        page = WorkspacePage(self.app)
        page.title('Workspace utilities')
        footer = tk.Frame(page, bg=PANEL, padx=24, pady=16); footer.pack(side='bottom', fill='x')
        self.button(footer, 'Back to workspace', page.destroy).pack(fill='x')
        scroll = ScrollFrame(page); scroll.pack(fill='both', expand=True, padx=24, pady=16)
        self.label(scroll.body, 'Workspace utilities', size=20, bold=True).pack(fill='x', pady=16)
        def navigate(command):
            page.destroy()
            command()
        for label, command in [('Projects & recovery', lambda: self.design_dialog('ProjectsDialog')),
                               ('New project', self.new_design), ('Materials & tools', self.open_library),
                               ('Machine', self.open_machine), ('Settings', lambda: self.settings('Appearance')),
                               ('First-cut guide', lambda: self.design_dialog('FirstCutDialog'))]:
            self.button(scroll.body, label, lambda c=command: navigate(c)).pack(fill='x', pady=4)
        fit_dialog(page, self.app)
        return page

    def open_machine(self):
        from PlotterMachineUI import MachineWindow
        existing = getattr(self, 'machine_window', None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return existing
        self.machine_window = MachineWindow(self)
        return self.machine_window

    def open_diagnostics(self, page='Control'):
        return self.open_machine()

    def design_dialog(self, kind):
        dialog = super().design_dialog(kind)
        if dialog is not None:
            fit_dialog(dialog, self.app)
            if hasattr(dialog, 'rebuild'):
                dialog.rebuild()
        return dialog

    def open_library(self):
        dialog = super().open_library()
        if dialog is not None:
            fit_dialog(dialog, self.app)
        return dialog

    def settings(self, page='Material'):
        dialog = super().settings(page)
        if dialog is not None:
            fit_dialog(dialog, self.app, 740, 760)
        return dialog
