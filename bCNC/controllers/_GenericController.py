# Generic motion controller definition
# All controller plugins inherit features from this one

import re
import time

from CNC import CNC, WCS


# GRBLv1
SPLITPAT = re.compile(r"[:,]")

# GRBLv0 + Smoothie
STATUSPAT = re.compile(
    r"^<(\w*?),MPos:([+\-]?\d*\.\d*),([+\-]?\d*\.\d*),([+\-]?\d*\.\d*)(?:,[+\-]?\d*\.\d*)?(?:,[+\-]?\d*\.\d*)?(?:,[+\-]?\d*\.\d*)?,WPos:([+\-]?\d*\.\d*),([+\-]?\d*\.\d*),([+\-]?\d*\.\d*)(?:,[+\-]?\d*\.\d*)?(?:,[+\-]?\d*\.\d*)?(?:,[+\-]?\d*\.\d*)?(?:,.*)?>$"
)
POSPAT = re.compile(
    r"^\[(...):([+\-]?\d*\.\d*),([+\-]?\d*\.\d*),([+\-]?\d*\.\d*)(?:,[+\-]?\d*\.\d*)?(?:,[+\-]?\d*\.\d*)?(?:,[+\-]?\d*\.\d*)?(:(\d*))?\]$"
)
# FIXME: add example for strings this regexes shall convert

TLOPAT = re.compile(r"^\[(...):([+\-]?\d*\.\d*)\]$")
DOLLARPAT = re.compile(r"^\[G\d* .*\]$")

# Only used in this file
VARPAT = re.compile(r"^\$(\d+)=(.*?)\s*(?:\(.*\))?$")


