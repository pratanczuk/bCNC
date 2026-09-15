"""Tool change sequencing with no physical transport."""
from dataclasses import replace
from unittest.mock import patch
import unittest
from test_plotter_services import RecordingPort
from test_plotter_library import artwork, process
from PlotterSequence import ToolSequence, ToolStage, sequence_blocks
from PlotterPlanning import JobParameters
from PlotterCompilation import compile_buffer


class SequencePort(RecordingPort):
    def end_program(self):
        self.events.append('ended')
        self.state=replace(self.state,job_running=False,running=False)


class ToolSequenceTest(unittest.TestCase):
    def setUp(self):
        self.port=SequencePort()
        self.port.state=replace(self.port.state,board='GRBLFilmCut',machine_position=(50,80,0),position=(10,20,0))
        self.sent=[]; self.notices=[]; self.now=0
        def submit(commands):
            self.sent.append(commands)
            self.port.state=replace(self.port.state,job_running=True,running=True)
        self.sequence=ToolSequence(self.port,submit,lambda *args:self.notices.append(args),lambda:self.now)
        self.stages=(ToolStage('Pen · Black',('M5','G1 X5','M5')),ToolStage('Knife · Vinyl',('M5','G1 X10','M5')))

    def ack(self):
        command=self.sequence.command
        if command=='$HX':
            self.port.state=replace(self.port.state,machine_position=(-215,80,0),position=(0,20,0))
        elif 'G92' in command:
            self.port.state=replace(self.port.state,position=(-255,20,0))
        self.sequence.receive('ok')
        self.sequence.tick()
        self.port.state=replace(self.port.state,status_sequence=self.port.state.status_sequence+1)
        self.sequence.tick()

    def home(self):
        self.assertEqual(self.sequence.command,'M5');self.ack()
        self.assertEqual(self.sequence.command,'$HX');self.ack()
        self.assertEqual(self.sequence.command,'G21 G90 G92 X-255.0000 Y20.0000');self.ack()
        self.assertEqual(self.sequence.phase,'waiting')

    def test_homes_before_every_exchange_preserves_origin_and_waits_for_confirmation(self):
        self.sequence.begin(self.stages);self.home()
        self.now+=600;self.sequence.tick()
        self.assertEqual(self.sent,[])
        self.assertIn('Pen · Black',self.sequence.message)
        self.sequence.continue_pass();self.sequence.tick()
        self.assertEqual(self.sent,[self.stages[0].commands])
        with self.assertRaises(ValueError):self.sequence.continue_pass()
        self.port.state=replace(self.port.state,job_running=False,running=False)
        self.sequence.pass_finished();self.home()
        self.assertEqual(len(self.sent),1)
        self.assertIn('Knife · Vinyl',self.sequence.message)
        self.sequence.continue_pass()
        self.port.state=replace(self.port.state,job_running=False,running=False)
        self.sequence.pass_finished()
        self.assertFalse(self.sequence.active)
        self.assertEqual(self.sequence.phase,'complete')
        self.assertEqual(self.port.commands.count('$HX'),2)
        self.assertFalse(any('LOAD_MATERIAL' in command for command in self.port.commands))

    def test_stale_status_and_unconfirmed_restore_cannot_open_tool_prompt(self):
        self.sequence.begin(self.stages)
        self.sequence.receive('ok');self.sequence.tick()
        self.assertEqual(self.port.commands,['M5'])
        self.port.state=replace(self.port.state,status_sequence=1);self.sequence.tick()
        self.ack()
        self.sequence.receive('ok')
        self.port.state=replace(self.port.state,status_sequence=3)
        self.sequence.tick()
        self.assertEqual(self.sequence.phase,'homing')
        self.assertEqual(self.sent,[])
        self.now=46;self.sequence.tick()
        self.assertFalse(self.sequence.active)
        self.assertIn('reset',self.port.events)

    def test_error_alarm_restart_disconnect_and_abort_never_advance(self):
        for failure in ('error:9','ALARM:9','GrblHAL 1.1f',None,'cancel'):
            with self.subTest(failure=failure):
                self.setUp(); self.sequence.begin(self.stages)
                if failure is None:
                    self.port.state=replace(self.port.state,session=None);self.sequence.tick()
                elif failure=='cancel':self.sequence.cancel()
                else:self.sequence.receive(failure)
                self.assertFalse(self.sequence.active)
                self.assertEqual(self.sent,[])
                self.sequence.pass_finished();self.sequence.tick()
                self.assertEqual(self.sent,[])

    def test_external_motion_or_offset_change_during_exchange_cancels(self):
        for change in ({'machine_position':(-214,80,0)}, {'position':(-250,20,0)}, {'state':'Jog'}):
            self.setUp();self.sequence.begin(self.stages);self.home()
            self.port.state=replace(self.port.state,**change)
            self.sequence.tick()
            self.assertFalse(self.sequence.active)
            with self.assertRaises(ValueError):self.sequence.continue_pass()
            self.assertEqual(self.sent,[])

    def test_homing_cannot_move_mat_axis(self):
        self.sequence.begin(self.stages);self.ack()
        self.port.state=replace(self.port.state,machine_position=(50,81,0))
        self.sequence.tick()
        self.assertFalse(self.sequence.active)
        self.assertIn('reset',self.port.events)
        self.assertEqual(self.sent,[])

    def test_cancel_while_waiting_does_not_reset_or_start_a_pass(self):
        self.sequence.begin(self.stages);self.home()
        self.sequence.cancel()
        self.assertFalse(self.sequence.active)
        self.assertEqual(self.port.events,['ended'])
        self.assertEqual(self.sent,[])

    def test_disconnect_during_pass_does_not_home_or_start_next_tool(self):
        self.sequence.begin(self.stages);self.home();self.sequence.continue_pass()
        self.port.state=replace(self.port.state,session=None)
        self.sequence.tick();self.sequence.pass_finished()
        self.assertFalse(self.sequence.active)
        self.assertEqual(len(self.sent),1)
        self.assertNotIn('reset',self.port.events)

    def test_mat_sensor_loss_during_exchange_cancels_remaining_passes(self):
        self.port.state=replace(self.port.state,pins='YZP')
        self.sequence.begin(self.stages);self.home()
        self.port.state=replace(self.port.state,pins='YZ')
        self.sequence.tick()
        self.assertFalse(self.sequence.active)
        self.assertEqual(self.sent,[])
        self.assertIn('mat sensor',self.sequence.message)

    def test_unsupported_controller_rejected_before_motion(self):
        self.port.state=replace(self.port.state,board='Other')
        with self.assertRaises(ValueError):self.sequence.begin(self.stages)
        self.assertEqual(self.port.commands,[])


