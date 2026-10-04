"""Mat transactions must prove homing and loader success before setting origin."""
from dataclasses import replace
import unittest
from test_plotter_services import RecordingPort
from PlotterMat import MatHandling

class OriginPort(RecordingPort):
    def __init__(self, home_x, g92, ignore_origin=False):
        super().__init__()
        self.home_x, self.g92, self.ignore_origin = home_x, g92, ignore_origin
        self.offsets = {'G54': (0, 0), 'G55': (25, 50)}
        self.system = 'G55'
        self.state = replace(self.state, board='GRBLFilmCut', pins='P', machine_position=(0, -73, 0))
        self.update_position()

    def update_position(self):
        position = tuple(machine - offset - temporary for machine, offset, temporary
            in zip(self.state.machine_position, self.offsets[self.system], self.g92)) + (0,)
        self.state = replace(self.state, position=position)

    def send(self, command):
        super().send(command)
        if command == '$HX':
            self.state = replace(self.state, machine_position=(self.home_x, -73, 0))
        elif command == 'G21 G54':
            self.system = 'G54'
        elif command == 'G10 L20 P1 X0 Y0' and not self.ignore_origin:
            self.offsets['G54'] = tuple(machine - temporary
                for machine, temporary in zip(self.state.machine_position, self.g92))
        self.update_position()


