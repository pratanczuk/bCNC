"""Advanced settings and deliberate machine actions for the foil workspace."""
from PlotterUI import AutoScrollbar
import tkinter as tk
from PlotterUI import Field
from tkinter import ttk

import Utils
from PlotterTheme import PANEL, BG, INK, MUTED


from PlotterConfiguration import CONFIG_FIELDS, validate_configuration


class AdvancedPanel:
    def __init__(self, dialog, parent):
        self.dialog, self.app, self.workflow = dialog, dialog.app, dialog.workflow
        self.machine = self.app.machine
        self.machine.clear_edit_session()
        style = ttk.Style(self.app)
        style.configure('Foil.TNotebook', background=PANEL, borderwidth=0)
        style.configure('Foil.TNotebook.Tab', padding=(9, 7), font=('DejaVu Sans', 10), background=BG)
        style.map('Foil.TNotebook.Tab', background=[('selected', '#e2f0ea')], foreground=[('selected', INK)])
        self.notebook = ttk.Notebook(parent, style='Foil.TNotebook')
        self.notebook.pack(fill='both', expand=True)
        self.pages = {}
        for title in ('Job G-code', 'Configuration', 'Controller', 'Machine control', 'System'):
            page = tk.Frame(self.notebook, bg=PANEL, padx=8, pady=8)
            self.notebook.add(page, text=title)
            self.pages[title] = page
        self.values = {}
        self.buttons = {}
        self.config_page()
        self.control_page()
        self.system_page()
        self.poll_id = None
        self.poll()
        dialog.bind('<Destroy>', self.destroyed, add='+')

    def label(self, parent, text, **kw):
        widget = self.dialog.text(parent, text, **kw)
        widget.configure(wraplength=500)
        widget.pack(anchor='w', fill='x', pady=3)
        return widget

    def button(self, parent, label, command):
        button = self.workflow.button(parent, label, lambda: self.action(command))
        self.buttons[label] = button
        return button

    def action(self, command):
        try:
            return command()
        except ValueError as error:
            self.dialog.error.set(str(error))
        except Exception as error:
            from PlotterErrorDialog import show_modal_error
            show_modal_error(self.workflow, self.dialog, 'Machine action could not finish', str(error))

    def scroll_frame(self, parent):
        canvas = tk.Canvas(parent, bg=PANEL, highlightthickness=0)
        scroll = AutoScrollbar(parent, orient='vertical', command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        canvas.config(yscrollcommand=scroll.set)
        frame = tk.Frame(canvas, bg=PANEL)
        item = canvas.create_window(0, 0, window=frame, anchor='nw')
        frame.bind('<Configure>', lambda e: canvas.config(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(item, width=e.width))
        return frame

    def config_page(self):
        page = self.pages['Configuration']
        self.label(page, 'Application configuration · millimeters', bold=True)
        self.label(page, 'These values affect preview and planning. Controller settings below are read from the connected machine.', muted=True)
        local = page
        firmware = self.pages['Controller']
        fields = self.scroll_frame(local)
        config = self.app.configuration.read()
        for key, (title, default, low, high) in CONFIG_FIELDS.items():
            row = tk.Frame(fields, bg=PANEL); row.pack(fill='x', pady=4)
            self.dialog.text(row, title).pack(anchor='w')
            self.values[key] = tk.StringVar(value=str(config[key] if config[key] is not None else default))
            Field(row, textvariable=self.values[key], width=12, bg=BG, fg=INK,
                     relief='flat', font=('DejaVu Sans', 11)).pack(fill='x')
        self.startup = tk.StringVar(value=config['startup'] or 'G90')
        for title, variable in [('Job startup commands', self.startup)]:
            self.label(fields, title)
            Field(fields, textvariable=variable, bg=BG, fg=INK, font=('DejaVu Sans Mono', 11)).pack(fill='x')
        self.label(fields, 'Use Advanced → Job G-code to edit the full header and footer.', muted=True)
        self.button(firmware, 'Read controller settings', self.read_firmware).pack(anchor='w', pady=6)
        self.firmware = ttk.Treeview(firmware, columns=('name', 'value'), show='headings', height=5)
        self.firmware.heading('name', text='Controller setting'); self.firmware.heading('value', text='Current value')
        self.firmware.column('name', width=360); self.firmware.column('value', width=110)
        scroll = AutoScrollbar(firmware, orient='vertical', command=self.firmware.yview)
        scroll.pack(side='right', fill='y'); self.firmware.config(yscrollcommand=scroll.set)
        self.firmware.pack(fill='both', expand=True)
        self.firmware.bind('<<TreeviewSelect>>', lambda event: self.action(self.select_firmware))
        row = tk.Frame(firmware, bg=PANEL); row.pack(fill='x', pady=6)
        self.firmware_value = tk.StringVar()
        Field(row, textvariable=self.firmware_value, width=14, bg=BG, font=('DejaVu Sans', 11)).pack(fill='x')
        self.button(row, 'Send selected setting', self.write_firmware).pack(fill='x', pady=8)
        self.firmware_labels = {key: title for key, typ, default, title, *rest in self.app.tools['Controller'].variables}
        self.label(firmware, 'Sends one selected value immediately. Read again to verify it; Apply settings saves application preferences only.', muted=True)

    def control_page(self):
        page = self.pages['Machine control']
        self.position = tk.StringVar()
        top = tk.Frame(page, bg=PANEL); top.pack(fill='x')
        tk.Label(top, textvariable=self.position, bg=PANEL, fg=INK, font=('DejaVu Sans Mono', 11), anchor='w', justify='left').pack(side='left', pady=3)
        self.button(top, 'Connection…', self.workflow.connection_settings).pack(side='right')
        self.label(page, 'Click once for one movement. Keep the blade clear of the mat.', muted=True)
        row = tk.Frame(page, bg=PANEL); row.pack(fill='x', pady=4)
        self.step = tk.StringVar(value='1'); self.feed = tk.StringVar(value='300')
        self.dialog.text(row, 'Step (mm)').pack(side='left')
        ttk.Combobox(row, textvariable=self.step, values=('0.1', '1', '5', '10'), state='readonly', width=5).pack(side='left', padx=8)
        self.dialog.text(row, 'Speed (mm/min)').pack(side='left')
        Field(row, textvariable=self.feed, width=7, bg=BG, font=('DejaVu Sans', 11)).pack(side='left', padx=8)
        pad = tk.Frame(page, bg=PANEL); pad.pack(pady=0)
        for label, axis, sign, row, col in [('Y +', 'Y', 1, 0, 1), ('X −', 'X', -1, 1, 0), ('X +', 'X', 1, 1, 2), ('Y −', 'Y', -1, 2, 1), ('Z +', 'Z', 1, 0, 3), ('Z −', 'Z', -1, 2, 3)]:
            self.button(pad, label, lambda a=axis, s=sign: self.jog(a, s)).grid(row=row, column=col, padx=5, pady=3, sticky='ew')
        self.button(pad, 'Stop', self.stop_motion).grid(row=1, column=1, padx=5, pady=3)
        row = tk.Frame(page, bg=PANEL); row.pack(fill='x', pady=4)
        for label, command in [('Home machine', self.home), ('Set XY origin', self.origin), ('Release blade', lambda: self.send('M5'))]:
            self.button(row, label, command).pack(side='left', padx=3)
        row = tk.Frame(page, bg=PANEL); row.pack(fill='x')
        self.button(row, 'Reset controller', self.reset).pack(side='left', padx=3)
        self.button(row, 'Unlock after alarm', self.unlock).pack(side='left', padx=3)
        self.label(page, 'Z moves the blade axis. Confirm mat position after manual moves.', muted=True, size=10)

    def idle(self):
        return self.machine.require_idle()

    def send(self, command):
        self.machine.send(command)

    def jog(self, axis, sign):
        self.machine.jog(axis, sign, self.step.get(), self.feed.get())

    def stop_motion(self):
        self.machine.stop_motion()

    def home(self):
        self.machine.home()

    def origin(self):
        self.machine.origin()

    def reset(self):
        self.machine.reset()

    def unlock(self):
        self.machine.unlock()

    def read_firmware(self):
        self.machine.read_settings()
        self.firmware.delete(*self.firmware.get_children())

    def select_firmware(self, event=None):
        selected = self.firmware.selection()
        if selected:
            self.firmware_value.set(str(self.machine.select_setting(selected[0])))
            self.dialog.error.set('Current controller value: ' + self.firmware_value.get() + '. Enter the new value, then Send selected setting.')

    def write_firmware(self):
        self.machine.write_setting(self.firmware_value.get())
        self.dialog.error.set('Setting queued. Read controller settings again to verify the saved value.')

    def system_page(self):
        page = self.pages['System']
        self.label(page, 'System preferences & support', bold=True)
        self.language = tk.StringVar(value=Utils.LANGUAGES.get(Utils.language, Utils.LANGUAGES.get('', '<system>')))
        row = tk.Frame(page, bg=PANEL); row.pack(fill='x', pady=6)
        self.dialog.text(row, 'Language · restart to apply').pack(anchor='w')
        ttk.Combobox(row, textvariable=self.language, values=sorted(Utils.LANGUAGES.values()), state='readonly', width=18).pack(fill='x')
        row = tk.Frame(page, bg=PANEL); row.pack(fill='x', pady=6)
        self.source = tk.StringVar(value='Connection log')
        ttk.Combobox(row, textvariable=self.source, values=('Connection log', 'User configuration', 'System defaults'), state='readonly', width=24).pack(fill='x', pady=8)
        self.button(row, 'Show', self.show_system).pack(side='left', padx=6)
        self.button(row, 'Copy', self.copy_system).pack(side='right')
        self.system_text = tk.Text(page, height=10, wrap='word', bg=BG, fg=INK, font=('DejaVu Sans Mono', 10), relief='flat')
        scroll = AutoScrollbar(page, command=self.system_text.yview)
        scroll.pack(side='right', fill='y'); self.system_text.configure(yscrollcommand=scroll.set)
        self.system_text.pack(fill='both', expand=True)
        self.show_system()

    def show_system(self):
        body = self.app.configuration.describe(self.source.get())
        self.system_text.config(state='normal'); self.system_text.delete('1.0', 'end'); self.system_text.insert('1.0', body); self.system_text.config(state='disabled')

    def copy_system(self):
        self.dialog.clipboard_clear(); self.dialog.clipboard_append(self.system_text.get('1.0', 'end-1c'))

    def validate(self):
        draft = {key: value.get() for key, value in self.values.items()}
        draft.update(startup=self.startup.get())
        return validate_configuration(draft)

    def apply(self, values):
        language = next((key for key, label in Utils.LANGUAGES.items()
                         if label == self.language.get()), '')
        self.app.configuration.apply(values, language)

    def poll(self):
        state = self.machine.snapshot()
        ready = state.ready
        for name in ('X −', 'X +', 'Y −', 'Y +', 'Z −', 'Z +', 'Home machine',
                     'Set XY origin', 'Release blade', 'Read controller settings', 'Send selected setting'):
            self.buttons[name].configure(state='normal' if ready else 'disabled')
        from PlotterPolicy import can_unlock
        connected = state.connected
        home_allowed = (connected and state.identified and not state.running and not state.pending
                        and not state.mpg and state.state in ('Idle', 'ALARM:11', 'Alarm:11'))
        self.buttons['Home machine'].configure(state='normal' if home_allowed else 'disabled')
        self.buttons['Stop'].configure(state='normal' if connected else 'disabled')
        self.buttons['Reset controller'].configure(state='normal' if connected and not state.running else 'disabled')
        self.buttons['Unlock after alarm'].configure(state='normal' if connected and not state.running and can_unlock(state.state) else 'disabled')
        self.buttons['Connection…'].configure(state='disabled' if state.running else 'normal')
        x, y, z = state.position
        self.position.set(f"{state.state}\nX {x:.2f}   Y {y:.2f}   Z {z:.2f}")
        settings = self.machine.settings()
        for key in self.firmware.get_children():
            if key not in settings:
                self.firmware.delete(key)
        for key, value in settings.items():
            firmware = getattr(self.app.sender, 'firmware', None)
            metadata = firmware.settings.get(int(key[5:]), {}) if firmware else {}
            label = metadata.get('name') or self.firmware_labels.get(key, '$' + key[5:])
            values = (label, value)
            if self.firmware.exists(key):
                self.firmware.item(key, values=values)
            else:
                self.firmware.insert('', 'end', iid=key, values=values)
        self.poll_id = self.app.after(250, self.poll)

    def destroyed(self, event):
        if event.widget is self.dialog and self.poll_id:
            self.app.after_cancel(self.poll_id); self.poll_id = None
