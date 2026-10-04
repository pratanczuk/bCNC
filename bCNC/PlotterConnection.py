"""Connection setup using the existing sender and saved serial configuration."""
import tkinter as tk
from queue import Empty, Queue
import threading
from PlotterUI import Field
from PlotterPages import WorkspacePage
from tkinter import ttk
from PlotterTheme import PANEL, INK, MUTED
from PlotterConnections import is_tcp_address
from PlotterBluetooth import BlueZBluetooth, is_bluetooth_address, validate_bluetooth_address


FIRMWARE_LABELS = {'AUTO': 'Automatic (recommended)', 'GRBLHAL': 'grblHAL',
                   'GRBL1': 'GRBL 1.1 compatible', 'GRBL0': 'GRBL 0.8 / 0.9'}


class ConnectionDialog(WorkspacePage):
    def __init__(self, workflow):
        super().__init__(workflow.app)
        self.previous_grab = self.grab_current()
        self.bind("<Destroy>", self.restore_grab, add="+")
        self.workflow = workflow
        self.app = workflow.app
        self.title('Connect your plotter · Foil Studio')
        self.configure(bg=PANEL, padx=16, pady=4)
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
        self.bluetooth_events = Queue()
        self.bluetooth_backend = None
        self.bluetooth_busy = False
        self.bluetooth_devices = {}
        self.bluetooth_poll = None
        self.bluetooth_address = tk.StringVar(self)
        self.bluetooth_channel = tk.StringVar(self, '1')
        self.bluetooth_selection = tk.StringVar(self)
        tk.Label(body, text='Connect your plotter', bg=PANEL, fg=INK,
                 font=('DejaVu Sans', 20, 'bold')).pack(anchor='w')
        tk.Label(body, text='Power on your plotter.',
                 bg=PANEL, fg=MUTED, wraplength=500, justify='left').pack(anchor='w', pady=4)
        self.transport = tk.StringVar(self, 'Network' if is_tcp_address(self.port.get()) else 'Serial port')
        self.host = tk.StringVar(self, 'plotter.local')
        self.network_port = tk.StringVar(self, '8888')
        nav = tk.Frame(body, bg=PANEL); nav.pack(fill='x', pady=8)
        from PlotterUI import ChoiceButton
        for column, name in enumerate(('Serial port', 'Network', 'Bluetooth')):
            nav.columnconfigure(column, weight=1, uniform='transport')
            ChoiceButton(nav, text=name, variable=self.transport, value=name,
                         command=self.choose_transport).grid(row=0, column=column, sticky='ew', padx=2)
        self.serial_form = tk.Frame(body, bg=PANEL)
        self.network_form = tk.Frame(body, bg=PANEL)
        self.bluetooth_form = tk.Frame(body, bg=PANEL)
        for title, variable, values in [('Serial port', self.port, []), ('Baud rate', self.baud, ['115200','57600','38400','9600'])]:
            row = tk.Frame(self.serial_form,bg=PANEL);row.pack(fill='x',pady=3)
            workflow.label(row, title).pack(side='left',padx=(0,12))
            combo = ttk.Combobox(row, textvariable=variable, values=values, style='Foil.TCombobox')
            combo.pack(side='right',fill='x',expand=True)
            if variable is self.port:
                self.ports = combo
            else:
                self.baud_combo = combo
        workflow.button(row, 'Refresh ports', self.refresh).pack(side='right',padx=8)
        for title, variable in [('Host name or IP address', self.host), ('TCP port', self.network_port)]:
            row=tk.Frame(self.network_form,bg=PANEL);row.pack(fill='x',pady=3)
            workflow.label(row,title).pack(side='left',padx=(0,12))
            ttk.Entry(row,textvariable=variable).pack(side='right',fill='x',expand=True)
        workflow.label(self.bluetooth_form, 'Bluetooth device').pack(anchor='w')
        self.bluetooth_combo = ttk.Combobox(self.bluetooth_form, textvariable=self.bluetooth_selection,
            state='readonly', style='Foil.TCombobox')
        self.bluetooth_combo.pack(fill='x', pady=3)
        self.bluetooth_combo.bind('<<ComboboxSelected>>', self.select_bluetooth)
        row = tk.Frame(self.bluetooth_form, bg=PANEL); row.pack(fill='x', pady=3)
        self.bluetooth_scan_button = workflow.button(row, 'Search', self.search_bluetooth)
        self.bluetooth_scan_button.pack(side='left', fill='x', expand=True, padx=(0,4))
        self.bluetooth_pair_button = workflow.button(row, 'Pair', self.pair_bluetooth)
        self.bluetooth_pair_button.pack(side='left', fill='x', expand=True)
        self.bluetooth_cancel_button = workflow.button(self.bluetooth_form, 'Cancel Bluetooth operation', self.cancel_bluetooth)
        for title, variable in [('Device address', self.bluetooth_address), ('SPP channel', self.bluetooth_channel)]:
            workflow.label(self.bluetooth_form, title).pack(anchor='w', pady=(3,0))
            if variable is self.bluetooth_channel:
                ttk.Spinbox(self.bluetooth_form, from_=1, to=30, textvariable=variable, width=5).pack(anchor='w')
            else:
                ttk.Entry(self.bluetooth_form, textvariable=variable).pack(fill='x')
        self.firmware_label = workflow.label(body, 'Firmware')
        self.firmware_label.pack(anchor='w', pady=(4, 2))
        ttk.Combobox(body, textvariable=self.controller, values=list(FIRMWARE_LABELS.values()),
                     state='readonly', style='Foil.TCombobox').pack(fill='x')
        self.transport_hint = tk.StringVar(self)
        tk.Label(body, textvariable=self.transport_hint, bg=PANEL, fg=MUTED,
                 wraplength=500, justify='left').pack(fill='x', pady=(2,0))
        self.port.trace_add('write', self.update_transport)
        self.update_transport()
        self.autoconnect_check = tk.Checkbutton(
            body, text='Automatically connect on startup', variable=self.autoconnect,
            command=self.change_autoconnect, bg=PANEL, fg=INK, activebackground=PANEL,
            selectcolor=PANEL, font=('DejaVu Sans', 11), anchor='w')
        self.autoconnect_check.pack(fill='x', pady=(2, 0))
        feedback = tk.Label(body, textvariable=self.message, bg=PANEL, fg='#a52a2a',
                 wraplength=500, justify='left'); self.message.trace_add('write',lambda *args:feedback.pack(fill='x',pady=4) if self.message.get() else feedback.pack_forget())
        row = tk.Frame(self, bg=PANEL)
        row.pack(side='bottom', fill='x', before=scroller)
        self.disconnect_button = workflow.button(row, 'Disconnect', self.disconnect)
        self.disconnect_button.pack(side='left')
        self.connect_button = workflow.button(row, 'Connect', self.connect, primary=True)
        self.connect_button.pack(side='right')
        workflow.button(row, 'Close', self.destroy).pack(side='right', padx=8)
        self.bind('<Escape>', lambda event: self.destroy())
        self.refresh()
        fit_dialog(self, self.app, 570, 740)
        self.grab_set()
        self.bluetooth_poll = self.after(100, self.poll_bluetooth)
        if self.transport.get() == 'Bluetooth':
            self.start_bluetooth(lambda backend: backend.devices(), 'Loading Bluetooth devices...')

    def change_autoconnect(self):
        self.app.connection.set_autoconnect(self.autoconnect.get())
        self.message.set('Startup connection enabled.' if self.autoconnect.get()
                         else 'Startup connection disabled. You can connect manually.')

    def update_transport(self, *args):
        tcp = is_tcp_address(self.port.get())
        bluetooth = is_bluetooth_address(self.port.get())
        self.transport.set('Bluetooth' if bluetooth else 'Network' if tcp else 'Serial port')
        if bluetooth:
            try:
                address = validate_bluetooth_address(self.port.get()).split('://', 1)[1]
                address, channel = address.rsplit('/', 1)
                self.bluetooth_address.set(address)
                self.bluetooth_channel.set(channel)
            except ValueError:
                pass
        if tcp:
            from urllib.parse import urlsplit
            try:
                address = urlsplit(self.port.get())
                self.host.set(address.hostname or 'plotter.local')
                self.network_port.set(str(address.port or 8888))
            except ValueError:
                self.message.set('Enter a valid host and TCP port.')
        self.serial_form.pack_forget()
        self.network_form.pack_forget()
        self.bluetooth_form.pack_forget()
        (self.bluetooth_form if bluetooth else self.network_form if tcp else self.serial_form).pack(fill='x', before=self.firmware_label)
        self.baud_combo.config(state='disabled' if tcp or bluetooth else 'normal')
        self.transport_hint.set('Bluetooth Classic / SPP' if bluetooth else 'TCP connection · baud rate is not used. The plotter must be reachable on your network.' if tcp
                                else 'Serial connection · choose the baud rate used by your firmware.')

    def choose_transport(self):
        self.cancel_bluetooth()
        if self.transport.get() == 'Bluetooth':
            self.port.set(f'bluetooth://{self.bluetooth_address.get()}/{self.bluetooth_channel.get()}')
            self.start_bluetooth(lambda backend: backend.devices(), 'Loading Bluetooth devices...')
        else:
            self.port.set('socket://' + self.host.get() + ':' + self.network_port.get() if self.transport.get() == 'Network' else '')

    def select_bluetooth(self, event=None):
        device = self.bluetooth_devices.get(self.bluetooth_selection.get())
        if device is not None:
            self.bluetooth_address.set(device.address)
            self.message.set('Device paired.' if device.paired else 'Device not paired.')

    def start_bluetooth(self, action, message):
        if self.bluetooth_busy:
            return False
        if self.app.sender.running or self.app.mat_handling.active or self.app.tool_sequence.active:
            self.message.set('Stop the current job or movement before Bluetooth setup.')
            return False
        backend = BlueZBluetooth()
        self.bluetooth_backend = backend
        self.bluetooth_busy = True
        for button in (self.bluetooth_scan_button, self.bluetooth_pair_button, self.connect_button):
            button.configure(state='disabled')
        self.bluetooth_combo.configure(state='disabled')
        self.bluetooth_cancel_button.pack(fill='x', pady=3)
        self.message.set(message)
        def work():
            try:
                self.bluetooth_events.put(('done', action(backend)))
            except Exception as error:
                self.bluetooth_events.put(('error', str(error)))
        threading.Thread(target=work, daemon=True).start()
        return True

    def search_bluetooth(self):
        return self.start_bluetooth(lambda backend: backend.devices(scan=True), 'Searching for Bluetooth devices...')

    def pair_bluetooth(self):
        address = self.bluetooth_address.get().strip().upper()
        try:
            validate_bluetooth_address(f'bluetooth://{address}/1')
        except ValueError:
            self.message.set('Select a Bluetooth device or enter a valid device address.')
            return False
        return self.start_bluetooth(lambda backend: backend.pair(address,
            lambda kind, message: self.bluetooth_prompt(backend, kind, message)), 'Pairing Bluetooth device...')

    def bluetooth_prompt(self, backend, kind, message):
        request = {'kind': kind, 'message': message, 'ready': threading.Event(), 'result': None, 'backend': backend}
        self.bluetooth_events.put(('prompt', request))
        while not request['ready'].wait(0.1):
            if backend.cancelled.is_set():
                return None
        return request['result']

    def poll_bluetooth(self):
        try:
            while True:
                kind, result = self.bluetooth_events.get_nowait()
                if kind == 'prompt':
                    from tkinter import messagebox, simpledialog
                    try:
                        if not result['backend'].cancelled.is_set():
                            message = f"{self.bluetooth_address.get()}\n{result['message']}"
                            if result['kind'] == 'confirm':
                                result['result'] = messagebox.askyesno('Bluetooth pairing', message, parent=self)
                            elif result['kind'] == 'display':
                                self.message.set(message)
                                result['result'] = True
                            else:
                                result['result'] = simpledialog.askstring('Bluetooth pairing', message, parent=self,
                                    show='*' if result['kind'] == 'pin' else '')
                    finally:
                        result['ready'].set()
                    if not self.winfo_exists():
                        return
                else:
                    self.bluetooth_busy = False
                    self.bluetooth_cancel_button.pack_forget()
                    for button in (self.bluetooth_scan_button, self.bluetooth_pair_button, self.connect_button):
                        button.configure(state='normal')
                    self.bluetooth_combo.configure(state='readonly')
                    if kind == 'error':
                        self.message.set(result)
                    elif not self.bluetooth_backend.cancelled.is_set():
                        names = [device.name for device in result]
                        self.bluetooth_devices = {
                            device.name + (f' ({device.address})' if names.count(device.name) > 1 else '')
                            + (' - paired' if device.paired else ''): device for device in result}
                        self.bluetooth_combo.configure(values=list(self.bluetooth_devices))
                        selected = next((label for label, device in self.bluetooth_devices.items()
                            if device.address == self.bluetooth_address.get().upper()), '')
                        self.bluetooth_selection.set(selected)
                        self.message.set(f'{len(result)} Bluetooth device(s) available.' if result else 'No SPP devices found.')
        except Empty:
            pass
        self.bluetooth_poll = self.after(100, self.poll_bluetooth)

    def cancel_bluetooth(self):
        if self.bluetooth_backend is not None and self.bluetooth_busy:
            self.bluetooth_backend.cancelled.set()
            self.message.set('Cancelling Bluetooth operation...')

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

    def disconnect(self):
        if (self.app.sender.running or self.app.mat_handling.active
                or self.app.tool_sequence.active):
            self.message.set('Stop the current job or movement before disconnecting.')
            return False
        if self.app.sender.serial is None:
            self.message.set('The plotter is already disconnected.')
            return True
        try:
            self.app.close()
        except OSError as error:
            self.message.set(f'Could not disconnect: {error}')
            return False
        self.workflow.confirmed.set(False)
        self.workflow._connection = None  # Intentional disconnect, not a lost connection.
        self.workflow.clear_notice()
        self.workflow.update_state()
        self.message.set('Plotter disconnected. You can change the connection settings.')
        return True

    def connect(self):
        if self.bluetooth_busy:
            self.message.set('Wait for the Bluetooth operation to finish or cancel it.')
            return False
        try:
            if self.transport.get() == 'Bluetooth':
                self.port.set(validate_bluetooth_address(
                    f'bluetooth://{self.bluetooth_address.get().strip()}/{self.bluetooth_channel.get().strip()}'))
            elif self.transport.get() == 'Network':
                host, port = self.host.get().strip(), int(self.network_port.get())
                if not host or any(c.isspace() for c in host) or not 1 <= port <= 65535:
                    raise ValueError('Enter a host and a TCP port from 1 to 65535.')
                if ':' in host and not host.startswith('['):
                    host = '[' + host + ']'
                self.port.set(f'socket://{host}:{port}')
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
        if event.widget is self:
            self.cancel_bluetooth()
            if self.bluetooth_poll is not None:
                self.after_cancel(self.bluetooth_poll)
                self.bluetooth_poll = None
        if event.widget is self and self.previous_grab is not None:
            try:
                if self.previous_grab.winfo_exists():
                    self.previous_grab.grab_set()
            except tk.TclError:
                pass
