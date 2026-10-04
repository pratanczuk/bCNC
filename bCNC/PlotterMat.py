"""Acknowledged mat-handling transactions; no UI or firmware-global dependencies."""
import math
import time


class MatHandling:
    def __init__(self, port, notify, clock=time.monotonic):
        self.port, self.notify, self.clock = port, notify, clock
        self.active = False
        self.positioned = False
        self.loading = True
        self.steps = []
        self.message = ''
        self.job_ready = None

    def prepare_job(self, on_ready):
        state = self.port.snapshot()
        if self.active or not state.ready:
            raise ValueError('Wait for the plotter to be idle before setting the job origin.')
        if state.board != 'GRBLFilmCut':
            raise ValueError('X-only job-origin preparation requires FilmCut firmware.')
        self.session = state.session
        self.loading = True
        self.positioned = False
        self.job_ready = on_ready
        self.home_y = state.machine_position[1]
        self.steps = [('M5', 'Releasing blade…'), ('$HX', 'Finding the carriage origin…'),
                      ('G21 G54', 'Selecting the job coordinate system…'),
                      ('G10 L20 P1 X0 Y0', 'Confirming the loaded mat origin…')]
        self.active = True
        self.advance()

    def begin(self, loading, distance=20, height=300):
        state = self.port.snapshot()
        if self.active or not state.ready:
            raise ValueError('Connect the plotter and wait until it is idle before handling the mat.')
        if state.board != 'GRBLFilmCut':
            raise ValueError('Automatic loading requires the FilmCut material-loader firmware. Use manual positioning for this plotter.')
        if 'P' not in state.pins:
            raise ValueError('Insert the mat under the rollers until the material sensor detects it, then try again.')
        distance, height = float(distance), float(height)
        if not all(math.isfinite(v) for v in (distance, height)) or not 0 <= distance <= height or not 0 < height <= 2000:
            raise ValueError('Use a loading distance within the mat height (up to 2000 mm).')
        self.loading, self.session = loading, state.session
        self.job_ready = None
        self.travel_limit = height + 60
        action = f'$LOAD_MATERIAL={distance:.3f}' if loading else '$UNLOAD_MATERIAL'
        self.steps = [('M5', 'Releasing blade…'), ('$HX', 'Finding the carriage origin…'),
                      (action, 'Finding the mat edge…' if loading else 'Ejecting the mat…'),
                      ('G92 X0 Y0' if loading else 'G92.1', 'Setting the mat origin…' if loading else 'Clearing the mat origin…')]
        self.positioned = False
        self.active = True
        self.advance()

    def advance(self):
        if not self.steps:
            self.active = False
            self.positioned = self.loading
            callback, self.job_ready = self.job_ready, None
            self.message = ('Job origin confirmed.' if callback is not None else
                'Mat loaded. Check alignment, then confirm its position.' if self.loading else
                'Mat unloaded. Insert it under the rollers before loading again.')
            self.notify(self.message, False)
            if callback is not None:
                callback()
            return
        self.command, self.message = self.steps.pop(0)
        self.ack = self.done = False
        self.started = self.clock()
        state = self.port.snapshot()
        self.y_start = state.position[1]
        self.origin_report = state.work_status_sequence
        self.notify(self.message, False)
        self.port.send(self.command)

    def receive(self, line):
        if not self.active:
            return
        lower = line.lower()
        if lower.startswith(('grbl ', 'grblhal ')):
            self.fail('The plotter restarted during mat handling. Check the mat and load it again when the plotter is ready.\nController: ' + line)
        elif lower.startswith(('error:', 'alarm:')):
            self.fail('Mat handling stopped: ' + line)
        elif self.command.startswith(('$LOAD_MATERIAL', '$UNLOAD_MATERIAL')) and 'material:' in lower:
            if ': done.' in lower:
                self.done = True
            elif any(word in lower for word in ('not found', 'too short', 'no material', 'invalid', 'must be')):
                self.fail('Mat handling stopped: ' + line)
        elif line.strip() == 'ok':
            if self.command.startswith(('$LOAD_MATERIAL', '$UNLOAD_MATERIAL')) and not self.done:
                self.fail('The loader did not confirm completion. Check the mat and sensor before trying again.')
                return
            self.ack = True
            state = self.port.snapshot()
            self.after_status = state.status_sequence
            self.origin_report = state.work_status_sequence

    def tick(self):
        if not self.active:
            return
        state = self.port.snapshot()
        if state.session is not self.session:
            self.fail('The connection changed. Check the mat before reconnecting.')
        elif state.state.startswith(('Alarm', 'ALARM', 'Door', 'Hold')):
            self.fail('Mat handling stopped: ' + state.state)
        elif self.job_ready is not None and abs(state.machine_position[1] - self.home_y) > .05:
            self.fail('The loaded mat moved during X homing. Check alignment before restarting.', stop=True)
        elif self.clock() - self.started > (max(30, self.travel_limit / 10) if 'MATERIAL' in self.command else 45):
            self.fail('Job origin confirmation timed out. Check the plotter status and coordinate offsets.'
                      if self.job_ready is not None else
                      'Mat movement timed out. Check the sensor and rollers.', stop=True)
        elif 'MATERIAL' in self.command and abs(state.position[1] - self.y_start) > self.travel_limit:
            self.fail('The mat moved farther than expected. Check its size and the material sensor.', stop=True)
        elif self.ack and state.status_sequence > self.after_status and state.state == 'Idle' and not state.pending:
            if self.command == 'G10 L20 P1 X0 Y0':
                if state.work_status_sequence <= self.origin_report:
                    return
                if (not state.position_valid or not all(math.isfinite(value) and abs(value) <= .001
                                                       for value in state.position[:2])):
                    self.fail('The controller did not confirm work X0/Y0. Check the coordinate offsets before starting the job.')
                    return
            self.advance()

    def fail(self, message, stop=False):
        self.positioned = False
        self.active = False
        self.steps.clear()
        self.job_ready = None
        self.message = message
        self.port.clear_queue()
        if stop:
            self.port.feed_hold()
            self.port.reset()
        self.notify(message, True)

    def cancel(self):
        if self.active:
            self.fail('Job origin preparation stopped. Check mat alignment before restarting.'
                      if self.job_ready is not None else
                      'Mat movement stopped. Check the mat and reload before cutting.', stop=True)
