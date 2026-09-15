"""Dedicated machine workspace. Every action uses the shared machine service."""
import tkinter as tk
from PlotterUI import Field
from PlotterPages import WorkspacePage
from tkinter import ttk

from PlotterTheme import PANEL, INK, MUTED
from PlotterUI import ScrollFrame, DANGER, fit_dialog


class MachineWindow(WorkspacePage):
    def __init__(self, workflow):
        super().__init__(workflow.app)
        self.workflow, self.app = workflow, workflow.app
        self.machine = self.app.machine
        self.title('Machine · Foil Studio')
        self.configure(bg=PANEL)
        self.transient(self.app)
        self.pending = None
        self.position = tk.StringVar(self)
        self.error = tk.StringVar(self)
        self.step = tk.StringVar(self, '1')
        self.speed = tk.StringVar(self, '300')
        self.buttons = {}
        header = tk.Frame(self, bg=PANEL, padx=16, pady=12)
        header.pack(fill='x')
        workflow.label(header, 'Machine', size=20, bold=True).pack(side='left')
        workflow.button(header, 'Connection…', workflow.connection_settings).pack(side='right')
        bottom = tk.Frame(self, bg=PANEL, padx=16, pady=12)
        bottom.pack(side='bottom', fill='x')
        stop = workflow.button(bottom, 'Stop movement', lambda: self.action(self.machine.stop_motion))
        stop.configure(fg=DANGER)
        stop.pack(side='left')
        self.buttons['stop'] = stop
        workflow.button(bottom, 'Close', self.destroy).pack(side='right')
        content = ScrollFrame(self)
        content.pack(fill='both', expand=True, padx=16)
        columns = content.body
        left = tk.Frame(columns, bg=PANEL)
        right = tk.Frame(columns, bg=PANEL)
        def reflow(event):
            compact = event.width < 840
            columns.columnconfigure(0, weight=1)
            columns.columnconfigure(1, weight=0 if compact else 1)
            left.grid(row=0, column=0, sticky='nsew', padx=8)
            right.grid(row=1 if compact else 0, column=0 if compact else 1, sticky='nsew', padx=8)
        columns.bind('<Configure>', reflow)
        body = left
        tk.Label(body, textvariable=self.position, bg=PANEL, fg=INK,
                 font=('DejaVu Sans Mono', 12), justify='left').pack(fill='x', pady=12)
        workflow.label(body, 'One tap moves one step. Keep the blade clear.', muted=True).pack(fill='x')
        for label, variable in [('Step · mm', self.step), ('Speed · mm/min', self.speed)]:
            workflow.label(body, label).pack(anchor='w', pady=(8, 4))
            ttk.Entry(body, textvariable=variable).pack(fill='x')
        pad = tk.Frame(body, bg=PANEL)
        pad.pack(pady=12)
        for axis, sign, row, col in [('Y', 1, 0, 1), ('X', -1, 1, 0),
                                     ('X', 1, 1, 2), ('Y', -1, 2, 1)]:
            key = axis + (' +' if sign > 0 else ' −')
            button = workflow.button(pad, key, lambda a=axis, s=sign: self.jog(a, s))
            button.grid(row=row, column=col, padx=4, pady=4, sticky='ew')
            self.buttons[key] = button
        center_stop = workflow.button(pad, 'Stop', lambda: self.action(self.machine.stop_motion))
        center_stop.configure(bg=DANGER, fg='white', minimum_height=56)
        center_stop.grid(row=1, column=1, padx=4, pady=4)
        self.buttons['pad_stop'] = center_stop
        stop.configure(bg=DANGER, fg='white', minimum_height=56)
        body = right
        workflow.label(body, 'Mat positioning', size=16, bold=True).pack(anchor='w', pady=12)
        actions = [('Home machine', self.machine.home), ('Set XY origin', self.machine.origin),
                   ('Release blade', lambda: self.machine.send('M5')),
                   ('Z +', lambda: self.jog('Z', 1)), ('Z −', lambda: self.jog('Z', -1)),
                   ('Reset controller', self.machine.reset), ('Unlock after inspection', self.machine.unlock)]
        for label, command in actions:
            if label == 'Reset controller':
                workflow.label(body, 'Recovery controls', size=16, bold=True).pack(anchor='w', pady=(24, 8))
            button = workflow.button(body, label, lambda c=command: self.action(c))
            button.pack(fill='x', pady=4)
            self.buttons[label] = button
        tk.Label(body, textvariable=self.error, bg=PANEL, fg=DANGER,
                 wraplength=280, justify='left').pack(fill='x', pady=12)
        workflow.label(body, 'Origin changes require a new mat confirmation. Reset discards the current controller job.', muted=True).pack(fill='x')
        self.bind('<Destroy>', self.destroyed, add='+')
        self.bind('<Escape>', lambda e: self.destroy())
        fit_dialog(self, self.app, 460, 740)
        self.poll()

    def action(self, command):
        try:
            result = command()
            self.error.set('')
            self.workflow.update_state()
            return result
        except ValueError as error:
            self.error.set(str(error))
            return False

    def jog(self, axis, sign):
        return self.action(lambda: self.machine.jog(axis, sign, self.step.get(), self.speed.get()))

    def poll(self):
        state = self.machine.snapshot()
        x, y, z = state.position
        self.position.set(f'{state.state}\nX {x:.2f}   Y {y:.2f}\nZ {z:.2f} mm')
        from PlotterPolicy import can_unlock
        for name, button in self.buttons.items():
            enabled = state.ready
            if name in ('stop', 'pad_stop'):
                enabled = state.connected
            elif name == 'Reset controller':
                enabled = state.connected and not state.running
            elif name == 'Unlock after inspection':
                enabled = state.connected and not state.running and can_unlock(state.state)
            elif name == 'Home machine':
                enabled = state.connected and state.identified and not state.running and not state.pending and not state.mpg and state.state in ('Idle', 'ALARM:11', 'Alarm:11')
            button.configure(state='normal' if enabled else 'disabled')
        self.pending = self.after(250, self.poll)

    def destroyed(self, event):
        if event.widget is self and self.pending:
            self.after_cancel(self.pending)
            self.pending = None
