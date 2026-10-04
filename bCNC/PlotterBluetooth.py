"""Bluetooth Classic SPP transport using pySerial's socket I/O contract."""
import re
import socket
import sys
import asyncio
from contextlib import suppress
from dataclasses import dataclass
from threading import Event

from serial import SerialException
from serial.urlhandler.protocol_socket import Serial as SocketSerial


SPP_UUID = '00001101-0000-1000-8000-00805f9b34fb'
ADDRESS = re.compile(r'bluetooth://([0-9a-f]{2}(?::[0-9a-f]{2}){5})/([0-9]+)', re.I)


def is_bluetooth_address(device):
    return device.strip().lower().startswith('bluetooth:')


def validate_bluetooth_address(device):
    match = ADDRESS.fullmatch(device.strip())
    if match is None or not 1 <= int(match[2]) <= 30:
        raise ValueError('Use bluetooth://AA:BB:CC:DD:EE:FF/1 with an SPP channel from 1 to 30.')
    return f'bluetooth://{match[1].upper()}/{int(match[2])}'


class BluetoothError(Exception):
    pass


@dataclass(frozen=True)
class BluetoothDevice:
    path: str
    address: str
    name: str
    paired: bool


def bluetooth_devices(objects):
    devices = []
    for path, interfaces in objects.items():
        properties = interfaces.get('org.bluez.Device1')
        if properties is None:
            continue
        values = {key: value.value for key, value in properties.items()}
        services = [value.lower() for value in values.get('UUIDs', [])]
        if (services and SPP_UUID not in services) or values.get('AddressType') == 'random':
            continue
        address = values.get('Address', '')
        try:
            validate_bluetooth_address(f'bluetooth://{address}/1')
        except ValueError:
            continue
        devices.append(BluetoothDevice(path, address.upper(),
            values.get('Alias') or values.get('Name') or address,
            values.get('Paired', False)))
    return sorted(devices, key=lambda device: (not device.paired, device.name.casefold(), device.address))


def pairing_agent(device_path, prompt):
    from dbus_next import DBusError
    from dbus_next.service import ServiceInterface, method

    class Agent(ServiceInterface):
        def __init__(self):
            super().__init__('org.bluez.Agent1')

        async def ask(self, device, kind, message):
            if device != device_path:
                raise DBusError('org.bluez.Error.Rejected', 'Unexpected device.')
            result = await asyncio.get_running_loop().run_in_executor(None, prompt, kind, message)
            if result is None or result is False:
                raise DBusError('org.bluez.Error.Rejected', 'Pairing cancelled.')
            return result

        @method()
        async def RequestPinCode(self, device: 'o') -> 's':
            result = await self.ask(device, 'pin', 'Bluetooth PIN')
            if not isinstance(result, str) or not 1 <= len(result) <= 16:
                raise DBusError('org.bluez.Error.Rejected', 'PIN must contain 1 to 16 characters.')
            return result

        @method()
        async def RequestPasskey(self, device: 'o') -> 'u':
            result = await self.ask(device, 'passkey', 'Bluetooth passkey (0 to 999999)')
            if not str(result).isascii() or not str(result).isdigit() or not 0 <= int(result) <= 999999:
                raise DBusError('org.bluez.Error.Rejected', 'Invalid passkey.')
            return int(result)

        @method()
        async def DisplayPinCode(self, device: 'o', pincode: 's'):
            await self.ask(device, 'display', f'Enter PIN {pincode} on the Bluetooth device.')

        @method()
        async def DisplayPasskey(self, device: 'o', passkey: 'u', entered: 'q'):
            await self.ask(device, 'display', f'Enter code {passkey:06d} on the Bluetooth device ({entered}/6).')

        @method()
        async def RequestConfirmation(self, device: 'o', passkey: 'u'):
            await self.ask(device, 'confirm', f'Confirm Bluetooth code {passkey:06d}')

        @method()
        async def RequestAuthorization(self, device: 'o'):
            await self.ask(device, 'confirm', 'Allow Bluetooth pairing?')

        @method()
        async def AuthorizeService(self, device: 'o', uuid: 's'):
            if uuid.lower() != SPP_UUID or device != device_path:
                raise DBusError('org.bluez.Error.Rejected', 'Only the selected SPP device is allowed.')

        @method()
        def Cancel(self):
            pass

        @method()
        def Release(self):
            pass

    return Agent()


