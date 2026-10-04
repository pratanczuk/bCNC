"""TCP and Bluetooth address validation, discovery, pairing and socket I/O."""
from pathlib import Path
import asyncio
import socket
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
for directory in ('bCNC', 'bCNC/lib', 'bCNC/controllers'):
    sys.path.insert(0, str(ROOT / directory))
import Helpers
from PlotterConnections import ConnectionService, ConnectionOptions
from PlotterErrors import friendly_error


class BlueZBackendTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from dbus_next import Variant, MessageType
        from PlotterBluetooth import BlueZBluetooth, SPP_UUID
        self.backend = BlueZBluetooth()
        self.objects = {
            '/adapter': {'org.bluez.Adapter1': {'Powered': Variant('b', True)}},
            '/plotter': {'org.bluez.Device1': {
                'Address': Variant('s', 'AA:BB:CC:DD:EE:FF'),
                'UUIDs': Variant('as', [SPP_UUID]), 'Paired': Variant('b', False)}},
        }
        self.backend.objects = AsyncMock(return_value=self.objects)
        self.backend.bus = Mock()
        self.backend.bus.call = AsyncMock(return_value=SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=[]))

    async def test_scan_uses_classic_transport_and_releases_discovery(self):
        devices = await self.backend.discover(True, 0)
        messages = [call.args[0] for call in self.backend.bus.call.await_args_list]
        self.assertEqual([message.member for message in messages], ['SetDiscoveryFilter', 'StartDiscovery', 'StopDiscovery'])
        self.assertEqual(messages[0].body[0]['Transport'].value, 'bredr')
        self.assertEqual(devices[0].address, 'AA:BB:CC:DD:EE:FF')

    async def test_cancelled_scan_stops_its_discovery_session(self):
        from PlotterBluetooth import BluetoothError
        original = self.backend.bus.call.return_value
        async def reply(message):
            if message.member == 'StartDiscovery':
                self.backend.cancelled.set()
            return original
        self.backend.bus.call.side_effect = reply
        with self.assertRaisesRegex(BluetoothError, 'cancelled'):
            await self.backend.discover(True, 10)
        self.assertEqual(self.backend.bus.call.await_args_list[-1].args[0].member, 'StopDiscovery')

    async def test_powered_off_adapter_gives_actionable_error(self):
        from dbus_next import Variant
        from PlotterBluetooth import BluetoothError
        self.objects['/adapter']['org.bluez.Adapter1']['Powered'] = Variant('b', False)
        with self.assertRaisesRegex(BluetoothError, 'Turn on Bluetooth'):
            await self.backend.discover(True, 0)
        self.backend.bus.call.assert_not_awaited()

    async def test_pair_registers_private_agent_and_trusts_only_selected_device(self):
        await self.backend.pair_device('AA:BB:CC:DD:EE:FF', Mock())
        self.backend.bus.export.assert_called_once()
        messages = [call.args[0] for call in self.backend.bus.call.await_args_list]
        self.assertEqual([message.member for message in messages], ['RegisterAgent', 'Pair', 'UnregisterAgent', 'Set'])
        self.assertEqual(messages[1].path, '/plotter')
        self.assertEqual(messages[-1].body[1:], ['Trusted', messages[-1].body[2]])
        self.assertTrue(messages[-1].body[2].value)
        self.backend.bus.unexport.assert_called_once()

    async def test_pair_failure_cancels_pairing_and_unregisters_agent(self):
        from dbus_next import MessageType
        from PlotterBluetooth import BluetoothError
        original = self.backend.bus.call.return_value
        async def reply(message):
            if message.member == 'Pair':
                return SimpleNamespace(message_type=MessageType.ERROR,
                    error_name='org.bluez.Error.AuthenticationFailed', body=['Authentication failed'])
            return original
        self.backend.bus.call.side_effect = reply
        with self.assertRaisesRegex(BluetoothError, 'AuthenticationFailed'):
            await self.backend.pair_device('AA:BB:CC:DD:EE:FF', Mock())
        messages = [call.args[0].member for call in self.backend.bus.call.await_args_list]
        self.assertEqual(messages, ['RegisterAgent', 'Pair', 'CancelPairing', 'UnregisterAgent'])
        self.backend.bus.unexport.assert_called_once()

    async def test_already_paired_device_does_not_pair_again(self):
        from dbus_next import Variant
        self.objects['/plotter']['org.bluez.Device1']['Paired'] = Variant('b', True)
        await self.backend.pair_device('AA:BB:CC:DD:EE:FF', Mock())
        self.backend.bus.export.assert_not_called()
        self.assertEqual(self.backend.bus.call.await_args.args[0].member, 'Set')

    async def test_missing_device_never_registers_agent(self):
        from PlotterBluetooth import BluetoothError
        with self.assertRaisesRegex(BluetoothError, 'Search again'):
            await self.backend.pair_device('AA:BB:CC:DD:EE:00', Mock())
        self.backend.bus.export.assert_not_called()

    async def test_agent_validates_pin_passkey_confirmation_and_service(self):
        from dbus_next import DBusError
        from PlotterBluetooth import pairing_agent, SPP_UUID
        prompt = Mock(return_value='1234')
        agent = pairing_agent('/plotter', prompt)
        async def invoke(name, *args):
            return await getattr(type(agent), name).__wrapped__(agent, *args)
        self.assertEqual(await invoke('RequestPinCode', '/plotter'), '1234')
        self.assertEqual(await invoke('RequestPasskey', '/plotter'), 1234)
        with self.assertRaises(DBusError):
            await invoke('RequestPinCode', '/other')
        for invalid in ('', 'x' * 17, None):
            prompt.return_value = invalid
            with self.assertRaises(DBusError):
                await invoke('RequestPinCode', '/plotter')
        prompt.return_value = '1000000'
        with self.assertRaises(DBusError):
            await invoke('RequestPasskey', '/plotter')
        prompt.return_value = True
        await invoke('RequestConfirmation', '/plotter', 42)
        prompt.assert_called_with('confirm', 'Confirm Bluetooth code 000042')
        await invoke('AuthorizeService', '/plotter', SPP_UUID)
        with self.assertRaises(DBusError):
            await invoke('AuthorizeService', '/plotter', 'unrelated-service')
        prompt.return_value = False
        with self.assertRaises(DBusError):
            await invoke('RequestAuthorization', '/plotter')


