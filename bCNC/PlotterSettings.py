"""Staged, task-oriented settings for the foil-cutting workspace."""

import tkinter as tk
from PlotterUI import Field
from PlotterPages import WorkspacePage
import json
import math
from tkinter import ttk, simpledialog

from CNC import CNC
from PlotterDocument import JobCodeTransaction
import Utils
from PlotterJob import SETTING_FIELDS, validate_settings, validate_blade_profile
from PlotterTheme import PANEL, BG, INK, MUTED, ACCENT, SOFT


class PlotterSettingsDialog(WorkspacePage):
    def __init__(self, workflow, page="Material"):
        super().__init__(workflow.app)
        self.workflow = workflow
        self.app = workflow.app
        self.title("Settings · Foil Studio")
        self.configure(bg=PANEL)
        self.resizable(True, True)
        self.transient(self.app)
        self.values = {
            key: tk.StringVar(self, f"{CNC.vars.get(key, default):g}")
            for key, (_, default, _, _) in SETTING_FIELDS.items()
        }
        self.compensation = tk.BooleanVar(self, bool(CNC.vars.get("mat_auto_dragknife")))
        self.blade_profiles = dict(workflow.blade_profiles)
        self.error = tk.StringVar(self)
        self.entries = {}
        self.pages = {}
        self.tabs = {}
        self.result = False
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda event: self.cancel())

        title = tk.Frame(self, bg=PANEL, padx=24, pady=10)
        title.pack(fill=tk.X)
        self.text(title, "Settings", size=20, bold=True).pack(anchor="w")
        self.text(title, "Job setup and application preferences.", muted=True).pack(fill='x', pady=(8, 0))
        nav = tk.Frame(self, bg=PANEL, padx=24)
        nav.pack(fill=tk.X)
        from PlotterUI import ScrollFrame
        self.scroller = ScrollFrame(self)
        self.scroller.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        content = self.scroller.body
        for name in ("Material", "Blade", "Mat", "Advanced"):
            tab = workflow.button(nav, {"Material": "Pressure & speed", "Blade": "Drag knife", "Mat": "Mat", "Advanced": "Advanced"}[name],
                                  lambda name=name: self.show_page(name))
            self.tabs[name] = tab
            self.pages[name] = tk.Frame(content, bg=PANEL)
        self.category = tk.StringVar(self)
        self.categories = {'Appearance': ('Appearance', None), 'Pressure & speed': ('Material', None), 'Drag knife': ('Blade', None),
                           'Mat setup': ('Mat', None), 'Job commands': ('Advanced', 'Job G-code'),
                           'Planning defaults': ('Advanced', 'Configuration'),
                           'Controller settings': ('Advanced', 'Controller'),
                           'Language & support': ('Advanced', 'System')}
        self.pages['Appearance'] = tk.Frame(content, bg=PANEL)
        picker = ttk.Combobox(nav, textvariable=self.category, values=list(self.categories),
                              state='readonly', style='Foil.TCombobox')
        picker.pack(fill='x')
        picker.bind('<<ComboboxSelected>>', self.choose_category)

        self.appearance = tk.StringVar(self, Utils.getStr('Plotter', 'appearance', 'System'))
        self.density = tk.StringVar(self, Utils.getStr('Plotter', 'density', 'Comfortable'))
        for title, variable, choices in [('Appearance', self.appearance, ('System','Light','Dark')),
                                          ('Control density', self.density, ('Comfortable','Compact for mouse'))]:
            self.text(self.pages['Appearance'], title, bold=True).pack(anchor='w', pady=8)
            ttk.Combobox(self.pages['Appearance'], textvariable=variable, values=choices,
                         state='readonly', style='Foil.TCombobox').pack(fill='x')
        self.text(self.pages['Appearance'], 'Touch layouts retain 48 px controls. Machine job actions stay at least 56 px.', muted=True).pack(fill='x', pady=16)

        p = self.pages["Material"]
        self.text(p, "Set blade exposure mechanically, then test pressure on your material.", muted=True).pack(anchor="w", pady=(0, 14))
        self.field(p, "mat_speed", "Cutting speed", "mm/min", "How quickly the blade moves through the foil.")
        self.field(p, "mat_pressure", "Cutting pressure", "0–1000 PWM", "Applied to the next job. Editing this value does not press the blade.")
        row = tk.Frame(p, bg=PANEL)
        row.pack(fill=tk.X, pady=6)
        workflow.button(row, "−25", lambda: self.adjust_pressure(-25)).pack(side=tk.LEFT)
        workflow.button(row, "+25", lambda: self.adjust_pressure(25)).pack(side=tk.LEFT, padx=8)
        self.text(p, "Machine units, not grams", muted=True).pack(fill=tk.X, pady=4)
        self.text(p, "Test the square: foil should peel cleanly while its backing stays intact. If it cuts the backing, review blade exposure and reduce pressure.", muted=True).pack(fill=tk.X, pady=12)

        p = self.pages["Blade"]
        self.text(p, "Blade-holder preset", bold=True).pack(anchor="w")
        row = tk.Frame(p, bg=PANEL)
        row.pack(fill=tk.X, pady=(6, 8))
        self.blade_choice = ttk.Combobox(row, state="readonly", style="Foil.TCombobox",
            font=("DejaVu Sans", 11), values=["Current blade"] + sorted(self.blade_profiles))
        self.blade_choice.set("Current blade")
        self.blade_choice.pack(fill=tk.X)
        self.blade_choice.bind("<<ComboboxSelected>>", self.choose_blade)
        workflow.button(row, 'Save preset…', self.save_blade).pack(anchor='e', pady=8)
        tk.Checkbutton(p, text="Compensate for the swivelling blade", variable=self.compensation,
                       bg=PANEL, fg=INK, activebackground=PANEL, selectcolor=PANEL,
                       font=("DejaVu Sans", 12), pady=8).pack(anchor="w")
        self.field(p, "mat_knife_offset", "Blade offset", "mm", "Use the offset specified for your blade holder.")
        self.field(p, "mat_overcut", "Close cuts with an overcut", "mm", "Continue along a closed outline to help its ends separate.")
        self.text(p, "Test circle and triangle corners to check offset; check joined ends for overcut. Enable for original outlines, not files already compensated for a drag knife.", muted=True).pack(fill=tk.X, pady=8)

        p = self.pages["Mat"]
        self.field(p, "mat_width", "Mat width", "mm")
        self.field(p, "mat_height", "Mat height", "mm")
        self.field(p, "mat_load_distance", "Automatic loading distance", "mm", "Used only by the grblHAL automatic loader.")
        self.text(p, "Changing mat dimensions or loading distance requires you to confirm the mat position again.", muted=True).pack(fill=tk.X, pady=8)

        self.text(p, 'Mat origin · lower-left corner', bold=True).pack(anchor='w', pady=(16, 8))
        diagram = tk.Canvas(p, height=130, bg=PANEL, highlightthickness=0)
        diagram.pack(fill='x')
        diagram.create_rectangle(40, 10, 180, 105, outline=ACCENT, width=2)
        diagram.create_oval(35, 100, 45, 110, fill=ACCENT, outline=ACCENT)
        diagram.create_text(70, 118, text='X →', fill=INK)
        diagram.create_text(22, 70, text='Y ↑', fill=INK)
        self.loading_preference = tk.StringVar(self, Utils.getStr('Plotter', 'load_mode', 'auto'))
        self.text(p, 'Loading method', bold=True).pack(anchor='w', pady=8)
        from PlotterUI import ChoiceButton
        for label, value in [('Automatic (detect loader)', 'auto'), ('Manual positioning', 'manual')]:
            ChoiceButton(p, text=label, variable=self.loading_preference, value=value).pack(fill='x', pady=4)

        from PlotterAdvanced import AdvancedPanel
        self.advanced = AdvancedPanel(self, self.pages['Advanced'])
        style = ttk.Style(self)
        style.layout('FoilFlat.TNotebook.Tab', [])
        self.advanced.notebook.configure(style='FoilFlat.TNotebook', height=390)
        p = self.advanced.pages['Job G-code']
        self.text(p, 'Job G-code · before and after the artwork', bold=True).pack(anchor='w')
        self.text(p, 'Apply edits this job. Pressure and speed settings also apply when cutting.', muted=True).pack(fill=tk.X, pady=(6, 8))
        self.gcode_editors = {}
        self.code_transaction = JobCodeTransaction(self.app.gcode)
        self.original_job_code = self.code_transaction.original
        for name in ('Header', 'Footer'):
            value = self.original_job_code[name]
            self.text(p, name + (' · runs first' if name == 'Header' else ' · runs last'), bold=True).pack(anchor='w', pady=(6, 4))
            frame = tk.Frame(p, bg=PANEL)
            frame.pack(fill=tk.X)
            frame.columnconfigure(0, weight=1)
            editor = tk.Text(frame, height=3, width=50, undo=True, wrap='none', font=('DejaVu Sans Mono', 11),
                             bg=BG, fg=INK, relief=tk.FLAT, padx=8, pady=6)
            editor.insert('1.0', value)
            editor.grid(row=0, column=0, sticky='ew')
            vertical = ttk.Scrollbar(frame, orient='vertical', command=editor.yview)
            vertical.grid(row=0, column=1, sticky='ns')
            horizontal = ttk.Scrollbar(frame, orient='horizontal', command=editor.xview)
            horizontal.grid(row=1, column=0, sticky='ew')
            editor.config(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
            self.gcode_editors[name] = editor
        self.save_code_defaults = tk.BooleanVar(self, False)
        tk.Checkbutton(p, text='Also use these as defaults for new designs', variable=self.save_code_defaults,
                       bg=PANEL, fg=INK, activebackground=PANEL, selectcolor=PANEL,
                       font=('DejaVu Sans', 11)).pack(anchor='w', pady=10)

        bottom = tk.Frame(self, bg=PANEL, padx=24, pady=8)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, before=self.scroller)
        feedback = tk.Label(bottom, textvariable=self.error, bg=PANEL, fg="#a52a2a", font=("DejaVu Sans", 11),
                 wraplength=555, anchor="w", justify=tk.LEFT)
        def show_feedback(*args):
            if self.error.get(): feedback.pack(side="top", fill="x", before=self.library_button, pady=(0,8))
            else: feedback.pack_forget()
        self.error.trace_add("write", show_feedback)
        self.library_button = workflow.button(bottom, "Materials & tools…", self.open_library)
        self.library_button.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))
        self.apply_button = workflow.button(bottom, 'Apply settings', self.apply, primary=True)
        self.apply_button.pack(side=tk.RIGHT)
        workflow.button(bottom, "Cancel", self.cancel).pack(side=tk.RIGHT, padx=10)
        self.show_page(page)
        self.update_idletasks()
        x = max(0, self.app.winfo_rootx() + (self.app.winfo_width()-self.winfo_reqwidth())//2)
        y = max(0, self.app.winfo_rooty() + (self.app.winfo_height()-self.winfo_reqheight())//2)
        self.geometry(f"+{x}+{y}")
        self.grab_set()
        self.focus_set()

    def choose_category(self, event=None):
        page, section = self.categories[self.category.get()]
        self.show_page(page)
        if section:
            self.advanced.notebook.select(self.advanced.pages[section])
        self.category.set(next(name for name, target in self.categories.items() if target == (page, section)))
        self.scroller.canvas.yview_moveto(0)
        if section == 'Controller':
            self.apply_button.pack_forget()
        else:
            self.apply_button.pack(side=tk.RIGHT)

    def open_library(self):
        before = dict(self.workflow.blade_profiles)
        child = self.workflow.open_library()
        if child is None:
            return
        child.transient(self)
        self.wait_window(child)
        if not self.winfo_exists():
            return
        # Preserve unsaved blade edits while refreshing profiles changed in the library.
        edited = {name: profile for name, profile in self.blade_profiles.items()
                  if profile != before.get(name)}
        self.blade_profiles = dict(self.workflow.blade_profiles)
        self.blade_profiles.update(edited)
        self.blade_choice.configure(values=['Current blade'] + sorted(self.blade_profiles))
        if self.blade_choice.get() not in self.blade_profiles:
            self.blade_choice.set('Current blade')
        self.grab_set()
        self.focus_set()

    def text(self, parent, text, size=11, bold=False, muted=False):
        return tk.Label(parent, text=text, bg=PANEL, fg=MUTED if muted else INK,
                        font=("DejaVu Sans", size, "bold" if bold else "normal"),
                        justify=tk.LEFT, anchor="w", wraplength=550)

    def field(self, parent, key, title, units, hint=""):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill=tk.X, pady=(6, 8))
        self.text(row, title, bold=True).pack(side=tk.TOP, anchor='w', fill='x', pady=(0, 4))
        self.text(row, units, muted=True).pack(side=tk.RIGHT, padx=(10, 0))
        entry = Field(row, textvariable=self.values[key], width=11, font=("DejaVu Sans", 13),
                         bg=BG, fg=INK, relief=tk.FLAT, highlightthickness=1,
                         highlightbackground="#cedbd5", highlightcolor=ACCENT)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=9)
        self.entries[key] = entry
        if hint:
            self.text(parent, hint, muted=True).pack(fill=tk.X, pady=(0, 8))

    def show_page(self, name):
        for key, panel in self.pages.items():
            panel.pack_forget()
            if key in self.tabs:
                self.tabs[key].config(bg=SOFT if key == name else BG)
        self.pages[name].pack(fill=tk.BOTH, expand=True)
        self.category.set(next(label for label, target in self.categories.items() if target[0] == name))

    def adjust_pressure(self, amount):
        try:
            value = float(self.values["mat_pressure"].get())
            if not math.isfinite(value):
                raise ValueError()
        except ValueError:
            self.error.set("Cutting pressure: enter a number from 0 to 1000.")
            return
        self.values["mat_pressure"].set(f"{min(1000, max(0, value + amount)):g}")
        self.error.set("")

    def choose_blade(self, event=None):
        profile = self.blade_profiles.get(self.blade_choice.get())
        if profile:
            self.values["mat_knife_offset"].set(f"{profile['mat_knife_offset']:g}")
            self.values["mat_overcut"].set(f"{profile['mat_overcut']:g}")
            self.compensation.set(profile["mat_auto_dragknife"])

    def save_blade(self):
        try:
            profile = validate_blade_profile({
                "mat_knife_offset": self.values["mat_knife_offset"].get(),
                "mat_overcut": self.values["mat_overcut"].get(),
                "mat_auto_dragknife": self.compensation.get(),
            })
        except ValueError as error:
            self.error.set(str(error))
            return
        name = simpledialog.askstring("Save blade preset", "Name this tested blade-holder setup:", parent=self)
        if name and name.strip() and name.strip() != "Current blade":
            name = name.strip()
            self.blade_profiles[name] = profile
            self.blade_choice.config(values=["Current blade"] + sorted(self.blade_profiles))
            self.blade_choice.set(name)
            self.error.set("Preset staged. Apply settings to keep it, or Cancel to discard it.")

    def apply(self):
        from PlotterAppearance import save_appearance
        if (self.app.sender.running or self.app.mat_handling.active
                or self.app.tool_sequence.active):
            self.error.set("Wait until cutting, mat handling or the tool sequence finishes before changing settings.")
            return False
        draft = {key: variable.get() for key, variable in self.values.items()}
        draft["mat_auto_dragknife"] = self.compensation.get()
        try:
            validated = validate_settings(draft)
            advanced_values = self.advanced.validate()
            job_code = {name: editor.get('1.0', 'end-1c').replace('\r\n', '\n')
                        for name, editor in self.gcode_editors.items()}
            code_changed = self.code_transaction.validate(job_code)
        except ValueError as error:
            self.error.set(str(error))
            return False
        geometry_changed = any(validated[k] != CNC.vars.get(k) for k in
                               ("mat_width", "mat_height", "mat_load_distance"))
        material_changed = any(validated[k] != CNC.vars.get(k) for k in ("mat_speed", "mat_pressure"))
        from PlotterLibrary import ProfileLibrary
        library = ProfileLibrary(self.workflow.library.snapshot())
        try:
            for name, profile in self.blade_profiles.items():
                existing = library.records['tools'].get(name)
                if existing and existing['kind'] != 'Knife':
                    raise ValueError('A pen already uses this preset name. Choose a different blade name.')
                library.save('tools', dict(existing or {}, name=name, kind='Knife',
                    offset=profile['mat_knife_offset'], overcut=profile['mat_overcut'], compensate=profile['mat_auto_dragknife']), name if existing else None)
        except ValueError as error:
            self.error.set(str(error))
            return False
        save_appearance(self.app, self.appearance.get(), self.density.get())
        self.advanced.apply(advanced_values)
        CNC.vars.update(validated)
        if Utils.getStr('Plotter', 'load_mode', 'auto') != self.loading_preference.get():
            Utils.setStr('Plotter', 'load_mode', self.loading_preference.get())
            self.workflow.loading_mode.current(0 if self.loading_preference.get() == 'auto' else 1)
            self.workflow.confirmed.set(False)
        self.workflow.library = library
        self.workflow.save_library()
        Utils.addSection("Plotter")
        Utils.setStr("Plotter", "blade_profiles", json.dumps(self.blade_profiles))
        if geometry_changed:
            self.workflow.confirmed.set(False)
            self.app.gcode._modified = True  # Mat dimensions are part of the editable project.
        if material_changed:
            self.workflow.material.set("Current settings")
        if code_changed:
            self.code_transaction.commit(job_code)
            self.app.refresh()
            self.workflow.confirmed.set(False)
        if self.save_code_defaults.get():
            for name, text in job_code.items():
                key = name.lower()
                self.app.tools['CNC'][key] = text
                setattr(self.app.gcode, key, text)
            self.app.tools['CNC'].save()
        self.app.saveConfig()
        self.result = True
        self.app.draw()
        self.workflow.update_state()
        self.app.after_idle(self.workflow.fit_mat)
        self.destroy()
        return True

    def cancel(self):
        self.destroy()