class BlueZBluetooth:
    def __init__(self):
        self.cancelled = Event()
        self.bus = None

    async def call(self, path, interface, member, signature='', body=None, timeout=15):
        from dbus_next import Message, MessageType
        message = Message(destination='org.bluez', path=path, interface=interface,
                          member=member, signature=signature, body=body or [])
        task = asyncio.ensure_future(self.bus.call(message))
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            while not task.done():
                if self.cancelled.is_set():
                    raise BluetoothError('Bluetooth operation cancelled.')
                if asyncio.get_running_loop().time() >= deadline:
                    raise BluetoothError('Bluetooth operation timed out. Check the plotter and try again.')
                await asyncio.wait({task}, timeout=0.1)
            reply = task.result()
            if reply.message_type == MessageType.ERROR:
                raise BluetoothError(f'{reply.error_name}: {reply.body[0] if reply.body else "Bluetooth operation failed."}')
            return reply.body
        finally:
            if not task.done():
                task.cancel()

    async def objects(self):
        return (await self.call('/', 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects'))[0]

    async def run(self, action):
        if sys.platform != 'linux':
            raise BluetoothError('Discovery and pairing require Linux/BlueZ. Pair in system settings and select the Bluetooth serial port on other systems.')
        try:
            from dbus_next import BusType
            from dbus_next.aio import MessageBus
        except ImportError:
            raise BluetoothError('Install the dbus-next Python package to discover and pair Bluetooth devices.') from None
        try:
            self.bus = await asyncio.wait_for(MessageBus(bus_type=BusType.SYSTEM).connect(), 10)
            return await action()
        except OSError as error:
            raise BluetoothError(f'Bluetooth is unavailable. Check the BlueZ service: {error}') from error
        finally:
            if self.bus is not None:
                self.bus.disconnect()
                self.bus = None

    def devices(self, scan=False, duration=10):
        return asyncio.run(self.run(lambda: self.discover(scan, duration)))

    async def discover(self, scan, duration):
        from dbus_next import Variant
        objects = await self.objects()
        if scan:
            adapter = next((path for path, interfaces in objects.items()
                if 'org.bluez.Adapter1' in interfaces and interfaces['org.bluez.Adapter1']['Powered'].value), None)
            if adapter is None:
                raise BluetoothError('No powered Bluetooth adapter. Turn on Bluetooth in system settings.')
            await self.call(adapter, 'org.bluez.Adapter1', 'SetDiscoveryFilter', 'a{sv}', [{'Transport': Variant('s', 'bredr')}])
            await self.call(adapter, 'org.bluez.Adapter1', 'StartDiscovery')
            try:
                deadline = asyncio.get_running_loop().time() + duration
                while asyncio.get_running_loop().time() < deadline:
                    if self.cancelled.is_set():
                        raise BluetoothError('Bluetooth discovery cancelled.')
                    await asyncio.sleep(0.1)
                objects = await self.objects()
            finally:
                from dbus_next import Message
                with suppress(Exception):
                    await asyncio.wait_for(self.bus.call(Message(destination='org.bluez', path=adapter,
                        interface='org.bluez.Adapter1', member='StopDiscovery')), 3)
        return bluetooth_devices(objects)

    def pair(self, address, prompt):
        return asyncio.run(self.run(lambda: self.pair_device(address, prompt)))

    async def pair_device(self, address, prompt):
        from dbus_next import Message, Variant
        devices = bluetooth_devices(await self.objects())
        device = next((device for device in devices if device.address == address.upper()), None)
        if device is None:
            raise BluetoothError('Device not found. Search again with the plotter discoverable.')
        if not device.paired:
            agent_path = '/org/foilstudio/agent'
            agent = pairing_agent(device.path, prompt)
            self.bus.export(agent_path, agent)
            try:
                await self.call('/org/bluez', 'org.bluez.AgentManager1', 'RegisterAgent', 'os', [agent_path, 'KeyboardDisplay'])
                try:
                    await self.call(device.path, 'org.bluez.Device1', 'Pair', timeout=90)
                except BluetoothError:
                    self.cancelled.set()
                    with suppress(Exception):
                        await asyncio.wait_for(self.bus.call(Message(destination='org.bluez', path=device.path,
                            interface='org.bluez.Device1', member='CancelPairing')), 3)
                    raise
            finally:
                with suppress(Exception):
                    await asyncio.wait_for(self.bus.call(Message(destination='org.bluez', path='/org/bluez',
                        interface='org.bluez.AgentManager1', member='UnregisterAgent', signature='o', body=[agent_path])), 3)
                self.bus.unexport(agent_path)
        await self.call(device.path, 'org.freedesktop.DBus.Properties', 'Set', 'ssv',
                        ['org.bluez.Device1', 'Trusted', Variant('b', True)])
        return bluetooth_devices(await self.objects())


class BluetoothSerial(SocketSerial):
    def read(self, size=1):
        try:
            return super().read(size)
        except SerialException as error:
            raise SerialException(f'Bluetooth SPP: {error}') from error

    def write(self, data):
        try:
            return super().write(data)
        except SerialException as error:
            raise SerialException(f'Bluetooth SPP: {error}') from error

    def open(self):
        self.logger = None
        if self.is_open:
            raise SerialException('Port is already open.')
        self._socket = None
        if sys.platform != 'linux' or not hasattr(socket, 'AF_BLUETOOTH'):
            raise SerialException('Bluetooth SPP requires Linux/BlueZ. On other systems, pair in system settings and select the Bluetooth serial port.')
        try:
            address = validate_bluetooth_address(self.portstr)
            match = ADDRESS.fullmatch(address)
            self._socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self._socket.settimeout(10)
            self._socket.connect((match[1], int(match[2])))
            self._socket.setblocking(False)
            self.is_open = True
        except (OSError, ValueError) as error:
            if self._socket is not None:
                self._socket.close()
                self._socket = None
            raise SerialException(f'Could not open Bluetooth SPP port {self.portstr}: {error}') from error