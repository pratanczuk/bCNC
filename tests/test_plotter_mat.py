"""Mat transactions must prove homing and loader success before setting origin."""
from dataclasses import replace
import unittest
from test_plotter_services import RecordingPort
from PlotterMat import MatHandling

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
