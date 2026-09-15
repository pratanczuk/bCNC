"""Mat-first desktop views composed with document, machine and job services."""

import math
import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import Utils
from CNC import CNC
from PlotterJob import bounds_fit, cut_settings_valid, design_bounds, readiness, validate_blade_profile, calibration_blocks


from PlotterTheme import BG, PANEL, INK, MUTED, ACCENT, SOFT


class PlotterWorkflow:
    def __init__(self, app):
        self.app = app
        self.step = 0
        self.confirmed = tk.BooleanVar(app, False)
        self.tool_confirmed = tk.BooleanVar(app, False)
        self._sequence_phase = None
        self._objects = None
        self._connection = None
        self._last_fault = None
        self._mat_geometry = None
        self._was_running = False
        self._cut_started = False
        self._stopped = False
        self.import_filename = ""
        style = ttk.Style(app)
        style.configure("Foil.TCombobox", padding=8)
        style.map("Foil.TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", INK)])
        self.profiles = {}
        self.blade_profiles = {}
        try:
            stored_blades = json.loads(Utils.getStr("Plotter", "blade_profiles", "{}"))
        except (ValueError, TypeError):
            stored_blades = {}
        if isinstance(stored_blades, dict):
            for name, values in stored_blades.items():
                try:
                    if isinstance(values, dict):
                        self.blade_profiles[name] = validate_blade_profile(values)
                except (ValueError, TypeError):
                    continue
        try:
            stored = json.loads(Utils.getStr("Plotter", "material_profiles", "{}"))
            if isinstance(stored, dict):
                for name, values in stored.items():
                    if isinstance(values, dict):
                        speed, strength = float(values.get("speed", 0)), float(values.get("strength", -1))
                        if cut_settings_valid(speed, strength):
                            self.profiles[name] = {"speed": speed, "strength": strength}
        except (ValueError, TypeError):
            pass
        from PlotterLibrary import ProfileLibrary
        saved_library = Utils.getStr('Plotter', 'profile_library', '')
        try:
            self.library = ProfileLibrary(json.loads(saved_library) if saved_library else None,
                                          self.profiles, self.blade_profiles)
        except (ValueError, TypeError, KeyError) as error:
            self.library = ProfileLibrary(materials=self.profiles, blades=self.blade_profiles)
            app.after_idle(lambda message=str(error): self.report_error('Library could not load', message))
        self.tool_pass = tk.StringVar(app, 'All included layers')
        self.confirmed.trace_add("write", self.confirmation_changed)
        self.edit_widgets = []
        self.machine_widgets = []
        self.header = tk.Frame(app, bg=PANEL, padx=20, pady=12)
        self.header.pack(side=tk.TOP, fill=tk.X, before=app.paned)
        self.label(self.header, "Foil Studio", size=20, bold=True).pack(side=tk.LEFT)
        self.brand_subtitle = self.label(self.header, "bCNC · mat cutting", muted=True)
        self.brand_subtitle.pack(side=tk.LEFT, padx=16)
        self.header.bind("<Configure>", self.resize_header)
        self.diagnostics_button = self.button(
            self.header, "Advanced settings", lambda: self.settings("Advanced"))
        self.diagnostics_button.pack(side=tk.RIGHT)
        self.nav = tk.Frame(self.header, bg=PANEL)
        self.nav.pack(side=tk.RIGHT, padx=20)
        self.tabs = []
        for i, name in enumerate(("1  Design", "2  Prepare", "3  Cut")):
            b = self.button(self.nav, name, lambda i=i: self.show_step(i))
            b.pack(side=tk.LEFT, padx=3)
            self.tabs.append(b)

        self.sidebar = tk.Frame(app.canvasPane, width=330, bg=PANEL, padx=16, pady=14)
        self.sidebar.pack(side=tk.RIGHT, fill=tk.Y, before=app.canvasFrame)
        self.sidebar.pack_propagate(False)
        self.action_area = tk.Frame(app, bg=PANEL, padx=16, pady=8)
        self.action_area.pack(side=tk.BOTTOM, fill=tk.X, before=app.paned)
        self.next_button = self.button(self.action_area, "", self.next_step, primary=True)
        self.next_button.pack(side=tk.RIGHT)
        self.back_button = self.button(self.action_area, "← Back", lambda: self.show_step(self.step - 1))
        self.back_button.pack(side=tk.LEFT)
        self.pause_button = self.button(self.action_area, "Pause", self.pause)
        self.stop_button = self.button(self.action_area, "Stop cut", self.stop)
        viewport = tk.Frame(self.sidebar, bg=PANEL)
        viewport.pack(fill=tk.BOTH, expand=True)
        viewport.columnconfigure(0, weight=1, minsize=0)
        viewport.rowconfigure(0, weight=1)
        self.scroll = tk.Canvas(viewport, bg=PANEL, highlightthickness=0, width=1)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(viewport, orient=tk.VERTICAL, command=self.scroll.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.scroll.config(yscrollcommand=self.scrollbar.set)
        self.content = tk.Frame(self.scroll, bg=PANEL)
        self.content_window = self.scroll.create_window(0, 0, window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda e: self.scroll.config(scrollregion=self.scroll.bbox("all")))
        self.notice = tk.Frame(self.content, bg="#fff0e7", padx=10, pady=10)
        self.notice_title = tk.StringVar(app)
        tk.Label(self.notice, textvariable=self.notice_title, bg="#fff0e7", fg=INK,
                 font=('DejaVu Sans', 14, 'bold'), anchor='w', wraplength=235,
                 justify=tk.LEFT).pack(fill=tk.X, pady=(2, 10))
        self.notice_text = tk.StringVar(app)
        tk.Label(self.notice, textvariable=self.notice_text, bg="#fff0e7", fg=INK,
                 font=('DejaVu Sans', 11), anchor='w', wraplength=235, justify=tk.LEFT).pack(fill=tk.X)
        self.notice_action = self.button(self.notice, "", lambda: None, primary=True)
        self.notice_action.pack(fill=tk.X, pady=(12, 6))
        self.unlock_button = self.button(self.notice, "Unlock after inspection", self.unlock_plotter)
        self.unlock_button.pack(fill=tk.X, pady=4)
        row = tk.Frame(self.notice, bg='#fff0e7')
        row.pack(fill=tk.X)
        self.details_button = self.button(row, 'Show details', self.toggle_error_details)
        self.details_button.pack(side=tk.LEFT)
        self.button(row, 'Close', self.clear_notice).pack(side=tk.RIGHT)
        self.error_details = tk.Frame(self.notice, bg='#fff0e7')
        self.technical_error = tk.StringVar(app)
        tk.Label(self.error_details, textvariable=self.technical_error, bg='#fff0e7', fg=MUTED,
                 wraplength=230, font=('DejaVu Sans', 9), anchor='w', justify=tk.LEFT).pack(fill=tk.X, pady=8)
        self.button(self.error_details, 'Advanced settings', lambda: self.open_diagnostics('Control')).pack(fill=tk.X)
        self.scroll.bind("<Configure>", lambda e: self.scroll.itemconfig(self.content_window, width=e.width))
        self.panels = [tk.Frame(self.content, bg=PANEL) for _ in range(3)]
        self.build_design(self.panels[0])
        self.build_prepare(self.panels[1])
        self.build_cut(self.panels[2])
        self.bind_scroll(self.content)

        self.toolbar = tk.Frame(app.canvasPane, bg=BG, padx=16, pady=12)
        self.toolbar.pack(side=tk.TOP, fill=tk.X, before=app.canvasFrame)
        self.filename = self.label(self.toolbar, "Untitled design", bg=BG)
        self.filename.pack(side=tk.LEFT)
        for title, command in (("Fit mat", self.fit_mat), ("Select", app.canvas.setActionSelect),
                               ("Move design", app.canvas.setActionMatDrag)):
            self.button(self.toolbar, title, command).pack(side=tk.RIGHT, padx=3)
        self.button(self.toolbar, "Undo", app.undo, edit=True).pack(side=tk.LEFT, padx=(12, 3))
        self.button(self.toolbar, "Redo", app.redo, edit=True).pack(side=tk.LEFT, padx=3)
        self.footer = tk.Frame(app, bg=PANEL, padx=20, pady=10)
        self.footer.pack(side=tk.BOTTOM, fill=tk.X)
        self.connection_label = self.label(self.footer, "Plotter disconnected", muted=True)
        self.connection_label.pack(side=tk.LEFT)
        self.mat_label = self.label(self.footer, "", muted=True)
        self.mat_label.pack(side=tk.RIGHT)
        self.set_workspace()
        self.refresh_library()
        self.show_step(0)
        self.app.after(400, self.fit_mat)
        from PlotterProjectUI import ProjectSession
        self.project = ProjectSession(self)
        if self.project.recoveries():
            self.projects_button.config(text="Recovery copies available…")
        self.poll()

    def label(self, parent, text, size=11, bold=False, muted=False, bg=PANEL):
        return tk.Label(parent, text=text, bg=bg, fg=MUTED if muted else INK,
                        font=("DejaVu Sans", size, "bold" if bold else "normal"),
                        anchor="w", justify=tk.LEFT, wraplength=245)


    def button(self, parent, text, command, primary=False, edit=False, machine=False):
        b = tk.Button(parent, text=text, command=command, relief=tk.FLAT, bd=0,
                      bg=ACCENT if primary else BG, fg="white" if primary else INK,
                      activebackground=SOFT, activeforeground=INK,
                      font=("DejaVu Sans", 11), padx=8, pady=8, cursor="hand2",
                      disabledforeground="#88958f",
                      highlightthickness=1, highlightbackground=BG, highlightcolor=ACCENT)
        if edit:
            self.edit_widgets.append(b)
            self.app.widgets.append(b)
        if machine:
            self.machine_widgets.append(b)
        return b

    def heading(self, parent, title, subtitle):
        self.label(parent, title, size=16, bold=True).pack(fill=tk.X, pady=(0, 6))
        self.label(parent, subtitle, muted=True).pack(fill=tk.X, pady=(0, 8))

    def button_grid(self, parent, actions, edit=False):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill=tk.X, pady=3)
        for column, (title, action) in enumerate(actions):
            row.columnconfigure(column, weight=1, uniform="actions")
            self.button(row, title, action, edit=edit).grid(
                row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 4 if column == 0 else 0))
        return row


    def build_prepare(self, p):
        self.heading(p, "Prepare your cut", "Choose your material and load the mat.")
        row = tk.Frame(p, bg=PANEL)
        row.pack(fill=tk.X)
        self.connect_button = self.button(row, "Connect", self.connect)
        self.connect_button.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.button(row, "Connection…", self.connection_settings).pack(side=tk.RIGHT, padx=(6, 0))
        self.label(p, "Material preset").pack(fill=tk.X, pady=(16, 4))
        row = tk.Frame(p, bg=PANEL)
        row.pack(fill=tk.X)
        self.material = ttk.Combobox(row, state="readonly", style="Foil.TCombobox", width=12,
            font=("DejaVu Sans", 11), values=["Current settings"] + sorted(self.profiles))
        self.material.set("Current settings")
        self.button(row, "Save…", self.save_material, edit=True).pack(side=tk.RIGHT, padx=(6, 0))
        self.material.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.material.bind("<<ComboboxSelected>>", self.apply_material)
        self.edit_widgets.append(self.material)
        self.button(p, "Materials & tools…", self.open_library, edit=True).pack(fill=tk.X, pady=(6, 0))
        self.settings_summary = self.label(p, "", muted=True)
        self.settings_summary.pack(fill=tk.X, pady=10)
        row = tk.Frame(p, bg=PANEL)
        row.pack(fill=tk.X)
        self.button(row, "Pressure…", lambda: self.settings("Material"), edit=True).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.button(row, "Drag knife…", lambda: self.settings("Blade"), edit=True).pack(side=tk.RIGHT, padx=(6, 0))
        self.button(p, "New pressure & corner test", self.new_calibration, edit=True).pack(fill=tk.X, pady=(6, 0))
        self.button(p, "First-cut guide…", lambda: self.design_dialog("FirstCutDialog"), edit=True).pack(fill=tk.X, pady=3)
        self.label(p, 'Tool pass').pack(fill=tk.X, pady=(12,4))
        self.pass_choice = ttk.Combobox(p, textvariable=self.tool_pass, state='readonly', style='Foil.TCombobox', values=['All included layers'])
        self.pass_choice.pack(fill=tk.X)
        self.edit_widgets.append(self.pass_choice)
        self.pass_choice.bind('<<ComboboxSelected>>', lambda e: self.update_state())
        self.pass_hint = self.label(p, 'Assign tools to layers in Layers & objects.', muted=True)
        self.pass_hint.pack(fill=tk.X, pady=6)
        self.label(p, "Mat loading").pack(fill=tk.X, pady=(16, 4))
        self.button(p, "Mat dimensions…", lambda: self.settings("Mat"), edit=True).pack(fill=tk.X, pady=(0, 6))
        self.loading_mode = ttk.Combobox(p, state="readonly", style="Foil.TCombobox", font=("DejaVu Sans", 11),
            values=("Automatic (detect plotter)", "Manual positioning"))
        mode = "manual" if Utils.getStr("Plotter", "load_mode", "auto") == "manual" else "auto"
        Utils.setStr("Plotter", "load_mode", mode)
        self.loading_mode.current(1 if mode == "manual" else 0)
        self.loading_mode.bind("<<ComboboxSelected>>", self.change_loading_mode)
        self.loading_mode.pack(fill=tk.X)
        row = tk.Frame(p, bg=PANEL)
        row.pack(fill=tk.X, pady=8)
        self.load_button = self.button(row, "Load mat", self.load_mat, machine=True)
        self.load_button.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.button(row, "Unload", self.unload_mat, machine=True).pack(side=tk.RIGHT, padx=(6, 0))
        self.mat_stop = self.button(p, "Stop mat movement", self.app.mat_handling.cancel)
        self.mat_stop.pack(fill=tk.X)
        self.loading_hint = self.label(p, "", muted=True)
        self.loading_hint.pack(fill=tk.X, pady=6)
        self.sensor_label = self.label(p, "", muted=True)
        self.sensor_label.pack(fill=tk.X, pady=8)
        self.confirm_check = tk.Checkbutton(p, text="Mat is loaded and aligned", variable=self.confirmed,
            bg=PANEL, fg=INK, selectcolor=PANEL, activebackground=PANEL,
            font=("DejaVu Sans", 11), wraplength=220, justify=tk.LEFT)
        self.confirm_check.pack(anchor="w")
        self.label(p, "Confirm after loading finishes. A sensor cannot confirm alignment.", muted=True).pack(fill=tk.X, pady=8)

    def build_cut(self, p):
        self.heading(p, "Review and cut", "Your design stays visible throughout cutting.")
        self.button(p, 'Preview cut sequence…', lambda: self.design_dialog('CutPreviewDialog'), edit=True).pack(fill=tk.X,pady=6)
        self.button(p, 'Layers, materials & tools…', lambda: self.design_dialog('LayersDialog'), edit=True).pack(fill=tk.X,pady=3)
        self.cut_setup = self.label(p, "", muted=True)
        self.cut_setup.pack(fill=tk.X, pady=(0, 10))
        self.checks = self.label(p, "")
        self.checks.pack(fill=tk.X, pady=12)
        self.cut_message = self.label(p, "", muted=True)
        self.cut_message.pack(fill=tk.X, pady=12)
        self.progress = ttk.Progressbar(p, maximum=100)
        self.progress.pack(fill=tk.X, pady=10)
        self.progress_label = self.label(p, "", muted=True)
        self.progress_label.pack(fill=tk.X)
        self.sequence_panel = tk.Frame(p, bg=SOFT, padx=10, pady=10)
        self.sequence_message = self.label(self.sequence_panel, '', bg=SOFT)
        self.sequence_message.pack(fill=tk.X, pady=(0,8))
        self.tool_check = tk.Checkbutton(self.sequence_panel, text='Tool fitted and aligned; mat unchanged', variable=self.tool_confirmed,
            bg=SOFT, fg=INK, selectcolor=PANEL, activebackground=SOFT, font=('DejaVu Sans',11), wraplength=230, justify=tk.LEFT, command=self.update_state)
        self.tool_check.pack(anchor='w', pady=6)
        self.tool_continue = self.button(self.sequence_panel, 'Continue with this tool', self.continue_tool, primary=True)
        self.tool_continue.pack(fill=tk.X, pady=4)
        self.tool_cancel = self.button(self.sequence_panel, 'Cancel sequence', self.app.tool_sequence.cancel)
        self.tool_cancel.pack(fill=tk.X, pady=4)
        mat_controls = self.cut_mat_controls = tk.Frame(p, bg=PANEL)
        mat_controls.pack(fill=tk.X, before=self.cut_setup, pady=(0,8))
        self.cut_mat_button = self.button(mat_controls, "Load mat", self.cut_mat_action, machine=True)
        self.cut_mat_button.pack(fill=tk.X, pady=(12,6))
        self.cut_mat_hint = self.label(mat_controls, "", muted=True)
        self.cut_mat_hint.pack(fill=tk.X, pady=6)
        self.cut_mat_stop = self.button(mat_controls, "Stop mat movement", self.app.mat_handling.cancel)
        self.cut_confirm_check = tk.Checkbutton(mat_controls, text="Mat is loaded and aligned", variable=self.confirmed,
            bg=PANEL, fg=INK, selectcolor=PANEL, activebackground=PANEL,
            font=("DejaVu Sans", 11), wraplength=220, justify=tk.LEFT)
        self.cut_confirm_check.pack(anchor="w", pady=6)

    def continue_tool(self):
        if not self.tool_confirmed.get():
            return
        try:
            self.app.tool_sequence.continue_pass()
        except ValueError as error:
            self.report_error('Tool change needs attention', str(error))
        self.update_state()

    def cut_mat_action(self):
        if not self.app.machine.snapshot().ready:
            return
        automatic = self.app.automaticMatLoading()
        loaded = (self.app.mat_handling.positioned or self.confirmed.get()) if automatic else self.confirmed.get()
        if loaded and (not automatic or 'P' in CNC.vars.get('pins', '')):
            self.unload_mat()
        else:
            self.load_mat()
        self.update_state()

    def show_step(self, step):
        if (step not in range(3) or self.app.sender.running
                or self.app.mat_handling.active or self.app.tool_sequence.active):
            return
        self.step = step
        for i, panel in enumerate(self.panels):
            panel.pack_forget()
            self.tabs[i].config(bg=SOFT if i == step else PANEL)
        self.panels[step].pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.scroll.yview_moveto(0)
        self.update_state()

    def bind_scroll(self, widget):
        widget.bind("<MouseWheel>", lambda e: self.scroll.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        widget.bind("<Button-4>", lambda e: self.scroll.yview_scroll(-1, "units"))
        widget.bind("<Button-5>", lambda e: self.scroll.yview_scroll(1, "units"))
        for child in widget.winfo_children():
            self.bind_scroll(child)

    def confirmation_changed(self, *args):
        CNC.vars["mat_loaded"] = self.confirmed.get()

    def next_step(self):
        if self.step < 2:
            self.show_step(self.step + 1)
        else:
            reason = self.start_reason()
            if reason:
                messagebox.showinfo("Before cutting", reason, parent=self.app)
                return
            self._stopped = False
            self.app.plotter.start()
            self._cut_started = bool(self.app.sender.running or self.app.tool_sequence.active)
            self.update_state()

    def start_reason(self):
        if self.app.tool_sequence.active:
            return 'Complete or cancel the active tool sequence before starting another job.'
        from PlotterLayers import catalog
        from PlotterProcesses import tool_passes, ALL_TOOLS
        processes = {layer['name']: layer['process'] for layer in catalog(self.app.gcode) if 'process' in layer}
        if processes:
            passes = tool_passes(self.app.gcode.blocks, processes)
            if self.tool_pass.get() != ALL_TOOLS and self.tool_pass.get() not in passes:
                return 'Choose a tool pass with included objects in Prepare.'
        if self.app.mat_handling.active:
            return "Wait for mat loading or unloading to finish."
        if (self.app.sender.serial is not None and not self.app.sender.running
                and str(CNC.vars.get('state', '')).startswith('Hold')):
            return ('The plotter is paused. If this is left over from startup, use '
                    'Advanced settings → Reset controller to discard the queued job, '
                    'then confirm the mat position. Do not resume an unknown job.')
        if self.app.sender.serial is not None and self.app.automaticMatLoading() and "P" not in CNC.vars.get("pins", ""):
            return "Insert the mat under the rollers, then choose Load mat and confirm alignment."
        if CNC.vars.get("mat_confirmation_invalid"):
            return "Confirm the mat position again after the controller reset."
        if CNC.inch:
            return "Set application units to millimeters by applying Advanced settings before cutting."
        if not self.app.sender.queue.empty() or getattr(self.app.sender, "_sumcline", 0):
            return "Wait for pending machine commands to finish."
        firmware = getattr(self.app.sender, 'firmware', None)
        if self.app.sender.serial is not None and firmware is not None and not firmware.ready:
            return firmware.label + ' · waiting for identification, units and work position.'
        if CNC.vars.get('mpg', False):
            return 'Release the external controller before starting a cut.'
        return readiness(self.app.sender.serial is not None, CNC.vars.get("state"),
                         self.app.sender.running, design_bounds(self.app.gcode.blocks),
                         CNC.vars.get("mat_width", 0), CNC.vars.get("mat_height", 0),
                         self.confirmed.get())

    def pause(self):
        if self.app.sender.running:
            self.app.plotter.pause()

    def stop(self):
        if self.app.tool_sequence.active:
            self.app.tool_sequence.cancel()
            return
        self._stopped = True
        self.confirmed.set(False)
        self.app.plotter.stop()

    def set_workspace(self):
        a = self.app
        import CNCCanvas
        CNCCanvas.CANVAS_COLOR = BG
        CNCCanvas.ENABLE_COLOR = ACCENT
        a.canvas.config(background=BG)
        a.canvasFrame.draw_rapid.set(False)
        a.canvasFrame.draw_axes.set(False)
        a.canvasFrame.draw_grid.set(False)
        a.canvasFrame.draw_margin.set(False)
        a.canvasFrame.toggleDrawFlag()
        self.sidebar.pack(side=tk.RIGHT, fill=tk.Y, before=a.canvasFrame)
        self.toolbar.pack(side=tk.TOP, fill=tk.X, before=a.canvasFrame)



    def fit_mat(self):
        c = self.app.canvas
        if c.winfo_width() < 10:
            return
        c.drawCuttingMat()
        box = c.bbox("CuttingMat")
        if not box:
            return
        # Reuse the existing canvas zoom/centering implementation with mat bounds.
        original = c.selBbox
        c.selBbox = lambda: c.bbox("CuttingMat")
        try:
            c.fit2Screen()
        finally:
            c.selBbox = original

    def import_artwork(self):
        if self.app.sender.running:
            return
        path = filedialog.askopenfilename(parent=self.app, title="Import artwork",
            filetypes=[("Vector artwork", "*.svg *.dxf"), ("Cut files", "*.ngc *.nc *.gcode"),
                       ("SVG", "*.svg"), ("DXF", "*.dxf")])
        if path:
            self.app.load(path)
            self._cut_started = False
            self.app.after(300, self.fit_mat)

    def add_text(self):
        return self.design_dialog('TextDialog')

    def add_shape(self):
        return self.design_dialog('ShapeDialog')

    def arrange(self):
        return self.design_dialog('ArrangeDialog')

    def break_apart(self):
        if self.app.sender.running:
            return
        ids = [i for i in self.app.editor.getSelectedBlocks()
               if self.app.gcode.blocks[i].name() not in ('Header', 'Footer')]
        replacements = []
        for i in ids:
            paths = self.app.gcode.toPath(i)
            if len(paths) > 1:
                blocks = []
                for n, path in enumerate(paths, 1):
                    block = self.app.gcode.fromPath(path, z=0)
                    block._name = f'{self.app.gcode.blocks[i].name()} · outline {n}'
                    block.enable = self.app.gcode.blocks[i].enable
                    block.passes = self.app.gcode.blocks[i].passes
                    block.color = self.app.gcode.blocks[i].color
                    source_properties = getattr(self.app.gcode.blocks[i], 'foil', {})
                    block.foil.update({key: source_properties[key] for key in ('group','layer') if key in source_properties})
                    blocks.append(block)
                replacements.append((i, blocks))
        if not replacements:
            self.report_error('Nothing to separate', 'Select an object containing several outlines. Text counters become independent outlines when separated.')
            return
        undo = []
        for i, blocks in sorted(replacements, reverse=True):
            undo.append(self.app.gcode.delBlockUndo(i))
            undo.append(self.app.gcode.insBlocksUndo(i, blocks))
        self.app.gcode.addUndo(undo, 'Break apart outlines')
        self.app.refresh()
        self.update_state()

    def design_dialog(self, kind):
        if self.app.sender.running:
            return
        import PlotterDesign
        existing = getattr(self, '_design_dialog', None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return existing
        if kind in ('LayoutDialog','ContourDialog','WeedDialog','LayersDialog','CutPreviewDialog','ProjectsDialog','FirstCutDialog'):
            import PlotterStudio
            self._design_dialog = getattr(PlotterStudio, kind)(self)
        elif kind == 'TraceDialog':
            from PlotterTrace import TraceDialog
            self._design_dialog = TraceDialog(self)
        else:
            self._design_dialog = getattr(PlotterDesign, kind)(self)
        return self._design_dialog

    def new_design(self):
        if not self.app.sender.running:
            self.app.newFile()
            if len(self.app.gcode.blocks) <= 2:
                self.import_filename = ""
            self._cut_started = False
            self.update_state()

    def finish_import(self, filename):
        """Place imported artwork synchronously, before another edit can occur."""
        self.import_filename = os.path.basename(filename)
        a = self.app
        bounds = design_bounds(a.gcode.blocks)
        if bounds:
            margin = 10 if bounds[2]-bounds[0] <= CNC.vars['mat_width']-20 and \
                           bounds[3]-bounds[1] <= CNC.vars['mat_height']-20 else 0
            items = [(i, None) for i, b in enumerate(a.gcode.blocks)
                     if b.name() not in ('Header', 'Footer')]
            a.gcode.moveLines(items, margin-bounds[0], margin-bounds[1], 0)
            a.gcode.undoredo.reset()
            a.gcode._modified = False
            a.editor.fill()
            if a._drawAfter is not None:
                a.after_cancel(a._drawAfter)
                a._drawAfter = None
            a.draw()
        self._cut_started = False
        self.fit_mat()
        self.update_state()

    def select_objects(self, event=None):
        if self.app.sender.running:
            return
        selected = [self.object_ids[i] for i in self.objects.curselection()]
        selected = self.expand_groups(selected)
        items = [(i, None) for i in selected]
        self.app.editor.select(items, clear=True)
        self.app.selectionChange()

    def expand_groups(self, ids):
        groups = {getattr(self.app.gcode.blocks[i], 'foil', {}).get('group') for i in ids}
        groups.discard(None); groups.discard('')
        return sorted(set(ids) | {i for i,b in enumerate(self.app.gcode.blocks)
            if b.name() not in ('Header','Footer') and getattr(b,'foil',{}).get('group') in groups})


    def transform(self, command, *args):
        if self.app.sender.running:
            return
        ids = self.selection()
        if ids:
            from PlotterTransforms import transform_document
            self.app.busy()
            try:
                transform_document(self.app.gcode, ids, command, *args)
                self.app.editor.selectBlocks(ids)
                self.app.editor.changed()
                self.app.setStatus('Artwork transformed')
            except ValueError as error:
                self.app.reportPlotterError('Could not transform artwork', str(error))
            finally:
                self.app.notBusy()

    def rotate(self):
        ids = self.selection()
        bounds = design_bounds([self.app.gcode.blocks[i] for i in ids])
        if bounds:
            self.transform("ROTATE", 90, (bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2)


    def resize(self):
        ids = self.selection()
        bounds = design_bounds([self.app.gcode.blocks[i] for i in ids])
        if not bounds or bounds[2] <= bounds[0]:
            return
        width = simpledialog.askfloat("Resize design", "Width in mm (proportions stay locked):",
                                      initialvalue=bounds[2]-bounds[0], minvalue=0.01,
                                      parent=self.app)
        if width is not None and math.isfinite(width):
            factor = width/(bounds[2]-bounds[0])
            self.transform("SCALE", factor, factor, bounds[0], bounds[1])

    def center(self):
        ids = self.selection()
        bounds = design_bounds([self.app.gcode.blocks[i] for i in ids])
        if bounds:
            self.transform("MOVE", (CNC.vars['mat_width']-bounds[0]-bounds[2])/2,
                           (CNC.vars['mat_height']-bounds[1]-bounds[3])/2, 0)

    def duplicate(self):
        if not self.app.sender.running and self.selection():
            self.app.editor.clone()
            import uuid
            mapping = {}
            for i in self.app.editor.getSelectedBlocks():
                props = getattr(self.app.gcode.blocks[i], 'foil', {})
                if props.get('group'):
                    props['group'] = mapping.setdefault(props['group'], uuid.uuid4().hex)
            self.transform("MOVE", 10, 10, 0)

    def remove(self):
        if not self.app.sender.running and self.selection():
            self.app.editor.deleteBlock()


    def settings(self, page="Material"):
        if self.app.sender.running and page != "Advanced":
            return
        existing = getattr(self, "settings_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.show_page(page)
            existing.lift()
            return existing
        from PlotterSettings import PlotterSettingsDialog
        self.settings_dialog = PlotterSettingsDialog(self, page)
        return self.settings_dialog

    def new_calibration(self):
        """Create a separate test job; never mix calibration cuts with artwork."""
        if self.app.sender.running or self.app.fileModified():
            return False
        self.app.gcode.init()
        self.app.gcode.headerFooter()
        self.app.gcode.insBlocks(1, calibration_blocks(), "Pressure and drag-knife test")
        self.import_filename = "Pressure & corner test"
        self._cut_started = False
        self.app.refresh()
        self.show_step(1)
        self.app.after_idle(self.fit_mat)
        return True

    def open_library(self):
        if self.app.sender.running or self.app.mat_handling.active or self.app.tool_sequence.active:
            return
        from PlotterLibraryUI import LibraryDialog
        return LibraryDialog(self)

    def refresh_library(self):
        self.profiles = {name: {'speed': record['speed'], 'strength': record['pressure']}
                         for name, record in self.library.records['materials'].items()}
        self.blade_profiles = {name: {'mat_knife_offset': record['offset'], 'mat_overcut': record['overcut'],
                                     'mat_auto_dragknife': record['compensate']}
                               for name, record in self.library.records['tools'].items() if record['kind']=='Knife'}
        self.material.configure(values=['Current settings'] + sorted(self.profiles))
        if self.material.get() not in self.profiles:
            self.material.set('Current settings')
        else:
            active = self.profiles[self.material.get()]
            CNC.vars['mat_speed'], CNC.vars['mat_pressure'] = active['speed'], active['strength']

    def save_library(self):
        Utils.addSection('Plotter')
        Utils.setStr('Plotter', 'profile_library', json.dumps(self.library.snapshot()))
        self.refresh_library()
        Utils.setStr('Plotter', 'material_profiles', json.dumps(self.profiles))
        Utils.setStr('Plotter', 'blade_profiles', json.dumps(self.blade_profiles))

    def apply_material(self, event=None):
        if self.app.sender.running:
            return
        values = self.profiles.get(self.material.get())
        if values:
            CNC.vars["mat_speed"] = values["speed"]
            CNC.vars["mat_pressure"] = values["strength"]
            self.update_state()

    def save_material(self):
        if self.app.sender.running:
            return
        name = simpledialog.askstring("Save material preset", "Name for these tested cut settings:", parent=self.app)
        if not name or not name.strip() or name.strip() == "Current settings":
            return
        name = name.strip()
        speed, strength = CNC.vars.get("mat_speed", 500), CNC.vars.get("mat_pressure", 500)
        if not cut_settings_valid(speed, strength):
            return
        existing = self.library.records['materials'].get(name)
        self.library.save('materials', dict(existing or {}, name=name, speed=speed, pressure=strength), name if existing else None)
        self.save_library()
        Utils.addSection("Plotter")
        Utils.setStr("Plotter", "material_profiles", json.dumps(self.profiles))
        self.material.config(values=["Current settings"] + sorted(self.profiles))
        self.material.set(name)

    def connect(self):
        if not self.app.sender.running:
            self.confirmed.set(False)
            if self.app.sender.serial is None:
                self.connection_settings()
            else:
                self.app.openClose()
                self._connection = None  # An intentional disconnect is not a failure.
                self.clear_notice()

    def connection_settings(self):
        if self.app.sender.running:
            return
        existing = getattr(self, 'connection_dialog', None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return existing
        from PlotterConnection import ConnectionDialog
        self.connection_dialog = ConnectionDialog(self)
        return self.connection_dialog

    def report_error(self, title, detail):
        from PlotterErrors import friendly_error
        self.confirmed.set(False)
        if self.technical_error.get() == f'{title}\n\n{detail}' and self.notice.winfo_manager():
            return
        firmware = getattr(self.app.sender, 'firmware', None)
        if firmware:
            import re
            code = re.search(r'(alarm|error)\s*:\s*(\d+)', str(detail), re.I)
            if code:
                descriptions = firmware.alarms if code[1].lower() == 'alarm' else firmware.errors
                description = descriptions.get(int(code[2]))
                if description: detail = str(detail) + '\nController explanation: ' + description
        heading, message, action, target = friendly_error(title, str(detail))
        self.notice_title.set(heading)
        self.notice_text.set(message)
        self.technical_error.set(f'{title}\n\n{detail}')
        self.error_details.pack_forget()
        self.details_button.config(text='Show details')
        actions = {'connection': self.connection_settings, 'diagnostics': lambda: self.open_diagnostics('Control'),
                   'arrange': self.arrange, 'settings': self.settings, 'design': lambda: self.show_step(0),
                   'details': self.toggle_error_details}
        self.notice_action.config(text=action, command=actions[target])
        self.notice.pack(fill=tk.X, before=self.panels[self.step], pady=(0, 12))
        self.scroll.yview_moveto(0)

    def toggle_error_details(self):
        if self.error_details.winfo_manager():
            self.error_details.pack_forget()
            self.details_button.config(text='Show details')
        else:
            self.error_details.pack(fill=tk.X)
            self.details_button.config(text='Hide details')

    def clear_notice(self):
        self.notice.pack_forget()
        self.notice_text.set('')
        self.notice_title.set('')
        self.technical_error.set('')
        self.error_details.pack_forget()

    def unlock_plotter(self):
        from PlotterErrors import can_unlock
        a = self.app
        if a.sender.serial is None or a.sender.running or not a.sender.queue.empty() or not can_unlock(str(CNC.vars.get('state', ''))):
            return
        self.confirmed.set(False)
        a.sender.unlock()
        self.report_error("Unlock requested", "Wait for the plotter to report Idle. Position may have been lost: restore the origin and confirm the mat before cutting. If the alarm returns, resolve its cause in Advanced settings.")

    def load_mat(self):
        self._cut_started = self._stopped = False
        self.confirmed.set(False)
        self.app.loadMat()

    def change_loading_mode(self, event=None):
        if self.app.sender.running or self.app.mat_handling.active or self.app.tool_sequence.active:
            return
        self.confirmed.set(False)
        Utils.addSection("Plotter")
        Utils.setStr("Plotter", "load_mode", ("auto", "manual")[self.loading_mode.current()])
        self.update_state()

    def unload_mat(self):
        self._cut_started = self._stopped = False
        self.confirmed.set(False)
        self.app.unloadMat()

    def update_state(self):
        a = self.app
        connected = a.sender.serial is not None
        state = CNC.vars.get("state", "Not connected")
        running = bool(a.sender.running)
        mat_active = a.mat_handling.active
        sequence = a.tool_sequence
        busy = running or mat_active or sequence.active
        if self._was_running and not running:
            self.confirmed.set(False)
        fault = state if state.startswith(("Alarm", "ALARM", "Door", "error")) else None
        if fault and fault != self._last_fault:
            self.report_error("Plotter needs attention", f"Controller: {state}\nStop and inspect the blade and mat. Close any open cover. Use Advanced settings to resolve the alarm, then confirm the mat again.")
        if self._connection is not None and not connected:
            self.report_error("Plotter disconnected", f"{getattr(self._connection, 'port', '')}\nCheck power and the USB or network connection, then reconnect. Inspect any interrupted cut and confirm the mat position before starting again.")
        self._last_fault = fault
        from PlotterErrors import can_unlock
        self.unlock_button.config(state=tk.NORMAL if connected and not running and a.sender.queue.empty()
            and can_unlock(state) else tk.DISABLED)
        if connected and can_unlock(state):
            self.unlock_button.pack(fill=tk.X, pady=4)
        else:
            self.unlock_button.pack_forget()
        geometry = (CNC.vars.get("mat_width", 300), CNC.vars.get("mat_height", 300))
        if CNC.vars.pop("mat_confirmation_invalid", False) or a.sender.serial is not self._connection or geometry != self._mat_geometry or \
                not connected or state.startswith(("Alarm", "ALARM", "Door")):
            self.confirmed.set(False)
            a.mat_handling.positioned = False
        self._connection, self._mat_geometry = a.sender.serial, geometry
        bounds = design_bounds(a.gcode.blocks)
        fits = bounds_fit(bounds, *geometry)
        self.filename.config(text=os.path.basename(a.gcode.filename or self.import_filename or "Untitled design"))
        firmware = getattr(a.sender, "firmware", None)
        identity = firmware.label if firmware else "Plotter"
        self.connection_label.config(text=f"{identity} · {state}" if connected else "Plotter disconnected")
        self.mat_label.config(text=f"Mat {geometry[0]:g} × {geometry[1]:g} mm  ·  XY view")
        self.size_label.config(text=(f"{bounds[2]-bounds[0]:.1f} × {bounds[3]-bounds[1]:.1f} mm"
                               + (" · Fits mat" if fits else " · Outside mat")) if bounds else "No design loaded")
        snapshot = tuple((i, b.name() + (" · " + b.foil["layer"] if getattr(b,"foil",{}).get("layer") else "") + (" [attached]" if getattr(b,"foil",{}).get("group") else ""), b.enable) for i, b in enumerate(a.gcode.blocks)
                         if b.name() not in ("Header", "Footer"))
        if snapshot != self._objects:
            self.objects.delete(0, tk.END)
            self.object_ids = []
            for position, (i, name, enabled) in enumerate(snapshot, 1):
                self.object_ids.append(i)
                label = f"Shape {position}" if name.lower() in ("block", "") else name
                self.objects.insert(tk.END, label + ("" if enabled else " (excluded)"))
            self._objects = snapshot
        idle = connected and state == "Idle" and not busy and a.sender.queue.empty() \
            and not getattr(a.sender, "_sumcline", 0)
        for b in self.edit_widgets + self.tabs + [self.connect_button]:
            b.config(state=tk.DISABLED if busy else ("readonly" if b in (self.material, self.pass_choice) else tk.NORMAL))
        for b in self.machine_widgets:
            b.config(state=tk.NORMAL if idle else tk.DISABLED)
        self.loading_mode.config(state=tk.DISABLED if busy else "readonly")
        automatic = a.automaticMatLoading()
        present = 'P' in CNC.vars.get('pins', '')
        if automatic and not present and not busy:
            self.confirmed.set(False)
            a.mat_handling.positioned = False
        can_confirm = idle and (not automatic or present)
        for check in (self.confirm_check, self.cut_confirm_check):
            check.config(state=tk.NORMAL if can_confirm else tk.DISABLED)
        loaded = (a.mat_handling.positioned or self.confirmed.get()) if automatic else self.confirmed.get()
        self.cut_mat_button.config(text='Unload mat' if loaded else 'Load mat' if automatic else 'Set origin here')
        if mat_active:
            self.cut_mat_button.config(text='Loading mat…' if a.mat_handling.loading else 'Unloading mat…')
            self.cut_mat_stop.pack(fill=tk.X, before=self.cut_confirm_check, pady=6)
            hint = a.mat_handling.message
        else:
            self.cut_mat_stop.pack_forget()
            hint = ('Insert the mat under the rollers, then choose Load mat.' if not present else
                    'Check alignment and tick the box below to enable cutting.' if loaded else
                    'Mat detected. Choose Load mat to home and position it, then confirm alignment.') if automatic else                    'Position the mat manually, set its origin, then confirm alignment below.'
        self.cut_mat_hint.config(text=hint if connected else 'Connect the plotter to load the mat.')
        self.mat_stop.config(state=tk.NORMAL if mat_active else tk.DISABLED)
        self.load_button.config(text="Load mat" if automatic else "Set origin here")
        self.loading_hint.config(text=a.mat_handling.message if mat_active else "The blade lifts and the carriage homes automatically before mat movement." if automatic else
            "Align the mat, then set its origin at the blade. For unloading, lift the blade and remove the mat manually.")
        self.objects.config(state=tk.DISABLED if busy else tk.NORMAL)
        self.connect_button.config(text="Disconnect" if connected else "Connect")
        sensor = "Detected" if "P" in CNC.vars.get("pins", "") else "Not detected"
        self.sensor_label.config(text=f"Mat sensor · {sensor}" if connected else "Mat sensor · Offline")
        from PlotterLayers import catalog
        from PlotterProcesses import tool_passes, ALL_TOOLS
        processes = {layer['name']: layer['process'] for layer in catalog(a.gcode) if 'process' in layer}
        passes = tool_passes(a.gcode.blocks, processes) if processes else []
        self.pass_choice.configure(values=[ALL_TOOLS] + passes)
        chosen = self.tool_pass.get()
        if not processes and chosen != ALL_TOOLS:
            self.tool_pass.set(ALL_TOOLS)
        self.pass_hint.configure(text=('Guided sequence: pens first, then knives. X homes before each exchange; confirm each tool before continuing. Keep the mat loaded.') if len(passes)>1 and chosen==ALL_TOOLS else
            ('Fit ' + (chosen if chosen != ALL_TOOLS else ', '.join(passes)) + '. Pen compensation and overcut are off.') if passes else
            'Assign materials and knives or pens in Layers & objects.')
        pressure = CNC.vars.get('mat_pressure', 500)
        knife_on = bool(CNC.vars.get('mat_auto_dragknife'))
        self.settings_summary.config(text=f"Pressure {pressure:g}/1000 · {CNC.vars.get('mat_speed', 500):g} mm/min\n"
            f"Drag knife: {'On' if knife_on else 'Off'}")
        self.cut_setup.config(text=f"Pressure: {pressure:g}/1000 PWM\nSpeed: {CNC.vars.get('mat_speed', 500):g} mm/min\n"
            + (f"Drag knife: On\nOffset: {CNC.vars.get('mat_knife_offset', .5):g} mm\nOvercut: {CNC.vars.get('mat_overcut', 0):g} mm" if knife_on
               else "Drag knife: Off\nEnable compensation for original swivel-blade outlines; leave it off for already-compensated files."))
        if processes:
            from PlotterProcesses import process_label
            selected = sequence.stages[sequence.index].label if sequence.active else self.tool_pass.get()
            descriptions = []
            from PlotterLayers import layer_name
            included = {layer_name(block).casefold() for block in a.gcode.blocks if block.enable and block.name() not in ('Header','Footer')}
            for layer in catalog(a.gcode):
                if not layer['enabled'] or layer['name'].casefold() not in included: continue
                process = layer.get('process')
                if selected != ALL_TOOLS and process_label(process) != selected: continue
                if process:
                    tool = process['tool']
                    material = process['material'] or self.library.records['materials'].get(self.material.get())
                    speed = material['speed'] if material else CNC.vars.get('mat_speed',500)
                    strength = material['pressure'] if material else pressure
                    descriptions.append(f"{layer['name']} · {process['operation']}\n{tool['name']} · {strength:g}/1000 · {speed:g} mm/min\n" +
                        ('Compensation and overcut: Off' if tool['kind']=='Pen' else f"Drag knife: {'On' if tool['compensate'] else 'Off'}"))
                else:
                    descriptions.append(layer['name'] + ' · Current knife settings')
            self.settings_summary.config(text='Layer setups apply to this job. Review the selected tool pass below.')
            self.cut_setup.config(text='\n\n'.join(descriptions) or 'Choose a tool pass with included objects.')
        reason = self.start_reason()
        self.checks.config(text=f"{'✓' if fits else '○'} Design fits the mat\n\n"
            f"{'✓' if idle else '○'} Plotter connected and idle\n\n"
            f"{'✓' if self.confirmed.get() else '○'} Mat position confirmed")
        self.back_button.config(state=tk.DISABLED if busy or self.step == 0 else tk.NORMAL)
        self.next_button.config(text=("Continue to Prepare →", "Review job →", "Start tool sequence" if len(passes)>1 and chosen==ALL_TOOLS else "Start tool pass" if processes else "Start cut")[self.step],
                                state=tk.DISABLED if busy or (self.step == 2 and reason) else tk.NORMAL)
        if running:
            self.pause_button.pack(side=tk.RIGHT, padx=8)
            self.stop_button.pack(side=tk.LEFT, padx=8)
            self.pause_button.config(text="Resume" if a.sender._pause else "Pause")
            self.cut_message.config(text="Cut paused." if a.sender._pause else "Cutting your design…")
            count, total = getattr(a.sender, '_gcount', 0), getattr(a.sender, '_runLines', 0)
            percent = min(100, 100*count/total) if 0 < total < 10**9 else 0
            self.progress.pack(fill=tk.X, pady=10)
            self.progress_label.pack(fill=tk.X)
            self.progress['value'] = percent
            self.progress_label.config(text=f"{percent:.0f}% of commands acknowledged")
        else:
            self.pause_button.pack_forget()
            self.stop_button.pack_forget()
            self.progress.pack_forget()
            self.progress_label.pack_forget()
            text = reason or "Ready. Check your material settings, then start the cut."
            if self._cut_started:
                text = "Cut stopped. Check the material before restarting." if self._stopped else \
                       "Job ended. Check the result and reload or confirm the mat before another cut."
                if reason:
                    text += "\n\n" + reason
            self.cut_message.config(text=text)
        phase = (sequence.active, sequence.phase, sequence.index)
        if phase != self._sequence_phase:
            self._sequence_phase = phase
            self.tool_confirmed.set(False)
        if sequence.active:
            self.cut_mat_controls.pack_forget()
            self.sequence_panel.pack(fill=tk.X, before=self.cut_setup, pady=(8,12))
            self.sequence_message.config(text=sequence.message)
            waiting = sequence.phase=='waiting'
            self.tool_check.config(state=tk.NORMAL if waiting else tk.DISABLED)
            self.tool_continue.config(state=tk.NORMAL if waiting and self.tool_confirmed.get() else tk.DISABLED)
            self.cut_message.config(text=sequence.message)
        else:
            self.sequence_panel.pack_forget()
            self.cut_mat_controls.pack(fill=tk.X, before=self.cut_setup, pady=(0,8))
            if sequence.phase in ('complete', 'cancelled') and self._cut_started:
                self.cut_message.config(text=sequence.message)
        self._was_running = running

    def poll(self):
        try:
            self.update_state()
            self.project.tick()
        finally:
            if self.app.winfo_exists():
                self.app.after(250, self.poll)