class BluetoothConnectionTest(unittest.TestCase):
    def test_bluetooth_errors_never_suggest_usb_or_tcp(self):
        for error in ('Connection refused', 'Permission denied', 'socket disconnected'):
            title, message, _, target = friendly_error('Bluetooth connection failed', error)
            self.assertNotIn('USB', message)
            self.assertNotIn('TCP', message)
            self.assertEqual(target, 'connection')
            self.assertIn('Bluetooth', title)

    def test_discovery_filters_known_non_spp_devices_and_keeps_unknown_devices(self):
        from PlotterBluetooth import bluetooth_devices, SPP_UUID
        def device(address, **properties):
            return {'org.bluez.Device1': {key: SimpleNamespace(value=value)
                for key, value in dict(Address=address, **properties).items()}}
        objects = {
            '/plotter': device('AA:BB:CC:DD:EE:01', Alias='Plotter', UUIDs=[SPP_UUID], Paired=True),
            '/unknown': device('AA:BB:CC:DD:EE:02', Name='HC-05'),
            '/mouse': device('AA:BB:CC:DD:EE:03', UUIDs=['00001124-0000-1000-8000-00805f9b34fb']),
            '/ble': device('AA:BB:CC:DD:EE:04', AddressType='random'),
            '/invalid': device('not a MAC'),
        }
        devices = bluetooth_devices(objects)
        self.assertEqual([device.name for device in devices], ['Plotter', 'HC-05'])
        self.assertTrue(devices[0].paired)
        self.assertFalse(devices[1].paired)

    def test_bluetooth_uses_existing_connection_service_without_baud(self):
        port = Mock(); port.busy.return_value = False; port.open.return_value = True
        self.assertTrue(ConnectionService(port).connect(' BLUETOOTH://aa:bb:cc:dd:ee:ff/01 ', '', 'AUTO'))
        port.open.assert_called_once_with(ConnectionOptions('bluetooth://AA:BB:CC:DD:EE:FF/1', 115200, 'AUTO'))
        port.invalidate_position.assert_called_once()
        port.enable.assert_called_once()

    def test_invalid_bluetooth_addresses_never_change_connection_state(self):
        port = Mock(); port.busy.return_value = False
        for address in ('bluetooth://', 'bluetooth://AA:BB:CC:DD:EE:FF',
                        'bluetooth://AA:BB:CC:DD:EE:FF/0', 'bluetooth://AA:BB:CC:DD:EE:FF/31',
                        'bluetooth://AA:BB:CC:DD:EE:GG/1', 'bluetooth://AA:BB:CC:DD:EE:FF/1?pin=1234'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                ConnectionService(port).connect(address, 115200, 'AUTO')
        port.configure.assert_not_called()
        port.open.assert_not_called()

    def test_spp_preserves_banner_and_exchanges_bytes(self):
        from PlotterBluetooth import BluetoothSerial
        local, remote = socket.socketpair()
        transport = Mock(wraps=local)
        transport.connect = Mock()
        remote.sendall(b'Grbl 1.1h\n')
        try:
            with patch('PlotterBluetooth.socket.socket', return_value=transport), \
                    patch('PlotterBluetooth.sys.platform', 'linux'), \
                    patch('PlotterBluetooth.socket.AF_BLUETOOTH', 31, create=True), \
                    patch('PlotterBluetooth.socket.BTPROTO_RFCOMM', 3, create=True):
                connection = BluetoothSerial('bluetooth://AA:BB:CC:DD:EE:FF/1', timeout=0.05)
            transport.connect.assert_called_once_with(('AA:BB:CC:DD:EE:FF', 1))
            self.assertEqual(connection.readline(), b'Grbl 1.1h\n')
            self.assertEqual(connection.write(b'?'), 1)
            self.assertEqual(remote.recv(1), b'?')
            remote.sendall(b'ok\n')
            self.assertTrue(connection.inWaiting())
            self.assertEqual(connection.readline(), b'ok\n')
            self.assertEqual(connection.read(1), b'')
            connection.close()
            self.assertFalse(connection.is_open)
        finally:
            local.close(); remote.close()

    def test_failed_spp_connection_closes_socket(self):
        from PlotterBluetooth import BluetoothSerial
        from serial import SerialException
        transport = Mock(); transport.connect.side_effect = OSError('Connection refused')
        with patch('PlotterBluetooth.socket.socket', return_value=transport), \
            patch('PlotterBluetooth.sys.platform', 'linux'), \
            patch('PlotterBluetooth.socket.AF_BLUETOOTH', 31, create=True), \
            patch('PlotterBluetooth.socket.BTPROTO_RFCOMM', 3, create=True):
            with self.assertRaisesRegex(SerialException, 'Bluetooth SPP'):
                BluetoothSerial('bluetooth://AA:BB:CC:DD:EE:FF/1')
        transport.close.assert_called_once()


class TCPConnectionTest(unittest.TestCase):
    def test_idle_disconnect_does_not_hold_or_reset_the_plotter(self):
        from Sender import Sender
        from CNC import CNC
        sender = Sender()
        transport = Mock()
        sender.serial = transport
        previous = CNC.vars.get('state')
        CNC.vars['state'] = 'Idle'
        try:
            with patch.object(sender, 'stopRun') as stop, patch('Sender.time.sleep'):
                sender.close()
            stop.assert_not_called()
            transport.write.assert_not_called()
            transport.close.assert_called_once()
        finally:
            CNC.vars['state'] = previous

    def test_hostname_ip_and_ipv6_use_existing_connection_port(self):
        for address in ('socket://plotter.local:8888', 'socket://192.168.1.50:8888', 'socket://[::1]:8888'):
            port = Mock(); port.busy.return_value = False; port.open.return_value = True
            service = ConnectionService(port)
            self.assertTrue(service.connect(address, '57600', 'GRBL1'))
            port.open.assert_called_once_with(ConnectionOptions(address, 57600, 'GRBL1'))
            port.enable.assert_called_once()
            port.invalidate_position.assert_called_once()

    def test_tcp_ignores_invalid_baud_and_normalizes_scheme(self):
        port = Mock(); port.busy.return_value = False; port.open.return_value = True
        self.assertTrue(ConnectionService(port).connect(' SOCKET://plotter.local:8888 ', '', 'GRBL1'))
        port.open.assert_called_once_with(ConnectionOptions('socket://plotter.local:8888', 115200, 'GRBL1'))

    def test_invalid_tcp_urls_never_change_connection_state(self):
        port = Mock(); port.busy.return_value = False
        for address in ('socket://', 'socket://host', 'socket://:8888', 'socket://host:zero',
                        'socket://host:0', 'socket://host:65536', 'socket:/host:8888',
                        'socket://user@host:8888', 'socket://host:8888/path',
                        'socket://host:8888?logging=debug', 'socket://bad host:8888'):
            with self.subTest(address=address), self.assertRaisesRegex(ValueError, 'socket://hostname:port'):
                ConnectionService(port).connect(address, 115200, 'GRBL1')
        port.configure.assert_not_called(); port.open.assert_not_called()

    def test_network_errors_give_network_guidance(self):
        for error, expected in [('Name or service not known', 'IP address'),
                                ('Connection refused', 'TCP service'), ('timed out', 'network'),
                                ('Connection reset by peer', 'confirm the mat')]:
            title, message, _, target = friendly_error('Could not connect', f'socket://plotter.local:8888: {error}')
            self.assertIn(expected, message)
            self.assertNotIn('USB', message)
            self.assertEqual(target, 'connection')

    def test_existing_sender_opens_exchanges_bytes_and_closes_tcp(self):
        from Sender import Sender
        from CNC import CNC
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.settimeout(3)
        address = f'socket://127.0.0.1:{listener.getsockname()[1]}'
        closed = threading.Event()
        errors = []
        def echo():
            try:
                with listener.accept()[0] as client:
                    client.settimeout(3)
                    while True:
                        data = client.recv(1024)
                        if not data:
                            closed.set(); break
                        client.sendall(data)
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=echo, daemon=True); worker.start()
        sender = SimpleNamespace(serial=None, mcontrol=Mock(), serialIO=lambda: None, stopRun=lambda: None)
        sender.serial_write = lambda data: Sender.serial_write(sender, data)
        old_state, old_color = CNC.vars.get('state'), CNC.vars.get('color')
        try:
            with patch('Sender.time.sleep'):
                self.assertTrue(Sender.open(sender, address, 115200))
                sender.serial.timeout = 2
                sender.serial_write('?')
                self.assertTrue(sender.serial.read_until(b'?').endswith(b'?'))
                Sender.close(sender)
            self.assertIsNone(sender.serial)
            self.assertTrue(closed.wait(2))
        finally:
            if sender.serial is not None: sender.serial.close()
            listener.close(); worker.join(3)
            CNC.vars['state'], CNC.vars['color'] = old_state, old_color
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
