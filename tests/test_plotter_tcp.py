"""TCP address validation, friendly failures and a real local socket transport."""
from pathlib import Path
import socket
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
for directory in ('bCNC', 'bCNC/lib', 'bCNC/controllers'):
    sys.path.insert(0, str(ROOT / directory))
import Helpers
from PlotterConnections import ConnectionService, ConnectionOptions
from PlotterErrors import friendly_error


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