class SequencePlanningTest(unittest.TestCase):
    def test_pens_first_wrappers_once_and_all_passes_validated_before_motion(self):
        from CNC import Block
        header=Block('Header');header.append('(user header)')
        footer=Block('Footer');footer.extend(['(user footer)','$H'])
        source=[header,artwork('Outline','Cut'),artwork('Label','Draw'),footer]
        params=JobParameters(compensate=True,processes={'Cut':process('Knife','Vinyl'),'Draw':process()})
        planned=sequence_blocks(source,params)
        self.assertEqual([name for name,blocks in planned],['Pen · Fine black','Knife · Vinyl'])
        flat=lambda blocks:[line for block in blocks for line in block]
        self.assertIn('(user header)',flat(planned[0][1]))
        self.assertNotIn('(user header)',flat(planned[1][1]))
        self.assertNotIn('$H',flat(planned[0][1]))
        self.assertIn('$H',flat(planned[1][1]))
        for label,blocks in planned:self.assertTrue(compile_buffer(blocks))
        params=replace(params,width=15)
        with self.assertRaises(ValueError):sequence_blocks(source,params)

    def test_coordinate_changing_header_is_rejected(self):
        from CNC import Block
        header=Block('Header');header.append('G92 X0 Y0')
        source=[header,artwork('A','Cut'),artwork('B','Draw')]
        params=JobParameters(processes={'Cut':process('Knife','Vinyl'),'Draw':process()})
        with self.assertRaisesRegex(ValueError,'fixed job origin'):sequence_blocks(source,params)
