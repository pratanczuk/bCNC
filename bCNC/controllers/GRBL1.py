# GRBL 1.0+ motion controller plugin

from _GenericGRBL import _GenericGRBL
from CNC import CNC

OV_FEED_100 = chr(0x90)  # Extended override commands
OV_FEED_i10 = chr(0x91)
OV_FEED_d10 = chr(0x92)
OV_FEED_i1 = chr(0x93)
OV_FEED_d1 = chr(0x94)

OV_RAPID_100 = chr(0x95)
OV_RAPID_50 = chr(0x96)
OV_RAPID_25 = chr(0x97)

OV_SPINDLE_100 = chr(0x99)
OV_SPINDLE_i10 = chr(0x9A)
OV_SPINDLE_d10 = chr(0x9B)
OV_SPINDLE_i1 = chr(0x9C)
OV_SPINDLE_d1 = chr(0x9D)

OV_SPINDLE_STOP = chr(0x9E)

OV_FLOOD_TOGGLE = chr(0xA0)
OV_MIST_TOGGLE = chr(0xA1)


class Controller(_GenericGRBL):
    def __init__(self, master):
        self.gcode_case = 0
        self.has_override = True
        self.master = master

    def jog(self, direction):
        self.master.sendGCode(f"$J=G91 {direction} F100000")
        # XXX is F100000 correct?

    def overrideSet(self):
        CNC.vars["_OvChanged"] = False  # Temporary
        # Check feed
        diff = CNC.vars["_OvFeed"] - CNC.vars["OvFeed"]
        if diff == 0:
            pass
        elif CNC.vars["_OvFeed"] == 100:
            self.master.serial_write(OV_FEED_100)
        elif diff >= 10:
            self.master.serial_write(OV_FEED_i10)
            CNC.vars["_OvChanged"] = diff > 10
        elif diff <= -10:
            self.master.serial_write(OV_FEED_d10)
            CNC.vars["_OvChanged"] = diff < -10
        elif diff >= 1:
            self.master.serial_write(OV_FEED_i1)
            CNC.vars["_OvChanged"] = diff > 1
        elif diff <= -1:
            self.master.serial_write(OV_FEED_d1)
            CNC.vars["_OvChanged"] = diff < -1
        # Check rapid
        target = CNC.vars["_OvRapid"]
        current = CNC.vars["OvRapid"]
        if target == current:
            pass
        elif target == 100:
            self.master.serial_write(OV_RAPID_100)
        # FIXME: GRBL protocol does not specify 75% override command at all
        elif target == 75:
            self.master.serial_write(
                OV_RAPID_50
            )
        elif target == 50:
            self.master.serial_write(OV_RAPID_50)
        elif target == 25:
            self.master.serial_write(OV_RAPID_25)
        # Check Spindle
        diff = CNC.vars["_OvSpindle"] - CNC.vars["OvSpindle"]
        if diff == 0:
            pass
        elif CNC.vars["_OvSpindle"] == 100:
            self.master.serial_write(OV_SPINDLE_100)
        elif diff >= 10:
            self.master.serial_write(OV_SPINDLE_i10)
            CNC.vars["_OvChanged"] = diff > 10
        elif diff <= -10:
            self.master.serial_write(OV_SPINDLE_d10)
            CNC.vars["_OvChanged"] = diff < -10
        elif diff >= 1:
            self.master.serial_write(OV_SPINDLE_i1)
            CNC.vars["_OvChanged"] = diff > 1
        elif diff <= -1:
            self.master.serial_write(OV_SPINDLE_d1)
            CNC.vars["_OvChanged"] = diff < -1

    def parseBracketAngle(self, line, cline):
        return self.parseStatus(line, cline)
