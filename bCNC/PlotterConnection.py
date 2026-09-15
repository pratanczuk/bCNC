"""Connection setup using the existing sender and saved serial configuration."""
import tkinter as tk
from tkinter import ttk
from PlotterTheme import PANEL, INK, MUTED
from PlotterConnections import is_tcp_address


FIRMWARE_LABELS = {'AUTO': 'Automatic (recommended)', 'GRBLHAL': 'grblHAL',
                   'GRBL1': 'GRBL 1.1 compatible', 'GRBL0': 'GRBL 0.8 / 0.9'}


class ConnectionDialog(tk.Toplevel):
    def __init__(self, workflow):
        super().__init__(workflow.app)
        self.previous_grab = self.grab_current()
        self.bind("<Destroy>", self.restore_grab, add="+")
        self.workflow = workflow
        self.app = workflow.app
        self.title('Connect your plotter · Foil Studio')
        self.configure(bg=PANEL, padx=16, pady=12)
        from PlotterUI import ScrollFrame, fit_dialog
        scroller = ScrollFrame(self)
        scroller.pack(fill='both', expand=True)
        body = scroller.body
        self.transient(self.app)
        self.resizable(True, True)
        defaults = self.app.connection.defaults()
        self.port = tk.StringVar(self, defaults.port)
        self.baud = tk.StringVar(self, defaults.baud)
        self.controller = tk.StringVar(self, FIRMWARE_LABELS.get(defaults.controller, defaults.controller))
        self.autoconnect = tk.BooleanVar(self, self.app.connection.autoconnect())
        self.message = tk.StringVar(self)
        tk.Label(body, text='Connect your plotter', bg=PANEL, fg=INK,
                 font=('DejaVu Sans', 20, 'bold')).pack(anchor='w')
        tk.Label(body, text='Power on your plotter. Choose a USB port or enter its TCP address.',
                 bg=PANEL, fg=MUTED, wraplength=500, justify='left').pack(anchor='w', pady=12)
        for title, variable, values in [('USB port or TCP address', self.port, []),
                ('Baud rate', self.baud, ['115200', '57600', '38400', '9600']),
                ('Firmware', self.controller, list(FIRMWARE_LABELS.values()))]:
            tk.Label(body, text=title, bg=PANEL, fg=INK).pack(anchor='w', pady=(10, 4))
            combo = ttk.Combobox(body, textvariable=variable, values=values, width=48,
                                style='Foil.TCombobox', state='readonly' if variable is self.controller else 'normal')
            combo.pack(fill='x')
            if variable is self.port:
                self.ports = combo
            elif variable is self.baud:
                self.baud_combo = combo
        workflow.button(body, 'Refresh serial ports', self.refresh).pack(anchor='w', pady=10)
        tk.Label(body, text='TCP examples: socket://plotter.local:8888\nor socket://192.168.1.50:8888\nUse the hostname or IP address and TCP port configured on your plotter.\nAutomatic detection supports GRBL 0.8/0.9, 1.0/1.1 and grblHAL. Manual profiles are troubleshooting overrides.',
                 bg=PANEL, fg=MUTED, wraplength=500, justify='left').pack(anchor='w')
        self.transport_hint = tk.StringVar(self)
        tk.Label(body, textvariable=self.transport_hint, bg=PANEL, fg=MUTED,
                 wraplength=500, justify='left').pack(fill='x', pady=(10,0))
        self.port.trace_add('write', self.update_transport)
        self.update_transport()
        self.autoconnect_check = tk.Checkbutton(
            body, text='Automatically connect on startup', variable=self.autoconnect,
            command=self.change_autoconnect, bg=PANEL, fg=INK, activebackground=PANEL,
            selectcolor=PANEL, font=('DejaVu Sans', 11), anchor='w')
        self.autoconnect_check.pack(fill='x', pady=(10, 0))
        tk.Label(body, text='Uses your saved serial port or TCP address next time you open Foil Studio.',
                 bg=PANEL, fg=MUTED, wraplength=500, justify='left').pack(anchor='w')
        tk.Label(body, textvariable=self.message, bg=PANEL, fg='#a52a2a',
                 wraplength=500, justify='left').pack(fill='x', pady=12)
        row = tk.Frame(self, bg=PANEL)
        row.pack(side='bottom', fill='x', before=scroller)
        workflow.button(row, 'Connect', self.connect, primary=True).pack(side='right')
        workflow.button(row, 'Close', self.destroy).pack(side='right', padx=8)
        self.bind('<Escape>', lambda event: self.destroy())
        self.refresh()
        fit_dialog(self, self.app, 570, 740)
        self.grab_set()

    def change_autoconnect(self):
        self.app.connection.set_autoconnect(self.autoconnect.get())
        self.message.set('Startup connection enabled.' if self.autoconnect.get()
                         else 'Startup connection disabled. You can connect manually.')

    def update_transport(self, *args):
        tcp = is_tcp_address(self.port.get())
        self.baud_combo.config(state='disabled' if tcp else 'normal')
        self.transport_hint.set('TCP connection · baud rate is not used. The plotter must be reachable on your network.' if tcp
                                else 'USB connection · choose the baud rate used by your firmware.')

    def refresh(self):
        try:
            from serial.tools.list_ports import comports
            values = sorted(p.device for p in comports())
            current = self.port.get().strip()
            if current and current not in values:
                values.insert(0, current)
            self.ports.configure(values=values)
            self.message.set('')
        except Exception as error:
            self.message.set('We couldn’t list serial ports. Check the cable or enter the port manually.')
            self.app.reportPlotterError('Connection scan failed', str(error))

    def connect(self):
        try:
            mode = next((key for key, label in FIRMWARE_LABELS.items() if label == self.controller.get()), self.controller.get())
            connected = self.app.connection.connect(self.port.get(), self.baud.get(), mode)
        except ValueError as error:
            self.message.set(str(error))
            return False
        if not connected:
            self.message.set(self.workflow.notice_title.get() + '\n' + self.workflow.notice_text.get())
            return False
        self.workflow.clear_notice()
        self.workflow.update_state()
        self.destroy()
        return True

    def restore_grab(self, event):
        if event.widget is self and self.previous_grab is not None:
            try:
                if self.previous_grab.winfo_exists():
                    self.previous_grab.grab_set()
            except tk.TclError:
                pass
