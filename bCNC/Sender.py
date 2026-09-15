# $Id: bCNC.py,v 1.6 2014/10/15 15:04:48 bnv Exp bnv $
#
# Author: Vasilis Vlachoudis
#  Email: vvlachoudis@gmail.com
#   Date: 17-Jun-2015

import os
import re
import sys
import threading
import time
import webbrowser
from datetime import datetime
from queue import (
    Empty,
    Queue,
)

from CNC import CNC, MSG, UPDATE, WAIT, GCode

__author__ = "Vasilis Vlachoudis"
__email__ = "vvlachoudis@gmail.com"

try:
    import serial
except ImportError:
    serial = None

WIKI = "https://github.com/vlachoudis/bCNC/wiki"

SERIAL_POLL = 0.125  # s
SERIAL_TIMEOUT = 0.10  # s
G_POLL = 10  # s
RX_BUFFER_SIZE = 128

FEEDPAT = re.compile(r"^(.*)[fF](\d+\.?\d+)(.*)$")

CONNECTED = "Connected"
NOT_CONNECTED = "Not connected"

STATECOLORDEF = "LightYellow"  # Default color for unknown types?
STATECOLOR = {
    "Idle": "Yellow",
    "Run": "LightGreen",
    "Alarm": "Red",
    "Jog": "Green",
    "Home": "Green",
    "Check": "Magenta2",
    "Sleep": "LightBlue",
    "Hold": "Orange",
    "Hold:0": "Orange",
    "Hold:1": "OrangeRed",
    "Queue": "OrangeRed",
    "Door": "Red",
    "Door:0": "OrangeRed",
    "Door:1": "Red",
    "Door:2": "Red",
    "Door:3": "OrangeRed",
    CONNECTED: "Yellow",
    NOT_CONNECTED: "OrangeRed",
}


