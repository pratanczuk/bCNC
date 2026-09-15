"""Application adapters for document, sender and configuration service ports.

Constructed only by bmain. Domain services do not import this module.
"""
from CNC import CNC
from PlotterCompensation import compensate_blocks
from PlotterMachine import MachineSnapshot
from PlotterPlanning import JobParameters
import Utils
from pathlib import Path


class SenderMachinePort:
    def __init__(self, app):
        self.app = app

    def snapshot(self):
        app = self.app
        return MachineSnapshot(
            session=app.sender.serial, controller=app.sender.controller,
            state=CNC.vars.get('state', ''), running=app.sender.running or any(bool(getattr(getattr(app, service, None), 'active', False)) for service in ('mat_handling', 'tool_sequence')),
            pending=not app.sender.queue.empty() or bool(getattr(app.sender, '_sumcline', 0)),
            position=tuple(float(CNC.vars.get(axis) or 0) for axis in ('wx', 'wy', 'wz')),
            units=CNC.vars.get('units', 'G21'), distance=CNC.vars.get('distance', 'G90'),
            feed=CNC.vars.get('feed', 300),
            jog_supported=app.sender.firmware.jog if getattr(app.sender, 'firmware', None) else None,
            position_valid=app.sender.firmware.ready if getattr(app.sender, 'firmware', None) else True,
            identified=app.sender.firmware.identified if getattr(app.sender, 'firmware', None) else True,
            mpg=bool(CNC.vars.get('mpg', False)),
            board=getattr(getattr(app.sender, 'firmware', None), 'board', ''),
            pins=CNC.vars.get('pins', ''),
            status_sequence=getattr(app.sender, '_status_sequence', 0),
            machine_position=tuple(float(CNC.vars.get(axis) or 0) for axis in ('mx','my','mz')),
            job_running=bool(app.sender.running))

    def invalidate_position(self):
        if hasattr(self.app, 'workflow'):
            self.app.workflow.confirmed.set(False)

    def send(self, command):
        self.app.sender.sendGCode(command)

    def clear_queue(self):
        self.app.sender.emptyQueue()

    def cancel_jog(self):
        self.app.sender.serial_write(b'\x85')

    def feed_hold(self):
        self.app.sender.feedHold()

    def reset(self):
        self.app.sender.softReset()

    def home(self):
        self.app.sender.home()

    def unlock(self):
        self.app.sender.unlock()

    def end_program(self):
        self.app.sender.runEnded()

    def stop_job(self):
        self.app.sender.stopRun()

    def settings(self):
        return {key: value for key, value in list(CNC.vars.items())
                if key.startswith('grbl_') and key[5:].isdigit()}

    def setting_metadata(self, key):
        firmware = getattr(self.app.sender, 'firmware', None)
        return firmware.settings.get(int(key[5:]), {}) if firmware and key[5:].isdigit() else {}

    def clear_settings(self):
        for key in list(CNC.vars):
            if key.startswith('grbl_'):
                del CNC.vars[key]

    def request_settings(self):
        self.app.sender.viewSettings()


class DocumentJobPort:
    def __init__(self, app):
        self.app = app

    def blocks(self):
        from PlotterLayers import apply_visibility
        apply_visibility(self.app.gcode)
        return self.app.gcode.blocks

    def parameters(self):
        from PlotterLayers import catalog
        values = CNC.vars
        return JobParameters(
            startup=CNC.startup,
            origin=tuple(values.get(axis, 0) or 0 for axis in ('wx', 'wy', 'wz')),
            width=values.get('mat_width', 0), height=values.get('mat_height', 0),
            speed=values.get('mat_speed', 500), pressure=values.get('mat_pressure', 500),
            compensate=bool(values.get('mat_auto_dragknife', False)),
            knife_offset=values.get('mat_knife_offset', 0.5), overcut=values.get('mat_overcut', 0),
            inner_first=bool(values.get('mat_inner_first',False)),
            processes={layer['name']: layer['process'] for layer in catalog(self.app.gcode) if 'process' in layer},
            tool_pass=self.app.workflow.tool_pass.get(),
            material=self.app.workflow.library.records['materials'].get(self.app.workflow.material.get()))

    def compensate(self, parameters):
        self.blocks()
        blocks = self.app.gcode.blocks
        if parameters.inner_first:
            from PlotterEditing import order_blocks
            blocks = order_blocks(self.app.gcode.blocks)
        return compensate_blocks(blocks, parameters.knife_offset, parameters.speed, parameters.overcut,
                                 safe=CNC.vars['safe'], digits=CNC.digits)

    def running(self):
        return self.app.sender.running

    def start(self):
        return self.app.run()

    def pause(self):
        return self.app.sender.pause()

    def stop(self):
        return self.app.sender.stopRun()


class ApplicationConfigurationStore:
    def __init__(self, app):
        self.app = app

    def read(self):
        tool = self.app.tools['CNC']
        return {key: tool[key] for key, *_ in tool.variables}

    def apply(self, values, language):
        tool = self.app.tools['CNC']
        changed = bool(tool['units']) or any(tool[key] != value for key, value in values.items())
        for key, value in values.items():
            tool[key] = value
        tool['units'] = 0
        tool.update()
        tool.save()
        CNC.loadConfig(Utils.config)
        Utils.setStr(Utils.__prg__, 'language', language)
        if changed:
            self.app.workflow.confirmed.set(False)

    def describe(self, source):
        if source == 'Connection log':
            return (f"Firmware: {self.app.sender.firmware.label if getattr(self.app.sender, 'firmware', None) else 'Disconnected'}\n\n"
                    + self.app.diagnostic_log.text())
        path = Path(Utils.iniUser if source == 'User configuration' else Utils.iniSystem)
        body = path.read_text() if path.exists() else 'No saved user configuration yet. Preferences are written when the application closes.'
        return str(path) + '\n\n' + body


class SenderConnectionPort:
    def __init__(self, app):
        self.app = app

    def busy(self):
        return self.app.sender.running or self.app.sender.serial is not None

    def defaults(self):
        from PlotterConnections import ConnectionOptions
        prefs = self.app.connection_preferences
        return ConnectionOptions(prefs.port, prefs.baud, prefs.controller)

    def autoconnect(self):
        return self.app.connection_preferences.autoconnect

    def set_autoconnect(self, enabled):
        self.app.connection_preferences.autoconnect = bool(enabled)
        self.app.connection_preferences.save()

    def configure(self, options):
        prefs = self.app.connection_preferences
        prefs.port, prefs.baud, prefs.controller = options.port, options.baud, options.controller
        prefs.save()
        self.app.sender.controllerSet('GRBL1' if options.controller in ('AUTO', 'GRBLHAL') else options.controller)

    def invalidate_position(self):
        self.app.workflow.confirmed.set(False)

    def open(self, options):
        return self.app.open(options.port, options.baud)

    def enable(self):
        self.app.enable()