class _GenericController:
    def firmware(self):
        from PlotterProtocol import Firmware
        if not hasattr(self.master, 'firmware') or self.master.firmware is None:
            self.master.firmware = Firmware()
        return self.master.firmware

    def parseStatus(self, line, cline):
        from PlotterProtocol import status_report
        firmware = self.firmware()
        self.master.sio_status = False
        try:
            values = status_report(line, firmware)
        except (ValueError, IndexError) as error:
            self.master.log.put((self.master.MSG_RECEIVE, f'Invalid status report: {error}'))
            return
        state = values.pop('state')
        CNC.vars.update(values)
        self.master._status_sequence = getattr(self.master, '_status_sequence', 0) + 1
        self.displayState(state)
        self.master._posUpdate = True
        self.master._pause = state.startswith('Hold')
        self.has_override = firmware.overrides
        for command in firmware.queries_due(state): self.master.sendGCode(command)
        if self.master.sio_wait and not cline and state.split(':')[0] == 'Idle':
            self.master.sio_wait = False
            self.master._gcount += 1

    def parseInformation(self, line):
        if not line.endswith(']'): return
        body = line[1:-1]
        if body.startswith('G') and ':' not in body:
            CNC.vars['G'] = body.split()
            CNC.updateG(); self.master._gUpdate = True
            return
        key, separator, value = body.partition(':')
        if not separator: return
        if key == 'GC':
            CNC.vars['G'] = value.split(); CNC.updateG()
            self.master._gUpdate = True
        elif key == 'TLO':
            CNC.vars[key] = value.split(',')[0]; self.master._gUpdate = True
        elif key in ('PRB', 'G92', 'G28', 'G30', 'G54', 'G55', 'G56', 'G57', 'G58', 'G59'):
            try:
                coords = [float(v) for v in value.split(':')[0].split(',')]
                if len(coords) < 2: return
                if len(coords) == 2: coords.append(0.0)
                CNC.vars[key] = coords
                for axis, coordinate in zip('XYZABC', coords):
                    CNC.vars[('prb'+axis.lower()) if key == 'PRB' else key+axis] = coordinate
                self.master._gUpdate = True
            except ValueError:
                self.master.log.put((self.master.MSG_RECEIVE, 'Invalid coordinate report: '+line))
        else:
            CNC.vars[key] = value.split(':')


    def viewSettings(self):
        pass


    def purgeControllerExtra(self):
        pass

    def overrideSet(self):
        pass


    # ----------------------------------------------------------------------
    def softReset(self, clearAlarm=True):
        # A reset can originate outside the Tk thread. Let the UI consume this
        # invalidation instead of touching its BooleanVar from serial callbacks.
        for key in list(CNC.vars):
            if key.startswith("grbl_"):
                del CNC.vars[key]
        CNC.vars["mat_loaded"] = False
        CNC.vars["mat_confirmation_invalid"] = True
        if self.master.serial:
            self.master.serial_write(b"\030")
        if clearAlarm:
            self.master._alarm = False
        CNC.vars["_OvChanged"] = True  # force a feed change if any

    # ----------------------------------------------------------------------
    def unlock(self, clearAlarm=True):
        if clearAlarm:
            self.master._alarm = False
        self.master.sendGCode("$X")

    # ----------------------------------------------------------------------
    def home(self, event=None):
        self.master._alarm = False
        self.master.sendGCode("$H")
        # After machine homing, return to mat origin (Y=0 in work coords).
        # grblHAL preserves G92 through $H, so the work-coordinate origin
        # set by loadMat (G92 X0 Y0) is still valid and G0 X0 Y0 will
        # bring the tool back to the beginning of the mat.
        if CNC.vars.get("mat_loaded"):
            self.master.sendGCode("G90G0X0Y0")

    def viewStatusReport(self):
        self.master.serial_write(b"\x80" if self.firmware().extended else b"?")
        self.master.sio_status = True

    def viewParameters(self):
        self.master.sendGCode("$#")

    def viewState(self):  # Maybe rename to viewParserState() ???
        self.master.sendGCode("$G")

    # ----------------------------------------------------------------------
    def feedHold(self, event=None):
        if self.master.serial is None:
            return
        self.master.serial_write(b"!")
        self.master.serial.flush()
        self.master._pause = True

    # ----------------------------------------------------------------------
    def resume(self, event=None):
        if self.master.serial is None:
            return
        self.master.serial_write(b"~")
        self.master.serial.flush()
        self.master._msg = None
        self.master._alarm = False
        self.master._pause = False

    # ----------------------------------------------------------------------
    def pause(self, event=None):
        if self.master.serial is None:
            return
        if self.master._pause:
            self.master.resume()
        else:
            self.master.feedHold()

    # ----------------------------------------------------------------------
    # Purge the buffer of the controller. Unfortunately we have to perform
    # a reset to clear the buffer of the controller
    # ---------------------------------------------------------------------
    def purgeController(self):
        self.master.serial_write(b"!")
        self.master.serial.flush()
        time.sleep(1)
        # remember and send all G commands; exclude G92 because it persists
        # through a soft reset and sending bare "G92" combined with a motion
        # command (G0) in the same block is rejected by GrblHAL (error:24).
        G = " ".join([x for x in CNC.vars["G"] if x[0] == "G" and x != "G92"])
        TLO = CNC.vars["TLO"]
        self.softReset(False)  # reset controller
        # runEnded() must come before purgeControllerExtra() so that
        # running=False when $X is sent via sendGCode() inside
        # purgeControllerExtra(); sendGCode() is a no-op when running=True.
        self.master.runEnded()
        self.purgeControllerExtra()
        if G:
            self.master.sendGCode(G)  # restore $G
        self.master.sendGCode(f"G43.1Z{TLO}")  # restore TLO
        self.viewState()
        self.viewParameters()

    # ----------------------------------------------------------------------
    def displayState(self, state):
        state = state.strip()

        # Command rejection is not a machine-state transition. Keep the actual
        # Idle/Run/Alarm status and report the command error separately.
        if state.startswith("error:"):
            return

        # Do not show g-code errors, when machine is already in alarm state
        if (CNC.vars["state"].startswith("ALARM:")
                and state.startswith("error:")):
            print(f"Suppressed: {state}")
            return

        # Do not show alarm without number when we already
        # display alarm with number
        if state == "Alarm" and CNC.vars["state"].startswith("ALARM:"):
            return

        CNC.vars["state"] = state

    # ----------------------------------------------------------------------
    def parseLine(self, line, cline, sline):
        if not line:
            return True
        if line.lower().startswith(('grbl ', 'grblhal ')):
            from PlotterProtocol import Firmware
            self.master.firmware = Firmware(self.firmware().mode)
        self.firmware().observe(line)
        CNC.vars["version"] = self.firmware().version

        if line[0] == "<":
            if not self.master.sio_status:
                self.master.log.put((self.master.MSG_RECEIVE, line))
            self.parseBracketAngle(line, cline)

        elif line[0] == "[":
            self.master.log.put((self.master.MSG_RECEIVE, line))
            self.parseInformation(line)

        elif "error:" in line or "ALARM:" in line:
            self.master.log.put((self.master.MSG_ERROR, line))
            self.master._gcount += 1
            if cline:
                del cline[0]
            if sline:
                CNC.vars["errline"] = sline.pop(0)
            if not self.master._alarm:
                self.master._posUpdate = True
            self.master._alarm = True
            self.displayState(line)
            if self.master.running:
                self.master._stop = True

        elif line.strip() == "ok":
            self.master.log.put((self.master.MSG_OK, line))
            self.master._gcount += 1
            if cline:
                del cline[0]
            if sline:
                del sline[0]

        elif line[0] == "$":
            self.master.log.put((self.master.MSG_RECEIVE, line))
            pat = VARPAT.match(line)
            if pat:
                value = pat.group(2)
                if self.firmware().family == 'grblHAL': value = line.split('=', 1)[1]
                CNC.vars[f"grbl_{pat.group(1)}"] = value
                annotation = re.search(r'\((.*)\)\s*$', line)
                if annotation and self.firmware().version.startswith('0.'):
                    self.firmware().settings[int(pat.group(1))] = {'name': annotation[1]}


        elif line.lower().startswith(('grbl ', 'grblhal ')):
            self.master.log.put((self.master.MSG_RECEIVE, line))
            self.master._stop = True
            del cline[:]
            del sline[:]
            CNC.vars['mat_confirmation_invalid'] = True
            if self.master.running:
                self.master.emptyQueue()
                self.master.runEnded()
                self.master.log.put((self.master.MSG_ERROR, 'Controller restarted during the cut. Inspect the mat and re-home before restarting.'))
            self.firmware().observe(line)
            CNC.vars['version'] = self.firmware().version

        else:
            # We return false in order to tell that we can't parse this line
            # Sender will log the line in such case
            return False

        # Parsing successful
        return True