# =============================================================================
# bCNC Sender class
# =============================================================================
class Sender:
    # Messages types for log Queue
    MSG_BUFFER = 0  # write to buffer one command
    MSG_SEND = 1  # send message
    MSG_RECEIVE = 2  # receive message from controller
    # ok response from controller, move top most command to terminal
    MSG_OK = 3
    MSG_ERROR = 4  # error message or exception
    MSG_RUNEND = 5  # run ended
    MSG_CLEAR = 6  # clear buffer

    def __init__(self, document=None):
        self.controllers = {}
        self.controllerLoad()
        self.controllerSet("GRBL1")

        self.gcode = document if document is not None else GCode()
        self.firmware = None

        self.log = Queue()  # Log queue returned from GRBL
        self.queue = Queue()  # Command queue to be send to GRBL
        self.serial = None
        self.thread = None

        self._posUpdate = False  # Update position
        self._gUpdate = False  # Update $G
        self._update = None  # Generic update

        self.running = False
        self.runningPrev = None
        self.sio_wait = False
        self.sio_status = False
        self._runLines = 0
        self._gcount = 0
        self._stop = False  # Raise to stop current run
        self._pause = False  # machine is on Hold
        self._alarm = True  # Display alarm message if true
        self._msg = None
        self._sumcline = 0
        self._lastFeed = 0
        self._newFeed = 0


    # ----------------------------------------------------------------------
    def controllerLoad(self):
        from GRBL0 import Controller as GrblLegacyProtocol
        from GRBL1 import Controller as GrblProtocol
        self.controllers = {'GRBL0': GrblLegacyProtocol(self), 'GRBL1': GrblProtocol(self)}

    # ----------------------------------------------------------------------
    def controllerSet(self, ctl):
        if ctl in self.controllers.keys():
            self.controller = ctl
            CNC.vars["controller"] = ctl
            self.mcontrol = self.controllers[ctl]

    # ----------------------------------------------------------------------
    # Evaluate a line for possible expressions
    # can return a python exception, needs to be caught
    # ----------------------------------------------------------------------
    def evaluate(self, line):
        return self.gcode.evaluate(CNC.compileLine(line, True), self)

    # ----------------------------------------------------------------------
    # Serial write
    # ----------------------------------------------------------------------
    def serial_write(self, data):
        if isinstance(data, bytes):
            ret = self.serial.write(data)
        else:
            ret = self.serial.write(data.encode())
        return ret

    # ----------------------------------------------------------------------
    # Open serial port
    # ----------------------------------------------------------------------
    def open(self, device, baudrate):
        self.serial = serial.serial_for_url(
            device.replace("\\", "\\\\"),  # Escape for windows
            baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_TIMEOUT,
            xonxoff=False,
            rtscts=False,
        )
        from PlotterProtocol import Firmware
        mode = getattr(getattr(self, 'connection_preferences', None), 'controller', 'AUTO')
        self.firmware = Firmware(mode)
        self._stop = self._pause = False
        self.mcontrol.has_override = False
        CNC.vars.update(state=CONNECTED, version='', pins='', mat_confirmation_invalid=True)
        CNC.vars['color'] = STATECOLOR[CONNECTED]
        # Keep incoming banners. Identification uses read-only queries and never resets.
        self._gcount = 0
        self._alarm = True
        self.thread = threading.Thread(target=self.serialIO)
        self.thread.start()
        return True

    # ----------------------------------------------------------------------
    # Close serial port
    # ----------------------------------------------------------------------
    def close(self):
        if self.serial is None:
            return
        try:
            pending = getattr(self, 'queue', None)
            idle = (CNC.vars.get('state') == 'Idle'
                    and not getattr(self, 'running', False)
                    and not getattr(self, '_sumcline', 0)
                    and (pending is None or pending.empty()))
            if not idle:
                self.stopRun()
        except Exception:
            pass
        self._runLines = 0
        self.thread = None
        time.sleep(1)
        try:
            self.serial.close()
        except Exception:
            pass
        self.serial = None
        CNC.vars["state"] = NOT_CONNECTED
        CNC.vars["color"] = STATECOLOR[CNC.vars["state"]]

    # ----------------------------------------------------------------------
    # Send to controller a gcode or command
    # WARNING: it has to be a single line!
    # ----------------------------------------------------------------------
    def sendGCode(self, cmd):
        if self.serial and not self.running:
            # Clear a stale _stop flag so the command isn't immediately eaten by
            # serialIO's emptyQueue() (e.g. after a purgeController soft-reset).
            self._stop = False
            if isinstance(cmd, tuple):
                self.queue.put(cmd)
            else:
                self.queue.put(cmd + "\n")

    # ----------------------------------------------------------------------
    # FIXME: legacy wrappers. try to call mcontrol directly instead:
    # ----------------------------------------------------------------------

    def softReset(self, clearAlarm=True):
        self.mcontrol.softReset(clearAlarm)

    def unlock(self, clearAlarm=True):
        self.mcontrol.unlock(clearAlarm)

    def home(self, event=None):
        self.mcontrol.home(event)

    def viewSettings(self):
        self.mcontrol.viewSettings()


    def feedHold(self, event=None):
        self.mcontrol.feedHold(event)

    def resume(self, event=None):
        self.mcontrol.resume(event)

    def pause(self, event=None):
        self.mcontrol.pause(event)

    def purgeController(self):
        self.mcontrol.purgeController()


    # ----------------------------------------------------------------------
    def emptyQueue(self):
        while self.queue.qsize() > 0:
            try:
                self.queue.get_nowait()
            except Empty:
                break

    # ----------------------------------------------------------------------
    def initRun(self):
        self._stop = False  # Clear any stale stop flag from previous run cleanup.
        self._pause = False
        self.sio_wait = False  # Reset in case it was left True by previous run.
        self._gcount = 0
        self.running = True
        self.emptyQueue()
        time.sleep(1)
        # Flush any GRBL responses that arrived during cleanup (e.g. error:3
        # replies to $G queries).  If they were processed after running=True
        # they would set _stop=True and drain the new run's gcode queue.
        if self.serial:
            self.serial.flushInput()

    def submit_program(self, commands):
        """Submit an already validated buffer; completion follows its last command."""
        if not self.running:
            raise RuntimeError('Start a job before submitting its commands.')
        self._runLines = len(commands) + 1
        self._gcount = 0
        for command in commands:
            self.queue.put(command)
        self.queue.put((WAIT,))

    # ----------------------------------------------------------------------
    # Called when run is finished
    # ----------------------------------------------------------------------
    def runEnded(self):
        if self.running:
            self.log.put((Sender.MSG_RUNEND, _("Run ended")))
            self.log.put((Sender.MSG_RUNEND, str(datetime.now())))
            self.log.put((Sender.MSG_RUNEND, str(CNC.vars["msg"])))
        self._runLines = 0
        self._msg = None
        self._pause = False
        self.running = False
        CNC.vars["running"] = False

    # ----------------------------------------------------------------------
    # Stop the current run
    # ----------------------------------------------------------------------
    def stopRun(self, event=None):
        self.feedHold()
        self._stop = True
        # if we are in the process of submitting do not do anything
        if self._runLines != sys.maxsize:
            self.purgeController()

    # ----------------------------------------------------------------------
    # thread performing I/O on serial line
    # ----------------------------------------------------------------------
    def serialIO(self):
        try:
            self._serialIOLoop()
        except Exception as error:
            # Transport failures can occur during status polling, writes or
            # reads. Keep cleanup off Tk; the UI consumes the log queue.
            if self.thread is None:
                return  # The user already requested a disconnect.
            port = self.serial
            self.thread = None
            self.serial = None
            self.emptyQueue()
            self.running = False
            self._pause = False
            self._sumcline = 0
            self._runLines = 0
            CNC.vars.update(state=NOT_CONNECTED, running=False,
                            mat_loaded=False, mat_confirmation_invalid=True)
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass
            self.log.put((Sender.MSG_RUNEND, "Connection lost; sending stopped"))
            self.log.put((Sender.MSG_ERROR, f"Connection lost: {error}"))

    def _serialIOLoop(self):
        # wait for commands to complete (status change to Idle)
        self.sio_wait = False
        self.sio_status = False  # waiting for status <...> report
        cline = []  # length of pipeline commands
        sline = []  # pipeline commands
        tosend = None  # next string to send
        from PlotterProtocol import LineFramer
        framer = LineFramer()
        tr = tg = time.time()  # last time a ? or $G was send to grbl

        while self.thread:
            t = time.time()
            # refresh machine position?
            if t - tr > SERIAL_POLL:
                self.mcontrol.viewStatusReport()
                tr = t

                # If Override change, attach feed
                if CNC.vars["_OvChanged"] and self.mcontrol.has_override and getattr(self, 'firmware', None) and self.firmware.overrides:
                    self.mcontrol.overrideSet()

            # Fetch new command to send if...
            if (
                tosend is None
                and not self.sio_wait
                and not self._pause
                and self.queue.qsize() > 0
            ):
                try:
                    tosend = self.queue.get_nowait()
                    if isinstance(tosend, tuple):
                        # wait to empty the grbl buffer and status is Idle
                        if tosend[0] == WAIT:
                            # Don't count WAIT until we are idle!
                            self.sio_wait = True
                        elif tosend[0] == MSG:
                            # Count executed commands as well
                            self._gcount += 1
                            if tosend[1] is not None:
                                # show our message on machine status
                                self._msg = tosend[1]
                        elif tosend[0] == UPDATE:
                            # Count executed commands as well
                            self._gcount += 1
                            self._update = tosend[1]
                        else:
                            # Count executed commands as well
                            self._gcount += 1
                        tosend = None

                    elif not isinstance(tosend, str):
                        try:
                            tosend = self.gcode.evaluate(tosend, self)
                            if isinstance(tosend, str):
                                tosend += "\n"
                            else:
                                # Count executed commands as well
                                self._gcount += 1
                        except Exception:
                            for s in str(sys.exc_info()[1]).splitlines():
                                self.log.put((Sender.MSG_ERROR, s))
                            self._gcount += 1
                            tosend = None
                except Empty:
                    break

                if tosend is not None:
                    # All modification in tosend should be
                    # done before adding it to cline

                    # Keep track of last feed
                    pat = FEEDPAT.match(tosend)
                    if pat is not None:
                        self._lastFeed = pat.group(2)

                    # Modify sent g-code to reflect overridden feed for
                    # controllers without override support
                    if not self.mcontrol.has_override:
                        if CNC.vars["_OvChanged"] and self.mcontrol.has_override and getattr(self, 'firmware', None) and self.firmware.overrides:
                            CNC.vars["_OvChanged"] = False
                            self._newFeed = (
                                float(self._lastFeed) * CNC.vars["_OvFeed"] / 100.0
                            )
                            if (
                                pat is None
                                and self._newFeed != 0
                                and not tosend.startswith("$")
                            ):
                                tosend = f"f{self._newFeed:g}{tosend}"

                        # Apply override Feed
                        if CNC.vars["_OvFeed"] != 100 and self._newFeed != 0:
                            pat = FEEDPAT.match(tosend)
                            if pat is not None:
                                try:
                                    tosend = "{}f{:g}{}\n".format(
                                        pat.group(1),
                                        self._newFeed,
                                        pat.group(3),
                                    )
                                except Exception:
                                    pass

                    # Bookkeeping of the buffers
                    sline.append(tosend)
                    cline.append(len(tosend))

            # Anything to receive?
            if self.serial.inWaiting() or tosend is None:
                try:
                    responses = framer.feed(self.serial.readline())
                except Exception:
                    raise  # serialIO handles transport and framing failures uniformly
                for line in responses:
                    if line and not self.mcontrol.parseLine(line, cline, sline):
                        self.log.put((Sender.MSG_RECEIVE, line))

            self._sumcline = sum(cline)

            # Received external message to stop
            if self._stop:
                self.emptyQueue()
                tosend = None
                self.log.put((Sender.MSG_CLEAR, ""))
                # WARNING if runLines==maxint then it means we are
                # still preparing/sending lines from from bCNC.run(),
                # so don't stop
                if self._runLines != sys.maxsize:
                    self._stop = False

            if tosend is not None and sum(cline) < RX_BUFFER_SIZE:
                self._sumcline = sum(cline)
                if self.mcontrol.gcode_case > 0:
                    tosend = tosend.upper()
                if self.mcontrol.gcode_case < 0:
                    tosend = tosend.lower()

                self.serial_write(tosend)

                self.log.put((Sender.MSG_BUFFER, tosend))

                tosend = None
                if not self.running and t - tg > G_POLL:
                    self.mcontrol.viewState()
                    tg = t
