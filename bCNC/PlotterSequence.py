"""Guided physical tool changes: acknowledged X homing and explicit continuation."""
from dataclasses import dataclass, replace
from copy import deepcopy
import time

from CNC import CNC
from PlotterProcesses import tool_passes, ALL_TOOLS
from PlotterPlanning import prepare_job


@dataclass(frozen=True)
class ToolStage:
    label: str
    commands: tuple


def sequence_blocks(blocks, parameters):
    """Plan every pass before motion; use the job header/footer only once."""
    labels = tool_passes(blocks, parameters.processes)
    if parameters.tool_pass not in ('', ALL_TOOLS) or len(labels) < 2:
        return []
    # Draw before cutting loose pieces; preserve appearance order within each type.
    labels.sort(key=lambda label: not label.startswith('Pen · '))
    for line in parameters.startup.splitlines() + [line for block in blocks if block.enable and block.name()=='Header' for line in block]:
        for word in CNC.parseLine(line) or []:
            upper = word.upper()
            if upper.startswith('$') or upper.startswith(('G10','G28','G30','G43','G49','G5','G92')):
                raise ValueError('Guided tool changes need a fixed job origin. Remove homing, work-offset and coordinate-system changes from the startup/header, or run individual tool passes.')
    result = []
    for index, label in enumerate(labels):
        source = deepcopy(blocks)
        for block in source:
            if (block.name()=='Header' and index != 0) or (block.name()=='Footer' and index != len(labels)-1):
                block.enable = False
        prepared = prepare_job(source, replace(parameters, tool_pass=label))
        result.append((label, prepared))
    return result


