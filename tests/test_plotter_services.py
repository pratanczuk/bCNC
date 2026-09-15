"""Behavioral service tests: no Tk root, serial device or Application required."""
from dataclasses import replace
from pathlib import Path
import os
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for directory in ('bCNC', 'bCNC/lib'):
    sys.path.insert(0, str(ROOT / directory))
import Helpers
from CNC import Block
from PlotterMachine import MachineService, MachineSnapshot
from PlotterPlanning import JobParameters, prepare_job
from PlotterConfiguration import validate_configuration


class RecordingPort:
    def __init__(self):
        self.state = MachineSnapshot(object(), 'GRBL1', 'Idle', False, False)
        self.commands = []
        self.events = []
        self.values = {}

    def snapshot(self): return self.state
    def send(self, command): self.commands.append(command)
    def clear_queue(self): self.commands.clear()
    def cancel_jog(self): self.events.append('cancel-jog')
    def feed_hold(self): self.events.append('hold')
    def reset(self): self.events.append('reset'); self.values.clear()
    def home(self): self.events.append('home')
    def unlock(self): self.events.append('unlock')
    def stop_job(self): self.events.append('stop-job')
    def invalidate_position(self): self.events.append('invalidate')
    def settings(self): return dict(self.values)
    def clear_settings(self): self.values.clear()
    def request_settings(self): self.commands.append('$$')


class MachineServiceTest(unittest.TestCase):
    def setUp(self):
        self.port = RecordingPort()
        self.machine = MachineService(self.port)

    def test_all_idle_actions_reject_disconnection_motion_and_pending_commands(self):
        actions = [lambda: self.machine.jog('X', 1, 1, 300), self.machine.home,
                   self.machine.origin, lambda: self.machine.send('M5'), self.machine.read_settings]
        idle = self.port.state
        for changes in ({'session': None}, {'running': True}, {'state': 'Alarm'}, {'pending': True}):
            self.port.state = replace(idle, **changes)
            for action in actions:
                with self.subTest(changes=changes, action=action), self.assertRaises(ValueError):
                    action()
        self.assertEqual(self.port.commands, [])
        self.assertEqual(self.port.events, [])

    def test_discovered_capabilities_override_legacy_adapter_name(self):
        self.port.state = replace(self.port.state, jog_supported=False)
        self.machine.jog('X', 1, 1, 300)
        self.assertEqual(self.port.commands, ['G21 G91 G1 X1 F300', 'G21 G90 F300'])
        self.port.commands.clear()
        self.port.state = replace(self.port.state, identified=False)
        with self.assertRaises(ValueError): self.machine.jog('X',1,1,300)
        self.assertEqual(self.port.commands, [])

    def test_grblhal_homing_required_allows_only_deliberate_home(self):
        self.port.state = replace(self.port.state, state='Alarm:11', position_valid=False)
        self.machine.home()
        self.assertEqual(self.port.events, ['invalidate','home'])
        with self.assertRaises(ValueError): self.machine.origin()
        self.port.state = replace(self.port.state, state='Alarm:10')
        with self.assertRaises(ValueError): self.machine.home()

    def test_discovered_setting_metadata_validates_values(self):
        self.port.setting_metadata = lambda key: {'datatype':'5','minimum':'-5','maximum':'20'}
        self.machine.read_settings(); self.port.values['grbl_123']='1'
        self.machine.select_setting('grbl_123')
        for value in ('21', '1.5', 'nan'):
            with self.assertRaises(ValueError): self.machine.write_setting(value)
        self.machine.write_setting('-2')
        self.assertEqual(self.port.commands[-1], '$123=-2')
        self.port.setting_metadata = lambda key: {'datatype':'9'}
        self.machine.select_setting('grbl_123')
        with self.assertRaises(ValueError): self.machine.write_setting('bad host')
        self.machine.write_setting('192.168.1.50')
        self.assertEqual(self.port.commands[-1], '$123=192.168.1.50')

    def test_rejected_jog_does_not_invalidate_position_or_send(self):
        for args in [('XY', 1, 1, 300), ('X', 1, 'nan', 300), ('Z', 1, 20, 300), ('Y', 1, 1, 4000)]:
            with self.subTest(args=args), self.assertRaises(ValueError): self.machine.jog(*args)
        self.assertEqual(self.port.commands + self.port.events, [])
        self.machine.jog('X', -1, '0.1', '250')
        self.assertEqual(self.port.commands, ['$J=G91 G21 X-0.1 F250'])
        self.assertEqual(self.port.events, ['invalidate'])

    def test_stop_routes_to_job_stop_or_controller_jog_cancel(self):
        self.machine.stop_motion()
        self.assertEqual(self.port.events, ['cancel-jog', 'invalidate'])
        self.port.events.clear()
        self.port.state = replace(self.port.state, running=True)
        self.machine.stop_motion()
        self.assertEqual(self.port.events, ['stop-job'])

    def test_firmware_selection_expires_after_reconnect_reset_or_new_editor(self):
        for invalidation in ('reconnect', 'reset', 'editor'):
            self.machine.read_settings()
            self.port.values['grbl_100'] = '250'
            self.machine.select_setting('grbl_100')
            if invalidation == 'reconnect':
                self.port.state = replace(self.port.state, session=object())
            elif invalidation == 'reset':
                self.machine.reset()
            else:
                self.machine.clear_edit_session()
            self.port.commands.clear()
            with self.subTest(invalidation=invalidation), self.assertRaises(ValueError):
                self.machine.write_setting(275)
            self.assertEqual(self.port.commands, [])

    def test_firmware_change_is_not_treated_as_an_acknowledgement(self):
        self.machine.read_settings()
        self.port.values['grbl_100'] = '250'
        self.machine.select_setting('grbl_100')
        self.machine.write_setting('275')
        self.assertEqual(self.port.commands, ['$$', '$100=275'])
        self.assertEqual(self.machine.settings()['grbl_100'], '250')
        with self.assertRaises(ValueError): self.machine.write_setting('300')

    def test_critical_alarm_cannot_be_unlocked(self):
        self.port.state = replace(self.port.state, state='ALARM:10')
        with self.assertRaises(ValueError): self.machine.unlock()
        self.assertEqual(self.port.events, [])
        self.port.state = replace(self.port.state, state='ALARM:3')
        self.machine.unlock()
        self.assertEqual(self.port.events, ['invalidate', 'unlock'])