class MatHandlingTest(unittest.TestCase):
    def setUp(self):
        self.port = RecordingPort()
        self.port.state = replace(self.port.state, board='GRBLFilmCut', pins='YZP')
        self.notices = []
        self.now = 0
        self.mat = MatHandling(self.port, lambda *args: self.notices.append(args), lambda: self.now)

    def ack(self):
        self.mat.receive('ok')
        self.mat.tick()
        self.port.state = replace(self.port.state, status_sequence=self.port.state.status_sequence + 1)
        self.mat.tick()

    def test_load_and_unload_home_before_moving(self):
        for loading in (True, False):
            self.port.commands.clear()
            self.mat.begin(loading)
            self.assertEqual(self.port.commands, ['M5'])
            self.assertFalse(self.mat.positioned)
            self.ack()
            self.assertEqual(self.port.commands[-1], '$HX')
            self.ack()
            self.assertEqual(self.port.commands[-1], '$LOAD_MATERIAL=20.000' if loading else '$UNLOAD_MATERIAL')
            self.mat.receive('[MSG:' + ('LOAD' if loading else 'UNLOAD') + '_MATERIAL: done. material moved]')
            self.ack()
            self.assertEqual(self.port.commands[-1], 'G92 X0 Y0' if loading else 'G92.1')
            self.ack()
            self.assertFalse(self.mat.active)
            self.assertEqual(self.mat.positioned, loading)
            self.assertFalse(self.notices[-1][1])

    def test_fresh_idle_required(self):
        self.mat.begin(True)
        self.mat.receive('ok')
        self.mat.tick()
        self.assertEqual(self.port.commands, ['M5'])
        self.port.state = replace(self.port.state, state='Home', status_sequence=1)
        self.mat.tick()
        self.assertEqual(self.port.commands, ['M5'])
        self.port.state = replace(self.port.state, state='Idle', status_sequence=2)
        self.mat.tick()
        self.assertEqual(self.port.commands[-1], '$HX')

    def test_warning_and_ok_never_set_origin(self):
        for result in ('[MSG:LOAD_MATERIAL: material too short]', 'ok', 'error:9', 'ALARM:4'):
            self.mat.begin(True)
            self.ack(); self.ack()
            self.mat.receive(result)
            self.mat.receive('ok')
            self.mat.tick()
            self.assertFalse(self.mat.active)
            self.assertTrue(self.notices[-1][1])
            self.assertNotIn('G92 X0 Y0', self.port.commands)

    def test_sensor_and_firmware_required(self):
        for fields in ({'pins': 'YZ'}, {'board': 'Other'}):
            initial = self.port.state
            self.port.state = replace(initial, **fields)
            with self.assertRaises(ValueError): self.mat.begin(True)
            self.assertFalse(self.port.commands)
            self.port.state = initial

    def test_timeout_travel_guard_and_cancel_stop(self):
        for cause in ('timeout', 'travel', 'cancel'):
            self.mat.begin(True)
            self.ack(); self.ack()
            if cause == 'timeout': self.now += 100
            elif cause == 'travel': self.port.state = replace(self.port.state, position=(0, -400, 0))
            else: self.mat.cancel()
            self.mat.tick()
            self.assertFalse(self.mat.active)
            self.assertEqual(self.port.events[-2:], ['hold', 'reset'])
            self.port.state = replace(self.port.state, position=(0, 0, 0))

    def test_unexpected_restart_stops_without_retry_and_explains_recovery(self):
        from PlotterErrors import friendly_error
        self.mat.begin(False)
        self.ack()
        self.mat.receive("GrblHAL 1.1f ['$' or '$HELP' for help]")
        self.mat.receive('ok'); self.mat.tick()
        self.assertFalse(self.mat.active)
        self.assertFalse(self.mat.positioned)
        self.assertEqual(self.port.commands, [])
        self.assertEqual(self.port.events, [])
        title, message, action, target = friendly_error('Mat needs attention', self.mat.message)
        self.assertEqual(title, 'The plotter restarted')
        self.assertIn('load it again', message)
        self.assertNotIn('cover', message)
        self.assertIn('GrblHAL', self.mat.message)

    def test_connection_change_aborts(self):
        self.mat.begin(True)
        self.port.state = replace(self.port.state, session=None)
        self.mat.tick()
        self.assertFalse(self.mat.active)
        self.assertTrue(self.notices[-1][1])

    def prepare_origin_write(self, home_x=-215):
        from unittest.mock import Mock
        callback = Mock()
        self.port.state = replace(self.port.state, machine_position=(0, -73, 0), position=(215, 0, 0))
        self.mat.prepare_job(callback)
        self.ack()
        self.assertEqual(self.port.commands[-1], '$HX')
        self.port.state = replace(self.port.state, machine_position=(home_x, -73, 0), position=(home_x, -73, 0))
        self.ack()
        self.assertEqual(self.port.commands[-1], 'G21 G54')
        self.ack()
        self.assertEqual(self.port.commands[-1], 'G10 L20 P1 X0 Y0')
        callback.assert_not_called()
        return callback

    def test_job_origin_waits_for_homing_idle_without_reloading_mat(self):
        from unittest.mock import Mock
        callback = Mock()
        self.mat.prepare_job(callback)
        self.ack()
        self.mat.receive('ok')
        self.port.state = replace(self.port.state, state='Home', status_sequence=2)
        self.mat.tick()
        self.assertEqual(self.port.commands, ['M5', '$HX'])
        self.port.state = replace(self.port.state, state='Idle', status_sequence=3)
        self.mat.tick()
        self.assertEqual(self.port.commands[-1], 'G21 G54')
        self.assertFalse(any('MATERIAL' in command for command in self.port.commands))
        callback.assert_not_called()

    def test_job_origin_accepts_different_homing_positions_only_after_fresh_zero_report(self):
        for home_x in (-215, -198.5, 0):
            with self.subTest(home_x=home_x):
                callback = self.prepare_origin_write(home_x)
                self.mat.receive('ok')
                self.port.state = replace(self.port.state, position=(0, 0, 0),
                    status_sequence=self.port.state.status_sequence + 1)
                self.mat.tick()
                callback.assert_not_called()
                self.port.state = replace(self.port.state, work_status_sequence=self.port.state.work_status_sequence + 1)
                self.mat.tick()
                callback.assert_called_once()
                self.assertFalse(self.mat.active)
                self.assertEqual(self.port.state.machine_position, (home_x, -73, 0))

    def test_ignored_origin_write_or_retained_offset_blocks_job(self):
        for work in ((-215, -73, 0), (5, 0, 0), (0, -7, 0), (float('nan'), 0, 0)):
            with self.subTest(work=work):
                callback = self.prepare_origin_write()
                self.mat.receive('ok')
                self.port.state = replace(self.port.state, position=work,
                    status_sequence=self.port.state.status_sequence + 1,
                    work_status_sequence=self.port.state.work_status_sequence + 1)
                self.mat.tick()
                self.assertFalse(self.mat.active)
                self.assertFalse(self.mat.positioned)
                callback.assert_not_called()
                self.assertIn('did not confirm work X0/Y0', self.notices[-1][0])

    def test_origin_acknowledgement_or_missing_report_never_starts_job(self):
        callback = self.prepare_origin_write()
        self.mat.receive('ok')
        self.mat.tick()
        callback.assert_not_called()
        self.now += 46
        self.mat.tick()
        self.assertFalse(self.mat.active)
        callback.assert_not_called()

    def test_g54_origin_compensates_retained_g92_without_moving_loaded_mat(self):
        from unittest.mock import Mock
        for home_x in (-215, -198.5):
            for g92 in ((0, 0), (5, -7)):
                with self.subTest(home_x=home_x, g92=g92):
                    self.port = OriginPort(home_x, g92)
                    self.mat.port = self.port
                    callback = Mock()
                    self.mat.prepare_job(callback)
                    self.ack(); self.ack(); self.ack()
                    self.mat.receive('ok')
                    self.port.state = replace(self.port.state,
                        status_sequence=self.port.state.status_sequence + 1,
                        work_status_sequence=self.port.state.status_sequence + 1)
                    self.mat.tick()
                    callback.assert_called_once()
                    self.assertEqual(self.port.system, 'G54')
                    self.assertEqual(self.port.g92, g92)
                    self.assertEqual(self.port.state.position[:2], (0, 0))
                    self.assertEqual(self.port.state.machine_position[1], -73)
                    effective_x_offset = self.port.offsets['G54'][0] + g92[0]
                    self.assertEqual(tuple(work_x + effective_x_offset for work_x in (18, 42)),
                                     (home_x + 18, home_x + 42))
                    self.assertFalse(any('MATERIAL' in command for command in self.port.commands))

    def test_controller_ignoring_g10_cannot_start_job_despite_ok(self):
        from unittest.mock import Mock
        self.port = OriginPort(-215, (5, -7), ignore_origin=True)
        self.mat.port = self.port
        callback = Mock()
        self.mat.prepare_job(callback)
        self.ack(); self.ack(); self.ack()
        self.mat.receive('ok')
        self.port.state = replace(self.port.state,
            status_sequence=self.port.state.status_sequence + 1,
            work_status_sequence=self.port.state.status_sequence + 1)
        self.mat.tick()
        callback.assert_not_called()
        self.assertFalse(self.mat.active)