class ToolSequence:
    def __init__(self, port, submit, notify, clock=time.monotonic):
        self.port, self.submit, self.notify, self.clock = port, submit, notify, clock
        self.active = False
        self.phase = 'idle'
        self.message = ''
        self.stages = ()
        self.index = 0

    def begin(self, stages):
        state = self.port.snapshot()
        if self.active or not state.ready:
            raise ValueError('Wait for the plotter to be connected and idle before starting the tool sequence.')
        if state.board != 'GRBLFilmCut':
            raise ValueError('Guided tool changes currently require FilmCut X-only homing. For this controller, select and run individual tool passes.')
        if len(stages) < 2 or any(not stage.commands for stage in stages):
            raise ValueError('Prepare at least two nonempty tool passes.')
        self.stages, self.index, self.session = tuple(stages), 0, state.session
        self.offset = tuple(m-w for m,w in zip(state.machine_position, state.position))
        self.active = True
        self.home()

    def home(self):
        self.phase = 'homing'
        self.home_y = self.port.snapshot().machine_position[1]
        self.steps = ['M5', '$HX', 'restore']
        self.advance()

    def advance(self):
        if not self.steps:
            self.phase = 'waiting'
            waiting = self.port.snapshot()
            self.wait_position = waiting.machine_position
            self.wait_sensor = 'P' in waiting.pins
            self.message = f'Fit {self.stages[self.index].label} · pass {self.index+1} of {len(self.stages)}. Keep the mat loaded and unchanged. Confirm the tool is fitted and aligned, then continue.'
            self.notify(self.message, False)
            return
        command = self.steps.pop(0)
        state = self.port.snapshot()
        if command == 'restore':
            work = tuple(m-offset for m,offset in zip(state.machine_position,self.offset))
            command = f'G21 G90 G92 X{work[0]:.4f} Y{work[1]:.4f}'
        self.command, self.ack, self.started = command, False, self.clock()
        self.message = f'Releasing tool and homing X for {self.stages[self.index].label}…'
        self.notify(self.message, False)
        self.port.send(command)

    def receive(self, line):
        if not self.active: return
        lower = line.strip().lower()
        if lower.startswith(('error:', 'alarm:', 'grbl ', 'grblhal ')):
            self.fail('Tool sequence interrupted. Check the plotter and mat before starting again.\nController: ' + line, stop=lower.startswith('error:'))
        elif self.phase == 'homing' and lower == 'ok':
            self.ack = True
            self.after_status = self.port.snapshot().status_sequence

    def tick(self):
        if not self.active: return
        state = self.port.snapshot()
        if state.session is not self.session:
            self.fail('The connection changed. The tool sequence was cancelled; check the mat before restarting.')
        elif state.state.lower().startswith(('alarm', 'door')) or state.mpg:
            self.fail('The plotter needs attention. The tool sequence was cancelled; check its position and the mat.', stop=state.state.lower().startswith('door'))
        elif self.phase == 'homing':
            if abs(state.machine_position[1]-self.home_y)>.05:
                self.fail('The mat axis moved during X homing. Check alignment before restarting.', stop=True)
            elif state.state.startswith('Hold') or self.clock()-self.started > 45:
                self.fail('Tool-change homing did not finish. Check the carriage and home switch.', stop=True)
            elif self.ack and state.status_sequence > self.after_status and state.state=='Idle' and not state.pending:
                if self.command.startswith('G21 G90 G92') and any(abs(m-w-offset)>.05 for m,w,offset in zip(state.machine_position,state.position,self.offset)):
                    return
                self.advance()
        elif self.phase == 'waiting':
            if self.wait_sensor and 'P' not in state.pins:
                self.fail('The mat sensor cleared during the tool change. Check the mat and restart the sequence.')
            elif state.state != 'Idle' or any(abs(a-b)>.05 for a,b in zip(state.machine_position,self.wait_position)) or any(abs(m-w-offset)>.05 for m,w,offset in zip(state.machine_position,state.position,self.offset)):
                self.fail('The plotter moved during the tool change. Check alignment and restart the job.', stop=state.state != 'Idle')
        elif self.phase == 'running' and not state.job_running:
            self.fail('The tool pass was interrupted. Check the material before restarting the sequence.', stop=state.state != 'Idle')

    def continue_pass(self):
        state = self.port.snapshot()
        if not self.active or self.phase != 'waiting':
            raise ValueError('Wait for X homing to finish before confirming the tool change.')
        if state.session is not self.session or state.state != 'Idle' or state.pending or not state.identified or not state.position_valid or state.mpg:
            raise ValueError('Wait for the plotter to be ready before continuing.')
        if self.wait_sensor and 'P' not in state.pins:
            self.fail('The mat sensor cleared during the tool change. Check the mat and restart the sequence.')
            return
        if any(abs(a-b)>.05 for a,b in zip(state.machine_position,self.wait_position)) or any(abs(m-w-offset)>.05 for m,w,offset in zip(state.machine_position,state.position,self.offset)):
            self.fail('The carriage or mat moved during the exchange. Check alignment before restarting.')
            return
        self.phase = 'running'
        self.message = f'Running {self.stages[self.index].label} · pass {self.index+1} of {len(self.stages)}'
        self.notify(self.message, False)
        try:
            self.submit(self.stages[self.index].commands)
        except Exception:
            self.fail('The tool pass could not start. Check the plotter before restarting.', stop=True)
            raise

    def pass_finished(self):
        if not self.active or self.phase != 'running': return
        self.index += 1
        if self.index == len(self.stages):
            self.active = False
            self.phase = 'complete'
            self.message = 'All tool passes completed. Check the result before unloading the mat.'
            self.notify(self.message, False)
        else:
            self.home()

    def fail(self, message, stop=False):
        self.active = False
        self.phase = 'cancelled'
        self.message = message
        self.port.clear_queue()
        try:
            if stop and self.port.snapshot().connected:
                self.port.feed_hold()
                self.port.reset()
        finally:
            self.port.end_program()
            self.notify(message, True)

    def cancel(self):
        if self.active:
            self.fail('Tool sequence cancelled. Check the mat and tool before restarting.', stop=self.phase != 'waiting')