class PlanningServiceTest(unittest.TestCase):
    def source(self):
        block = Block('Artwork')
        block.extend(['G90', 'G0 X10 Y10', 'G1 X20 Y10 F100', 'M3 S100'])
        return [block]

    def test_preparation_uses_snapshot_and_preserves_source(self):
        blocks = self.source()
        original = list(blocks[0])
        result = prepare_job(blocks, JobParameters(speed=420, pressure=350))
        self.assertEqual(list(blocks[0]), original)
        self.assertIsNot(result[0], blocks[0])
        self.assertTrue(any('420' in line for line in result[0]))
        self.assertTrue(any('350' in line for line in result[0]))

    def test_compensator_receives_snapshot_and_failures_propagate(self):
        settings = JobParameters(compensate=True, knife_offset=0.7, overcut=0.2)
        def compensate(received):
            self.assertIs(received, settings)
            raise RuntimeError('compensation failed')
        with self.assertRaisesRegex(RuntimeError, 'compensation failed'):
            prepare_job(self.source(), settings, compensate)
        with self.assertRaises(ValueError): prepare_job(self.source(), settings)
        with self.assertRaises(ValueError): prepare_job(self.source(), settings, lambda p: None)

    def test_configuration_validation_has_no_live_state_to_mutate(self):
        draft = {'travel_x': '250', 'round': '4', 'startup': 'G90'}
        self.assertEqual(validate_configuration(draft)['travel_x'], 250)
        self.assertEqual(draft['travel_x'], '250')
        for bad in ({'round': 2.5}, {'accuracy': 'nan'}, {'startup': 'G81 Z-2'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): validate_configuration(bad)

    def test_services_and_compiler_do_not_import_presentation_or_adapters(self):
        script = '''
import sys, importlib.abc
class Boundary(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'tkinter', 'Utils', 'MatManager', 'PlotterWorkflow', 'PlotterAdvanced', 'PlotterErrorDialog', 'PlotterAdapters'}:
            raise AssertionError('Forbidden dependency: ' + fullname)
sys.meta_path.insert(0, Boundary())
import Helpers
import PlotterMachine, PlotterEngine, PlotterPlanning, PlotterConfiguration, PlotterErrors, PlotterDocument, PlotterConnections, PlotterCompensation, PlotterPath, PlotterKnife, PlotterShapes
from CNC import GCode, Block
from Sender import Sender
assert not hasattr(Sender, "event_generate")
transport = Sender()
assert transport.serial is None
from queue import Queue
job = GCode()
block = Block('Cut')
block.extend(['G90', 'G0 X10 Y10', 'G1 X20 Y10'])
job.blocks = [block]
queue = Queue()
job.compile(queue)
assert not queue.empty()
'''
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / 'bCNC'), str(ROOT / 'bCNC/lib'), str(ROOT / 'bCNC/controllers')]))
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class DocumentTransactionTest(unittest.TestCase):
    def test_insert_both_job_sections_is_one_undo(self):
        from CNC import GCode
        from PlotterDocument import JobCodeTransaction
        job = GCode()
        source = Block('Artwork'); source.extend(['G0 X10 Y10', 'G1 X20'])
        job.blocks = [source]
        tx = JobCodeTransaction(job)
        self.assertTrue(tx.commit({'Header': 'G90\nG21', 'Footer': 'M5'}))
        self.assertEqual([b.name() for b in job.blocks], ['Header', 'Artwork', 'Footer'])
        job.undo()
        self.assertEqual(job.blocks, [source])

    def test_stale_or_invalid_draft_does_not_modify_job(self):
        from CNC import GCode
        from PlotterDocument import JobCodeTransaction
        job = GCode(); tx = JobCodeTransaction(job)
        for draft in ({'Header': 'G90'}, {'Header': '\x00', 'Footer': 'M5'}):
            with self.assertRaises(ValueError): tx.commit(draft)
            self.assertEqual(job.blocks, [])
        job.blocks.append(Block('New artwork'))
        with self.assertRaisesRegex(ValueError, 'job changed'):
            tx.commit({'Header': 'G90', 'Footer': 'M5'})
        self.assertEqual(len(job.blocks), 1)


