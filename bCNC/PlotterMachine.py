"""Machine actions and firmware-edit sessions, independent of Tk and CNC globals."""
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol
import math

from PlotterPolicy import can_unlock


@dataclass(frozen=True)
class MachineSnapshot:
    session: object
    controller: str
    state: str
    running: bool
    pending: bool
    position: tuple = (0.0, 0.0, 0.0)
    units: str = 'G21'
    distance: str = 'G90'
    feed: float = 300.0
    jog_supported: Optional[bool] = None
    identified: bool = True
    position_valid: bool = True
    mpg: bool = False
    board: str = ''
    pins: str = ''
    status_sequence: int = 0
    machine_position: tuple = (0.0, 0.0, 0.0)
    job_running: bool = False

    @property
    def connected(self):
        return self.session is not None

    @property
    def ready(self):
        return self.connected and self.identified and self.position_valid and not self.mpg and not self.running and self.state == 'Idle' and not self.pending


class MachinePort(Protocol):
    """Operations implemented by a sender adapter or a headless test double."""
    def snapshot(self) -> MachineSnapshot: ...
    def send(self, command: str) -> None: ...
    def clear_queue(self) -> None: ...
    def cancel_jog(self) -> None: ...
    def feed_hold(self) -> None: ...
    def reset(self) -> None: ...
    def home(self) -> None: ...
    def unlock(self) -> None: ...
    def stop_job(self) -> None: ...
    def invalidate_position(self) -> None: ...
    def settings(self) -> Mapping[str, str]: ...
    def clear_settings(self) -> None: ...
    def request_settings(self) -> None: ...


class MachineService:
    def __init__(self, port: MachinePort):
        self.port = port
        self._settings_session = None
        self._selection: Optional[tuple] = None

    def clear_edit_session(self):
        self._settings_session = self._selection = None

    def snapshot(self):
        return self.port.snapshot()

    def require_idle(self):
        state = self.snapshot()
        if not state.connected:
            raise ValueError('Connect the plotter first using Connection setup.')
        if not state.identified or not state.position_valid:
            raise ValueError('Wait for firmware identification and position reports.')
        if state.mpg:
            raise ValueError('Release the external controller before moving the plotter.')
        if state.running or state.state != 'Idle':
            raise ValueError('Wait for the plotter to report Idle before this action.')
        if state.pending:
            raise ValueError('Wait for pending machine commands to finish.')
        return state

    def send(self, command):
        self.require_idle()
        self.port.send(command)

    def jog(self, axis, sign, step, feed):
        state = self.require_idle()
        try:
            step, feed = float(step), float(feed)
        except (TypeError, ValueError):
            raise ValueError('Enter a number for movement speed.') from None
        if axis not in ('X', 'Y', 'Z') or sign not in (-1, 1) or not math.isfinite(step + feed) or not 0 < step <= 10 or not 1 <= feed <= 3000:
            raise ValueError('Use a step up to 10 mm and speed from 1 to 3000 mm/min.')
        if state.jog_supported if state.jog_supported is not None else state.controller == 'GRBL1':
            commands = [f'$J=G91 G21 {axis}{sign*step:g} F{feed:g}']
        else:
            if state.units not in ('G20', 'G21') or state.distance not in ('G90', 'G91'):
                raise ValueError('Wait for the controller to report its positioning mode.')
            previous_feed = float(state.feed)
            if not math.isfinite(previous_feed) or previous_feed <= 0:
                previous_feed = feed / 25.4 if state.units == 'G20' else feed
            commands = [f'G21 G91 G1 {axis}{sign*step:g} F{feed:g}',
                        f'{state.units} {state.distance} F{previous_feed:g}']
        self.port.invalidate_position()
        for command in commands:
            self.port.send(command)

    def stop_motion(self):
        state = self.snapshot()
        if state.running:
            self.port.stop_job()
        elif state.connected:
            self.port.clear_queue()
            if state.jog_supported if state.jog_supported is not None else state.controller == 'GRBL1':
                self.port.cancel_jog()
            else:
                self.port.feed_hold()
                self.port.reset()
            self.port.invalidate_position()

    def home(self):
        state = self.snapshot()
        if (not state.connected or not state.identified or state.running or state.pending or state.mpg
                or state.state not in ('Idle', 'ALARM:11', 'Alarm:11')):
            raise ValueError('Connect the plotter and resolve active faults before homing.')
        self.port.invalidate_position()
        self.port.home()

    def origin(self):
        self.require_idle()
        self.port.invalidate_position()
        self.port.send('G92 X0 Y0')

    def reset(self):
        state = self.snapshot()
        if not state.connected:
            raise ValueError('Connect the plotter first.')
        if state.running:
            raise ValueError('Stop the current cut before resetting the controller.')
        self.port.clear_queue()
        self.port.invalidate_position()
        self.port.reset()
        self._settings_session = self._selection = None

    def unlock(self):
        state = self.snapshot()
        if not state.connected or state.running or not can_unlock(state.state):
            raise ValueError('This state does not allow unlocking. Resolve the reported cause first.')
        self.port.invalidate_position()
        self.port.unlock()

    def read_settings(self):
        state = self.require_idle()
        self.port.clear_settings()
        self._selection = None
        self._settings_session = state.session
        self.port.request_settings()

    def settings(self):
        state = self.snapshot()
        if not state.connected or state.session is not self._settings_session:
            return {}
        return dict(self.port.settings())

    def select_setting(self, key):
        values = self.settings()
        if key not in values:
            raise ValueError('Read controller settings and select a value first.')
        self._selection = (key, values[key])
        return values[key]

    def write_setting(self, value):
        state = self.require_idle()
        if state.session is not self._settings_session or self._selection is None:
            raise ValueError('Read controller settings and select a value first.')
        key, old = self._selection
        if self.port.settings().get(key) != old:
            raise ValueError('The controller value changed. Select it again before editing.')
        if not key.startswith('grbl_') or not key[5:].isdigit():
            raise ValueError('Select a numbered controller setting.')
        metadata = self.port.setting_metadata(key) if hasattr(self.port, 'setting_metadata') else {}
        if not isinstance(metadata, dict): metadata = {}
        if metadata.get('datatype') in ('7', '8', '9'):
            value = str(value)
            if len(value) > 100 or any(ord(c) < 32 or ord(c) > 126 for c in value):
                raise ValueError('Use up to 100 printable characters without line breaks.')
            if metadata.get('datatype') == '9':
                import ipaddress
                try: ipaddress.IPv4Address(value)
                except ValueError: raise ValueError('Enter a valid IPv4 address.') from None
        else:
            try: number = float(value)
            except (TypeError, ValueError): raise ValueError('Enter a numeric controller value.') from None
            minimum = float(metadata.get('minimum') or 0)
            maximum = float(metadata.get('maximum') or 'inf')
            if not math.isfinite(number) or not minimum <= number <= maximum:
                raise ValueError('Enter a finite value within the controller setting range.')
            if metadata.get('datatype') in ('0','1','2','3','4','5') and int(number) != number:
                raise ValueError('This controller setting requires a whole number.')
            value = f'{number:g}'
        self.port.invalidate_position()
        self.port.send(f'${int(key[5:])}={value}')
        self._selection = None
