"""Connection lifecycle policy with an injected adapter to the existing sender."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ConnectionOptions:
    port: str
    baud: int
    controller: str


class ConnectionPort(Protocol):
    def busy(self) -> bool: ...
    def defaults(self) -> ConnectionOptions: ...
    def autoconnect(self) -> bool: ...
    def set_autoconnect(self, enabled: bool) -> None: ...
    def configure(self, options: ConnectionOptions) -> None: ...
    def invalidate_position(self) -> None: ...
    def open(self, options: ConnectionOptions) -> bool: ...
    def enable(self) -> None: ...


def is_tcp_address(device):
    return device.strip().lower().startswith('socket:')


def validate_tcp_address(device):
    """Validate the supported raw TCP URL before changing saved connection state."""
    from urllib.parse import urlsplit
    guidance = 'Use socket://hostname:port, for example socket://plotter.local:8888 or socket://192.168.1.50:8888.'
    try:
        parts = urlsplit(device)
        if (not device.lower().startswith('socket://') or not parts.hostname
                or parts.port is None or not 1 <= parts.port <= 65535
                or parts.username is not None or parts.password is not None
                or parts.path or parts.query or parts.fragment
                or any(char.isspace() for char in device)):
            raise ValueError(guidance)
    except ValueError:
        raise ValueError(guidance) from None
    return 'socket://' + device.split('://', 1)[1]


class ConnectionService:
    def __init__(self, port: ConnectionPort):
        self.port = port

    def defaults(self):
        return self.port.defaults()

    def autoconnect(self):
        return self.port.autoconnect()

    def set_autoconnect(self, enabled):
        self.port.set_autoconnect(bool(enabled))

    def connect(self, device, baud, controller):
        if self.port.busy():
            raise ValueError('Disconnect the plotter before changing its connection.')
        device = device.strip()
        if is_tcp_address(device):
            device = validate_tcp_address(device)
            # Raw TCP has no baud setting; retain the serial UI's saved baud value.
            try:
                baud = int(baud)
                if not 0 < baud <= 4000000:
                    baud = 115200
            except (ValueError, TypeError):
                baud = 115200
        else:
            try:
                baud = int(baud)
            except (ValueError, TypeError):
                raise ValueError('Choose a serial port and enter a baud rate from 1 to 4000000.') from None
            if not device or not 0 < baud <= 4000000:
                raise ValueError('Choose a serial port and enter a baud rate from 1 to 4000000.')
        if controller not in ('AUTO', 'GRBL0', 'GRBL1', 'GRBLHAL'):
            raise ValueError('Choose automatic detection or a supported GRBL firmware profile.')
        options = ConnectionOptions(device, baud, controller)
        self.port.configure(options)
        self.port.invalidate_position()
        if not self.port.open(options):
            return False
        self.port.enable()
        return True