class ConnectionServiceTest(unittest.TestCase):
    def test_invalid_busy_and_failed_connections_never_enable(self):
        from unittest.mock import Mock
        from PlotterConnections import ConnectionService, ConnectionOptions
        port = Mock(); port.busy.return_value = False; port.open.return_value = False
        service = ConnectionService(port)
        for args in [('', '115200', 'GRBL1'), ('usb', 'nan', 'GRBL1'), ('usb', 0, 'GRBL1'), ('usb', 115200, 'OTHER')]:
            with self.assertRaises(ValueError): service.connect(*args)
        port.configure.assert_not_called()
        self.assertFalse(service.connect(' usb ', '115200', 'GRBL1'))
        port.open.assert_called_once_with(ConnectionOptions('usb', 115200, 'GRBL1'))
        port.enable.assert_not_called()
        port.busy.return_value = True
        with self.assertRaises(ValueError): service.connect('usb', 115200, 'GRBL1')
        self.assertEqual(port.open.call_count, 1)


class OutlineEffectsTest(unittest.TestCase):
    def rectangle(self, x0=10, y0=10, x1=30, y1=30):
        from shapely.geometry import box
        from PlotterGeometry import geometry_paths
        return geometry_paths(box(x0, y0, x1, y1))

    def test_offset_inset_holes_and_sources(self):
        from PlotterGeometry import outline_effect, outlines_geometry
        paths = self.rectangle() + self.rectangle(15, 15, 25, 25)
        before = outlines_geometry(paths)
        grown = outlines_geometry(outline_effect([paths], 2, rounded=False))
        self.assertEqual(grown.bounds, (8, 8, 32, 32))
        self.assertEqual(len(grown.interiors), 1)
        self.assertGreater(grown.area, before.area)
        smaller = outlines_geometry(outline_effect([paths], -1))
        self.assertLess(smaller.area, before.area)
        self.assertTrue(outlines_geometry(paths).equals(before))

    def test_border_and_invalid_results(self):
        from PlotterGeometry import outline_effect, outlines_geometry
        paths = self.rectangle()
        for actual, expected in zip(outlines_geometry(outline_effect([paths], 3, border=True)).bounds, (7, 7, 33, 33)):
            self.assertAlmostEqual(actual, expected, places=5)
        for distance in ('nan', 'inf', 0, 101, -100):
            with self.subTest(distance=distance), self.assertRaises(ValueError):
                outline_effect([paths], distance)
        with self.assertRaises(ValueError): outline_effect([paths], -1, border=True)
        with self.assertRaises(ValueError): outline_effect([], 2)
