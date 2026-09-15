# $Id: CNC.py,v 1.8 2014/10/15 15:03:49 bnv Exp $
#
# Author: vvlachoudis@gmail.com
# Date: 24-Aug-2014

import math
import os
import re
import types

import undo
import Unicode
from math import sqrt, atan2, cos, sin
from bmath import Vector
from bpath import Path, Segment
from dxf import DXF
from svgcode import SVGcode
from Helpers import to_zip

IDPAT = re.compile(r".*\bid:\s*(.*?)\)")
PARENPAT = re.compile(r"(\(.*?\))")
SEMIPAT = re.compile(r"(;.*)")
OPPAT = re.compile(r"(.*)\[(.*)\]")
CMDPAT = re.compile(r"([A-Za-z]+)")
BLOCKPAT = re.compile(r"^\(Block-([A-Za-z]+):\s*(.*)\)")
AUXPAT = re.compile(r"^(%[A-Za-z0-9]+)\b *(.*)$")

STOP = 0
SKIP = 1
ASK = 2
MSG = 3
WAIT = 4
UPDATE = 5

XY = 0
XZ = 1
YZ = 2

CW = 2
CCW = 3

WCS = ["G54", "G55", "G56", "G57", "G58", "G59"]

DISTANCE_MODE = {"G90": "Absolute", "G91": "Incremental"}
FEED_MODE = {"G93": "1/Time", "G94": "unit/min", "G95": "unit/rev"}
UNITS = {"G20": "inch", "G21": "mm"}
PLANE = {"G17": "XY", "G18": "XZ", "G19": "YZ"}

# Modal Mode from $G and variable set
MODAL_MODES = {
    "G0": "motion",
    "G1": "motion",
    "G2": "motion",
    "G3": "motion",
    "G38.2": "motion",
    "G38.3": "motion",
    "G38.4": "motion",
    "G38.5": "motion",
    "G80": "motion",
    "G54": "WCS",
    "G55": "WCS",
    "G56": "WCS",
    "G57": "WCS",
    "G58": "WCS",
    "G59": "WCS",
    "G17": "plane",
    "G18": "plane",
    "G19": "plane",
    "G90": "distance",
    "G91": "distance",
    "G91.1": "arc",
    "G93": "feedmode",
    "G94": "feedmode",
    "G95": "feedmode",
    "G20": "units",
    "G21": "units",
    "G40": "cutter",
    "G43.1": "tlo",
    "G49": "tlo",
    "M0": "program",
    "M1": "program",
    "M2": "program",
    "M30": "program",
    "M3": "spindle",
    "M4": "spindle",
    "M5": "spindle",
    "M7": "coolant",
    "M8": "coolant",
    "M9": "coolant",
}

ERROR_HANDLING = {}
TOLERANCE = 1e-7
MAXINT = 1000000000  # python3 doesn't have maxint


# -----------------------------------------------------------------------------
# Return a value combined from two dictionaries new/old
# -----------------------------------------------------------------------------
def getValue(name, new, old, default=0.0):
    try:
        return new[name]
    except Exception:
        try:
            return old[name]
        except Exception:
            return default


# =============================================================================
# Probing class and linear interpolation
# =============================================================================


# =============================================================================
# contains a list of machine points vs position in the gcode
# calculates the transformation matrix (rotation + translation) needed
# to adjust the gcode to match the workpiece on the machine
# =============================================================================


# =============================================================================
# Command operations on a CNC
# =============================================================================
class CNC:
    inch = False
    acceleration_x = 25.0  # mm/s^2
    acceleration_y = 25.0  # mm/s^2
    acceleration_z = 25.0  # mm/s^2
    feedmax_x = 3000
    feedmax_y = 3000
    feedmax_z = 2000
    travel_x = 300
    travel_y = 300
    travel_z = 60
    accuracy = 0.01  # sagitta error during arc conversion
    digits = 4
    startup = "G90"
    stdexpr = False  # standard way of defining expressions with []
    comment = ""  # last parsed comment
    vars = {
        "prbx": 0.0,
        "prby": 0.0,
        "prbz": 0.0,
        "prbcmd": "G38.2",
        "prbfeed": 10.0,
        "errline": "",
        "wx": 0.0,
        "wy": 0.0,
        "wz": 0.0,
        "wa": 0.0,
        "wb": 0.0,
        "wc": 0.0,
        "mx": 0.0,
        "my": 0.0,
        "mz": 0.0,
        "ma": 0.0,
        "mb": 0.0,
        "mc": 0.0,
        "wcox": 0.0,
        "wcoy": 0.0,
        "wcoz": 0.0,
        "wcoa": 0.0,
        "wcob": 0.0,
        "wcoc": 0.0,
        "curfeed": 0.0,
        "curspindle": 0.0,
        "_camwx": 0.0,
        "_camwy": 0.0,
        "G": [],
        "TLO": 0.0,
        "motion": "G0",
        "WCS": "G54",
        "plane": "G17",
        "feedmode": "G94",
        "distance": "G90",
        "arc": "G91.1",
        "units": "G20",
        "cutter": "",
        "tlo": "",
        "program": "M0",
        "spindle": "M5",
        "coolant": "M9",
        "tool": 0,
        "feed": 0.0,
        "rpm": 0.0,
        "planner": 0,
        "rxbytes": 0,
        "OvFeed": 100,  # Override status
        "OvRapid": 100,
        "OvSpindle": 100,
        "_OvChanged": False,
        "_OvFeed": 100,  # Override target values
        "_OvRapid": 100,
        "_OvSpindle": 100,
        "diameter": 3.175,  # Tool diameter
        "cutfeed": 1000.0,  # Material feed for cutting
        "cutfeedz": 500.0,  # Material feed for cutting
        "safe": 3.0,
        "state": "",
        "pins": "",
        "msg": "",
        "stepz": 1.0,
        "surface": 0.0,
        "thickness": 5.0,
        "stepover": 40.0,
        "PRB": None,
        "TLO": 0.0,
        "version": "",
        "controller": "",
        "running": False,
        # ── Cutting-mat / foil-plotter parameters (MatManager) ──────────
        "mat_width":          300.0,   # mm – physical mat X dimension
        "mat_height":         300.0,   # mm – physical mat Y dimension
        "mat_pressure":         500.0, # PWM value 0-1000 for M3 S command
        "mat_speed":          500.0,   # mm/min – default cutting feed
        "mat_knife_offset":     0.5,   # mm – swivel-axis to blade-tip
        "mat_auto_dragknife": False,   # auto-apply drag-knife on load
        "mat_loaded":         False,   # physical mat present flag
    }

    appendFeed = False  # append feed on every G1/G2/G3 commands to be used
    # ----------------------------------------------------------------------
    def __init__(self):
        self.initPath()
        self.bounds = {}
        self.resetAllMargins()

    # ----------------------------------------------------------------------
    # Update G variables from "G" string
    # ----------------------------------------------------------------------
    @staticmethod
    def updateG():
        for g in CNC.vars["G"]:
            if g[0] == "F":
                CNC.vars["feed"] = float(g[1:])
            elif g[0] == "S":
                CNC.vars["rpm"] = float(g[1:])
            elif g[0] == "T":
                CNC.vars["tool"] = int(g[1:])
            else:
                var = MODAL_MODES.get(g)
                if var is not None:
                    CNC.vars[var] = g

    # ----------------------------------------------------------------------
    def __getitem__(self, name):
        return CNC.vars[name]

    # ----------------------------------------------------------------------
    def __setitem__(self, name, value):
        CNC.vars[name] = value

    # ----------------------------------------------------------------------
    @staticmethod
    def loadConfig(config):
        section = "CNC"
        try:
            CNC.inch = bool(int(config.get(section, "units")))
        except Exception:
            pass
        try:
            CNC.doublesizeicon = bool(int(
                config.get(section, "doublesizeicon")))
        except Exception:
            pass
        try:
            CNC.acceleration_x = float(config.get(section, "acceleration_x"))
        except Exception:
            pass
        try:
            CNC.acceleration_y = float(config.get(section, "acceleration_y"))
        except Exception:
            pass
        try:
            CNC.acceleration_z = float(config.get(section, "acceleration_z"))
        except Exception:
            pass
        try:
            CNC.feedmax_x = float(config.get(section, "feedmax_x"))
        except Exception:
            pass
        try:
            CNC.feedmax_y = float(config.get(section, "feedmax_y"))
        except Exception:
            pass
        try:
            CNC.feedmax_z = float(config.get(section, "feedmax_z"))
        except Exception:
            pass
        try:
            CNC.travel_x = float(config.get(section, "travel_x"))
        except Exception:
            pass
        try:
            CNC.travel_y = float(config.get(section, "travel_y"))
        except Exception:
            pass
        try:
            CNC.travel_z = float(config.get(section, "travel_z"))
        except Exception:
            pass
        try:
            CNC.acceleration_a = float(config.get(section, "acceleration_a"))
        except Exception:
            pass
        try:
            CNC.acceleration_b = float(config.get(section, "acceleration_b"))
        except Exception:
            pass
        try:
            CNC.acceleration_c = float(config.get(section, "acceleration_c"))
        except Exception:
            pass
        try:
            CNC.feedmax_a = float(config.get(section, "feedmax_a"))
        except Exception:
            pass
        try:
            CNC.feedmax_b = float(config.get(section, "feedmax_b"))
        except Exception:
            pass
        try:
            CNC.feedmax_c = float(config.get(section, "feedmax_c"))
        except Exception:
            pass
        try:
            CNC.travel_a = float(config.get(section, "travel_a"))
        except Exception:
            pass
        try:
            CNC.travel_b = float(config.get(section, "travel_b"))
        except Exception:
            pass
        try:
            CNC.travel_c = float(config.get(section, "travel_c"))
        except Exception:
            pass
        try:
            CNC.accuracy = float(config.get(section, "accuracy"))
        except Exception:
            pass
        try:
            CNC.digits = int(config.get(section, "round"))
        except Exception:
            pass
        try:
            CNC.startup = config.get(section, "startup")
        except Exception:
            pass
        try:
            CNC.header = config.get(section, "header")
        except Exception:
            pass
        try:
            CNC.footer = config.get(section, "footer")
        except Exception:
            pass

        if CNC.inch:
            CNC.acceleration_x /= 25.4
            CNC.acceleration_y /= 25.4
            CNC.acceleration_z /= 25.4
            CNC.feedmax_x /= 25.4
            CNC.feedmax_y /= 25.4
            CNC.feedmax_z /= 25.4
            CNC.travel_x /= 25.4
            CNC.travel_y /= 25.4
            CNC.travel_z /= 25.4
            # a,b,c are in degrees no conversion required

        section = "Error"

        for cmd, value in config.items(section):
            try:
                ERROR_HANDLING[cmd.upper()] = int(value)
            except Exception:
                pass

    # ----------------------------------------------------------------------
    @staticmethod
    def saveConfig(config):
        pass

    # ----------------------------------------------------------------------
    def initPath(self, x=None, y=None, z=None, a=None, b=None, c=None):
        if x is None:
            self.x = self.xval = CNC.vars["wx"] or 0
        else:
            self.x = self.xval = x
        if y is None:
            self.y = self.yval = CNC.vars["wy"] or 0
        else:
            self.y = self.yval = y
        if z is None:
            self.z = self.zval = CNC.vars["wz"] or 0
        else:
            self.z = self.zval = z
        if a is None:
            self.a = self.aval = CNC.vars["wa"] or 0
        else:
            self.a = self.aval = a
        if b is None:
            self.b = self.bval = CNC.vars["wb"] or 0
        else:
            self.b = self.bval = b
        if c is None:
            self.c = self.cval = CNC.vars["wc"] or 0
        else:
            self.c = self.cval = c

        self.ival = self.jval = self.kval = 0.0
        self.uval = self.vval = self.wval = 0.0
        self.dx = self.dy = self.dz = 0.0
        self.di = self.dj = self.dk = 0.0
        self.rval = 0.0
        self.pval = 0.0
        self.qval = 0.0
        self.unit = 1.0
        self.mval = 0
        self.lval = 1
        self.tool = 0
        self._lastTool = None

        self.absolute = True  # G90/G91     absolute/relative motion
        self.arcabsolute = False  # G90.1/G91.1 absolute/relative arc
        self.gcode = None
        self.plane = XY
        self.feedmode = 94
        self.feed = 0  # Actual gcode feed rate (not to confuse with cutfeed
        self.totalLength = 0.0
        self.totalTime = 0.0

    # ----------------------------------------------------------------------
    def resetEnableMargins(self):
        # Selected blocks margin
        self.bounds["xmin"] = self.bounds["ymin"] = self.bounds["zmin"] = 1000000.0
        self.bounds["xmax"] = self.bounds["ymax"] = self.bounds["zmax"] = -1000000.0

    # ----------------------------------------------------------------------
    def resetAllMargins(self):
        self.resetEnableMargins()
        # All blocks margin
        self.bounds["axmin"] = self.bounds["aymin"] = self.bounds["azmin"] = 1000000.0
        self.bounds["axmax"] = self.bounds["aymax"] = self.bounds["azmax"] = -1000000.0

    # ----------------------------------------------------------------------
    def isMarginValid(self):
        return (
            self.bounds["xmin"] <= self.bounds["xmax"]
            and self.bounds["ymin"] <= self.bounds["ymax"]
            and self.bounds["zmin"] <= self.bounds["zmax"]
        )

    # ----------------------------------------------------------------------
    def isAllMarginValid(self):
        return (
            self.bounds["axmin"] <= self.bounds["axmax"]
            and self.bounds["aymin"] <= self.bounds["aymax"]
            and self.bounds["azmin"] <= self.bounds["azmax"]
        )

    # ----------------------------------------------------------------------
    # Number formatting
    # ----------------------------------------------------------------------
    @staticmethod
    def fmt(c, v, d=None):
        if d is None:
            d = CNC.digits
        # Don't know why, but in some cases floats are not truncated by
        # format string unless rounded
        # I guess it's vital idea to round them rather than truncate anyway!
        v = round(v, d)
        return (f"{c}{v:>{d}f}").rstrip("0").rstrip(".")

    # ----------------------------------------------------------------------
    @staticmethod
    def gcode(g, pairs):
        s = f"g{int(g)}"
        for c, v in pairs:
            s += f" {c[0]}{round(v, CNC.digits):g}"
        return s

    # ----------------------------------------------------------------------

    @staticmethod
    def _goto(g, x=None, y=None, z=None, **args):
        s = f"g{int(g)}"
        if x is not None:
            s += " " + CNC.fmt("x", x)
        if y is not None:
            s += " " + CNC.fmt("y", y)
        if z is not None:
            s += " " + CNC.fmt("z", z)
        for n, v in args.items():
            s += " " + CNC.fmt(n, v)
        return s

    # ----------------------------------------------------------------------

    @staticmethod
    def grapid(x=None, y=None, z=None, **args):
        return CNC._goto(0, x, y, z, **args)

    # ----------------------------------------------------------------------

    @staticmethod
    def gline(x=None, y=None, z=None, **args):
        return CNC._goto(1, x, y, z, **args)

    # ----------------------------------------------------------------------
    @staticmethod
    def garc(g, x=None, y=None, z=None, i=None, j=None, k=None, **args):
        s = f"g{int(g)}"
        if x is not None:
            s += " " + CNC.fmt("x", x)
        if y is not None:
            s += " " + CNC.fmt("y", y)
        if z is not None:
            s += " " + CNC.fmt("z", z)
        if i is not None:
            s += " " + CNC.fmt("i", i)
        if j is not None:
            s += " " + CNC.fmt("j", j)
        if k is not None:
            s += " " + CNC.fmt("k", k)
        for n, v in args.items():
            s += " " + CNC.fmt(n, v)
        return s

    # ----------------------------------------------------------------------
    # Lower the blade at its configured Z feed
    # ----------------------------------------------------------------------
    @staticmethod
    def zenter(z, d=None):
        return (f"g1 {CNC.fmt('z', z, d)} "
                f"{CNC.fmt('f', CNC.vars['cutfeedz'])}")

    # ----------------------------------------------------------------------
    @staticmethod
    def zexit(z, d=None):
        return f"g0 {CNC.fmt('z', z, d)}"

    # ----------------------------------------------------------------------
    # gcode to go to z-safe
    # Lift the blade clear of the material
    # ----------------------------------------------------------------------
    @staticmethod
    def zsafe():
        return CNC.zexit(CNC.vars["safe"])

    # ----------------------------------------------------------------------
    # @return line in broken a list of commands, None if empty or comment
    # ----------------------------------------------------------------------
    @staticmethod
    def parseLine(line):
        # skip empty lines
        if len(line) == 0 or line[0] in ("%", "(", "#", ";"):
            return None

        # remove comments
        line = PARENPAT.sub("", line)
        line = SEMIPAT.sub("", line)

        # process command
        # strip all spaces
        line = line.replace(" ", "")

        # Insert space before each command
        line = CMDPAT.sub(r" \1", line).lstrip()
        return line.split()

    # ----------------------------------------------------------------------
    # @return line,comment
    #   line broken in a list of commands,
    #       None,"" if empty or comment
    #       else compiled expressions,""
    # ----------------------------------------------------------------------
    @staticmethod
    def compileLine(line, space=False):
        line = line.strip()
        if not line:
            return None
        if line[0] == "$":
            return line

        # to accept #nnn variables as _nnn internally
        line = line.replace("#", "_")
        CNC.comment = ""

        # execute literally the line after the first character
        if line[0] == "%":
            # special command
            pat = AUXPAT.match(line.strip())
            if pat:
                cmd = pat.group(1)
                args = pat.group(2)
            else:
                cmd = None
                args = None
            if cmd == "%wait":
                return (WAIT,)
            elif cmd == "%msg":
                if not args:
                    args = None
                return (MSG, args)
            elif cmd == "%update":
                return (UPDATE, args)
            elif line.startswith("%if running") and not CNC.vars["running"]:
                # ignore if running lines when not running
                return None
            else:
                try:
                    return compile(line[1:], "", "exec")
                except Exception as e:
                    print("Compile line error: \n")
                    print(e)
                    return None

        # most probably an assignment like  #nnn = expr
        if line[0] == "_":
            try:
                return compile(line, "", "exec")
            except Exception:
                # FIXME show the error!!!!
                return None

        # commented line
        if line[0] == ";":
            CNC.comment = line[1:].strip()
            return None

        out = []  # output list of commands
        bracket = 0  # bracket count []
        paren = 0  # parenthesis count ()
        expr = ""  # expression string
        cmd = ""  # cmd string
        inComment = False  # inside inComment
        for i, ch in enumerate(line):
            if ch == "(":
                # comment start?
                paren += 1
                inComment = bracket == 0
                if not inComment:
                    expr += ch
            elif ch == ")":
                # comment end?
                paren -= 1
                if not inComment:
                    expr += ch
                if paren == 0 and inComment:
                    inComment = False
            elif ch == "[":
                # expression start?
                if not inComment:
                    if CNC.stdexpr:
                        ch = "("
                    bracket += 1
                    if bracket == 1:
                        if cmd:
                            out.append(cmd)
                            cmd = ""
                    else:
                        expr += ch
                else:
                    CNC.comment += ch
            elif ch == "]":
                # expression end?
                if not inComment:
                    if CNC.stdexpr:
                        ch = ")"
                    bracket -= 1
                    if bracket == 0:
                        try:
                            out.append(compile(expr, "", "eval"))
                        except Exception:
                            # FIXME show the error!!!!
                            pass
                        expr = ""
                    else:
                        expr += ch
                else:
                    CNC.comment += ch
            elif ch == "=":
                # check for assignments (FIXME very bad)
                if not out and bracket == 0 and paren == 0:
                    for i in " ()-+*/^$":
                        if i in cmd:
                            cmd += ch
                            break
                    else:
                        try:
                            return compile(line, "", "exec")
                        except Exception:
                            # FIXME show the error!!!!
                            return None
            elif ch == ";":
                # Skip everything after the semicolon on normal lines
                if not inComment and paren == 0 and bracket == 0:
                    CNC.comment += line[i + 1:]
                    break
                else:
                    expr += ch

            elif bracket > 0:
                expr += ch

            elif not inComment:
                if ch == " ":
                    if space:
                        cmd += ch
                else:
                    cmd += ch

            elif inComment:
                CNC.comment += ch

        if cmd:
            out.append(cmd)

        # return output commands
        if len(out) == 0:
            return None
        if len(out) > 1:
            return out
        return out[0]

    # ----------------------------------------------------------------------
    # Break line into commands
    # ----------------------------------------------------------------------
    @staticmethod
    def breakLine(line):
        if line is None:
            return None
        # Insert space before each command
        line = CMDPAT.sub(r" \1", line).lstrip()
        return line.split()

    # ----------------------------------------------------------------------
    # Create path for one g command
    # ----------------------------------------------------------------------
    def motionStart(self, cmds):
        self.mval = 0  # reset m command
        for cmd in cmds:
            c = cmd[0].upper()
            try:
                value = float(cmd[1:])
            except Exception:
                value = 0

            if c == "X":
                self.xval = value * self.unit
                if not self.absolute:
                    self.xval += self.x
                self.dx = self.xval - self.x

            elif c == "Y":
                self.yval = value * self.unit
                if not self.absolute:
                    self.yval += self.y
                self.dy = self.yval - self.y

            elif c == "Z":
                self.zval = value * self.unit
                if not self.absolute:
                    self.zval += self.z
                self.dz = self.zval - self.z

            elif c == "A":
                self.aval = value * self.unit

            elif c == "F":
                self.feed = value * self.unit

            elif c == "G":
                gcode = int(value)
                decimal = int(round((value - gcode) * 10))

                # Execute immediately
                if gcode in (4, 10, 53):
                    pass  # do nothing but don't record to motion
                elif gcode == 17:
                    self.plane = XY

                elif gcode == 18:
                    self.plane = XZ

                elif gcode == 19:
                    self.plane = YZ

                elif gcode == 20:  # Switch to inches
                    if CNC.inch:
                        self.unit = 1.0
                    else:
                        self.unit = 25.4

                elif gcode == 21:  # Switch to mm
                    if CNC.inch:
                        self.unit = 1.0 / 25.4
                    else:
                        self.unit = 1.0

                elif gcode == 80:
                    # turn off canned cycles
                    self.gcode = None
                    self.dz = 0
                    self.zval = self.z

                elif gcode == 90:
                    if decimal == 0:
                        self.absolute = True
                    elif decimal == 1:
                        self.arcabsolute = True

                elif gcode == 91:
                    if decimal == 0:
                        self.absolute = False
                    elif decimal == 1:
                        self.arcabsolute = False

                elif gcode in (93, 94, 95):
                    self.feedmode = gcode


                else:
                    self.gcode = gcode

            elif c == "I":
                self.ival = value * self.unit
                if self.arcabsolute:
                    self.ival -= self.x

            elif c == "J":
                self.jval = value * self.unit
                if self.arcabsolute:
                    self.jval -= self.y

            elif c == "K":
                self.kval = value * self.unit
                if self.arcabsolute:
                    self.kval -= self.z

            elif c == "L":
                self.lval = int(value)

            elif c == "M":
                self.mval = int(value)

            elif c == "N":
                pass

            elif c == "P":
                self.pval = value

            elif c == "Q":
                self.qval = value * self.unit

            elif c == "R":
                self.rval = value * self.unit

            elif c == "T":
                self.tool = int(value)

            elif c == "U":
                self.uval = value * self.unit

            elif c == "V":
                self.vval = value * self.unit

            elif c == "W":
                self.wval = value * self.unit

    # ----------------------------------------------------------------------
    # Return center x,y,z,r for arc motions 2,3 and set self.rval
    # ----------------------------------------------------------------------
    def motionCenter(self):
        if self.rval > 0.0:
            if self.plane == XY:
                x = self.x
                y = self.y
                xv = self.xval
                yv = self.yval
            elif self.plane == XZ:
                x = self.x
                y = self.z
                xv = self.xval
                yv = self.zval
            else:
                x = self.y
                y = self.z
                xv = self.yval
                yv = self.zval

            ABx = xv - x
            ABy = yv - y
            Cx = 0.5 * (x + xv)
            Cy = 0.5 * (y + yv)
            AB = math.sqrt(ABx**2 + ABy**2)
            try:
                OC = math.sqrt(self.rval**2 - AB**2 / 4.0)
            except Exception:
                OC = 0.0
            if self.gcode == 2:
                OC = -OC  # CW
            if AB != 0.0:
                return Cx - OC * ABy / AB, Cy + OC * ABx / AB
            else:
                # Error!!!
                return x, y
        else:
            # Center
            xc = self.x + self.ival
            yc = self.y + self.jval
            zc = self.z + self.kval
            self.rval = math.sqrt(self.ival**2 + self.jval**2 + self.kval**2)

            if self.plane == XY:
                return xc, yc
            elif self.plane == XZ:
                return xc, zc
            else:
                return yc, zc

    # ----------------------------------------------------------------------
    # Create path for one g command
    # ----------------------------------------------------------------------
    def motionPath(self):
        xyz = []

        # Execute g-code
        if self.gcode in (0, 1):  # fast move or line
            if (
                self.xval - self.x != 0.0
                or self.yval - self.y != 0.0
                or self.zval - self.z != 0.0
            ):
                xyz.append((self.x, self.y, self.z))
                xyz.append((self.xval, self.yval, self.zval))

        elif self.gcode in (2, 3):  # CW=2,CCW=3 circle
            xyz.append((self.x, self.y, self.z))
            uc, vc = self.motionCenter()

            gcode = self.gcode
            if self.plane == XY:
                u0 = self.x
                v0 = self.y
                w0 = self.z
                u1 = self.xval
                v1 = self.yval
                w1 = self.zval
            elif self.plane == XZ:
                u0 = self.x
                v0 = self.z
                w0 = self.y
                u1 = self.xval
                v1 = self.zval
                w1 = self.yval
                gcode = 5 - gcode  # flip 2-3 when XZ plane is used
            else:
                u0 = self.y
                v0 = self.z
                w0 = self.x
                u1 = self.yval
                v1 = self.zval
                w1 = self.xval
            phi0 = math.atan2(v0 - vc, u0 - uc)
            phi1 = math.atan2(v1 - vc, u1 - uc)
            try:
                sagitta = 1.0 - CNC.accuracy / self.rval
            except ZeroDivisionError:
                sagitta = 0.0
            if sagitta > 0.0:
                df = 2.0 * math.acos(sagitta)
                df = min(df, math.pi / 4.0)
            else:
                df = math.pi / 4.0

            if gcode == 2:
                if phi1 >= phi0 - 1e-10:
                    phi1 -= 2.0 * math.pi
                ws = (w1 - w0) / (phi1 - phi0)
                phi = phi0 - df
                while phi > phi1:
                    u = uc + self.rval * math.cos(phi)
                    v = vc + self.rval * math.sin(phi)
                    w = w0 + (phi - phi0) * ws
                    phi -= df
                    if self.plane == XY:
                        xyz.append((u, v, w))
                    elif self.plane == XZ:
                        xyz.append((u, w, v))
                    else:
                        xyz.append((w, u, v))
            else:
                if phi1 <= phi0 + 1e-10:
                    phi1 += 2.0 * math.pi
                ws = (w1 - w0) / (phi1 - phi0)
                phi = phi0 + df
                while phi < phi1:
                    u = uc + self.rval * math.cos(phi)
                    v = vc + self.rval * math.sin(phi)
                    w = w0 + (phi - phi0) * ws
                    phi += df
                    if self.plane == XY:
                        xyz.append((u, v, w))
                    elif self.plane == XZ:
                        xyz.append((u, w, v))
                    else:
                        xyz.append((w, u, v))

            xyz.append((self.xval, self.yval, self.zval))

        elif self.gcode == 4:  # Dwell
            self.totalTime = self.pval


        return xyz

    # ----------------------------------------------------------------------
    # move to end position
    # ----------------------------------------------------------------------
    def motionEnd(self):
        if self.gcode in (0, 1, 2, 3):
            self.x = self.xval
            self.y = self.yval
            self.z = self.zval
            self.dx = 0
            self.dy = 0
            self.dz = 0

            if self.gcode >= 2:  # reset at the end
                self.rval = self.ival = self.jval = self.kval = 0.0

        elif self.gcode in (28, 30, 92):
            self.x = 0.0
            self.y = 0.0
            self.z = 0.0
            self.dx = 0
            self.dy = 0
            self.dz = 0

    # ----------------------------------------------------------------------
    # Doesn't work correctly for G83 (peck drilling)
    # ----------------------------------------------------------------------
    def pathLength(self, block, xyz):
        # For XY plane
        p = xyz[0]
        length = 0.0
        for i in xyz:
            length += math.sqrt(
                (i[0] - p[0]) ** 2 + (i[1] - p[1]) ** 2 + (i[2] - p[2]) ** 2
            )
            p = i

        if self.gcode == 0:
            # FIXME calculate the correct time with the feed direction
            # and acceleration
            block.time += length / self.feedmax_x
            self.totalTime += length / self.feedmax_x
            block.rapid += length
        elif ((self.gcode == 1 or self.gcode == 2 or self.gcode == 3)
              and self.feed > 0):
            block.time += length / self.feed
            self.totalTime += length / self.feed
        else:
            try:
                if self.feedmode == 94:
                    # Normal mode
                    t = length / self.feed
                elif self.feedmode == 93:
                    # Inverse mode
                    t = length * self.feed
                block.time += t
                self.totalTime += t
            except Exception:
                pass
            block.length += length

        self.totalLength += length

    # ----------------------------------------------------------------------
    def pathMargins(self, block):
        if block.enable:
            self.bounds["xmin"] = min(self.bounds["xmin"], block.xmin)
            self.bounds["ymin"] = min(self.bounds["ymin"], block.ymin)
            self.bounds["zmin"] = min(self.bounds["zmin"], block.zmin)
            self.bounds["xmax"] = max(self.bounds["xmax"], block.xmax)
            self.bounds["ymax"] = max(self.bounds["ymax"], block.ymax)
            self.bounds["zmax"] = max(self.bounds["zmax"], block.zmax)

        self.bounds["axmin"] = min(self.bounds["axmin"], block.xmin)
        self.bounds["aymin"] = min(self.bounds["aymin"], block.ymin)
        self.bounds["azmin"] = min(self.bounds["azmin"], block.zmin)
        self.bounds["axmax"] = max(self.bounds["axmax"], block.xmax)
        self.bounds["aymax"] = max(self.bounds["aymax"], block.ymax)
        self.bounds["azmax"] = max(self.bounds["azmax"], block.zmax)

    # ----------------------------------------------------------------------
    # Instead of the current code, override with the custom user lines
    # @param program a list of lines to execute
    # @return the new list of lines
    # ----------------------------------------------------------------------
    @staticmethod
    def compile(program):
        lines = []
        for j, line in enumerate(program):
            newcmd = []
            cmds = CNC.compileLine(line)
            if cmds is None:
                continue
            if isinstance(cmds, str):
                cmds = CNC.breakLine(cmds)
            else:
                # either CodeType or tuple, list[] append it as is
                lines.append(cmds)
                continue

            for cmd in cmds:
                c = cmd[0]
                try:
                    value = float(cmd[1:])
                except Exception:
                    value = 0.0
                if c.upper() in ("F", "X", "Y", "Z", "I", "J", "K", "R", "P"):
                    cmd = CNC.fmt(c, value)
                else:
                    opt = ERROR_HANDLING.get(cmd.upper(), 0)
                    if opt == SKIP:
                        cmd = None

                if cmd is not None:
                    newcmd.append(cmd)
            lines.append("".join(newcmd))
        return lines

# =============================================================================
# Block of g-code commands. A gcode file is represented as a list of blocks
# - Commands are grouped as (non motion commands Mxxx)
# - Basic shape from the first rapid move command to the last rapid z raise
#   above the working surface
#
# Inherits from list and contains:
#   - a list list of gcode lines
#   - (imported shape)
# =============================================================================
class Block(list):
    def __init__(self, name=None):
        # Copy constructor
        if isinstance(name, Block):
            self.copy(name)
            return
        self._name = name
        self.foil = {}  # Editable project properties; never emitted as machine commands
        self.enable = True  # Enabled/Visible in drawing
        self.expand = False  # Expand in editor
        self.color = None  # Custom color for path
        self.passes = 1    # Number of times to repeat the cut
        self._path = []  # canvas drawing paths
        self._xyzPaths = []  # cached motion geometry [(xyz, gcode), ...]
        self._xyzVersion = -1  # GCode._drawVersion when cache was built
        self.sx = self.sy = self.sz = 0  # start  coordinates
        # (entry point first non rapid motion)
        self.ex = self.ey = self.ez = 0  # ending coordinates
        self.resetPath()

    # ----------------------------------------------------------------------
    def copy(self, src):
        from copy import deepcopy
        self.foil = deepcopy(getattr(src, "foil", {}))
        self._name = src._name
        self.enable = src.enable
        self.expand = src.expand
        self.color = src.color
        self.passes = src.passes
        self[:] = src[:]
        self._path = []
        self._xyzPaths = []
        self._xyzVersion = -1
        self.sx = src.sx
        self.sy = src.sy
        self.sz = src.sz
        self.ex = src.ex
        self.ey = src.ey
        self.ez = src.ez

    # ----------------------------------------------------------------------
    def name(self):
        return self._name is None and "block" or self._name

    # ----------------------------------------------------------------------
    # @return name without the operation
    # ----------------------------------------------------------------------
    def nameNop(self):
        name = self.name()
        pat = OPPAT.match(name)
        if pat is None:
            return name
        else:
            return pat.group(1).strip()

    # ----------------------------------------------------------------------
    def header(self):
        e = (
            self.expand
            and Unicode.BLACK_DOWN_POINTING_TRIANGLE
            or Unicode.BLACK_RIGHT_POINTING_TRIANGLE
        )
        v = self.enable and Unicode.BALLOT_BOX_WITH_X or Unicode.BALLOT_BOX
        p = f" \u00d7{self.passes}" if self.passes > 1 else ""
        try:
            return f"{e} {v} {self.name()}{p} - [{len(self)}]"
        except UnicodeDecodeError:
            return " ".join([
                f"{e} {v} {self.name().decode('ascii', 'replace')}{p} -",
                f"[{int(len(self))}]"
            ])  # TODO: is this OK?

    # ----------------------------------------------------------------------
    def write_header(self):
        header = ""
        header += f"(Block-name: {self.name()})\n"
        header += f"(Block-expand: {int(self.expand)})\n"
        header += f"(Block-enable: {int(self.enable)})\n"
        if self.color:
            header += f"(Block-color: {self.color})\n"
        if self.passes > 1:
            header += f"(Block-passes: {self.passes})\n"
        return header

    def write(self, f):
        f.write(self.write_header())
        for line in self:
            if self.enable:
                f.write(f"{line}\n")
            else:
                f.write(
                    f"(Block-X: {line.replace('(', '[').replace(')', ']')})\n")


    # ----------------------------------------------------------------------
    # Create a block from a dump object from unpickler
    # ----------------------------------------------------------------------
    @staticmethod
    def load(obj):
        name, enable, expand, color, code = obj
        block = Block(name)
        block.enable = enable
        block.expand = expand
        block.color = color
        block.extend(code)
        return block

    # ----------------------------------------------------------------------
    def append(self, line):
        if line.startswith("(Block-"):
            pat = BLOCKPAT.match(line)
            if pat:
                name, value = pat.groups()
                value = value.strip()
                if name == "name":
                    self._name = value
                    return
                elif name == "expand":
                    self.expand = bool(int(value))
                    return
                elif name == "enable":
                    self.enable = bool(int(value))
                    return
                elif name == "tab":
                    # Handled elsewhere
                    return
                elif name == "color":
                    self.color = value
                    return
                elif name == "passes":
                    try:
                        self.passes = max(1, int(value))
                    except ValueError:
                        pass
                    return
                elif name == "X":  # uncomment
                    list.append(
                        self, value.replace("[", "(").replace("]", ")"))
                    return
        if self._name is None and ("id:" in line) and ("End" not in line):
            pat = IDPAT.match(line)
            if pat:
                self._name = pat.group(1)
        list.append(self, line)

    # ----------------------------------------------------------------------
    def resetPath(self):
        del self._path[:]
        self.xmin = self.ymin = self.zmin = 1000000.0
        self.xmax = self.ymax = self.zmax = -1000000.0
        self.length = 0.0  # cut length
        self.rapid = 0.0  # rapid length
        self.time = 0.0

    # ----------------------------------------------------------------------
    def addPath(self, p):
        self._path.append(p)

    # ----------------------------------------------------------------------
    def path(self, item):
        try:
            return self._path[item]
        except Exception:
            return None

    # ----------------------------------------------------------------------
    def startPath(self, x, y, z):
        self.sx = x
        self.sy = y
        self.sz = z

    # ----------------------------------------------------------------------
    def endPath(self, x, y, z):
        self.ex = x
        self.ey = y
        self.ez = z

    # ----------------------------------------------------------------------
    def pathMargins(self, xyz):
        self.xmin = min(self.xmin, min(i[0] for i in xyz))
        self.ymin = min(self.ymin, min(i[1] for i in xyz))
        self.zmin = min(self.zmin, min(i[2] for i in xyz))
        self.xmax = max(self.xmax, max(i[0] for i in xyz))
        self.ymax = max(self.ymax, max(i[1] for i in xyz))
        self.zmax = max(self.zmax, max(i[2] for i in xyz))


# =============================================================================
# Gcode file
# =============================================================================
class GCode:
    LOOP_MERGE = False

    # ----------------------------------------------------------------------
    def __init__(self):
        self.cnc = CNC()
        self.header = "M5\nG21 G90 G17 G94"
        self.footer = "M5"
        self.undoredo = undo.UndoRedo()
        self.vars = {}  # local variables
        self.init()

    # ----------------------------------------------------------------------
    def init(self):
        self.filename = ""
        self.blocks = []  # list of blocks
        self.foil_layers = []  # Explicit project layers, including empty layers
        self.vars.clear()
        self.undoredo.reset()
        self._lastModified = 0
        self._modified = False
        self._drawVersion = 0  # monotonic counter; canvas cache key

    # ----------------------------------------------------------------------
    def isModified(self):
        return self._modified

    # ----------------------------------------------------------------------
    def resetModified(self):
        self._modified = False

    # ----------------------------------------------------------------------
    def __getitem__(self, item):
        return self.blocks[item]

    # ----------------------------------------------------------------------
    def __setitem__(self, item, value):
        self.blocks[item] = value

    # ----------------------------------------------------------------------
    # Evaluate code expressions if any and return line
    # ----------------------------------------------------------------------
    def evaluate(self, line, app=None):
        if isinstance(line, int):
            return None

        elif isinstance(line, list):
            for i, expr in enumerate(line):
                if isinstance(expr, types.CodeType):
                    result = eval(expr, CNC.vars, self.vars)
                    if isinstance(result, float):
                        line[i] = str(round(result, CNC.digits))
                    else:
                        line[i] = str(result)
            return "".join(line)

        elif isinstance(line, types.CodeType):
            import traceback  # noqa: F401

            v = self.vars
            v["os"] = os
            v["app"] = app
            return eval(line, CNC.vars, self.vars)

        else:
            return line

    # ----------------------------------------------------------------------
    # add new line to list create block if necessary
    # ----------------------------------------------------------------------
    def _addLine(self, line):
        if line.startswith("(Block-name:"):
            self._blocksExist = True
            pat = BLOCKPAT.match(line)
            if pat:
                value = pat.group(2).strip()
                if not self.blocks or len(self.blocks[-1]):
                    self.blocks.append(Block(value))
                else:
                    self.blocks[-1]._name = value
                return

        if not self.blocks:
            self.blocks.append(Block("Header"))

        cmds = CNC.parseLine(line)
        if cmds is None:
            self.blocks[-1].append(line)
            return

        self.cnc.motionStart(cmds)

        # rapid move up = end of block
        if self._blocksExist:
            self.blocks[-1].append(line)
        elif self.cnc.gcode == 0 and self.cnc.dz > 0.0:
            self.blocks[-1].append(line)
            self.blocks.append(Block())
        elif self.cnc.gcode == 0 and len(self.blocks) == 1:
            self.blocks.append(Block())
            self.blocks[-1].append(line)
        else:
            self.blocks[-1].append(line)

        self.cnc.motionEnd()

    # ----------------------------------------------------------------------
    # Load a file into editor
    # ----------------------------------------------------------------------
    def load(self, filename=None):
        if filename is None:
            filename = self.filename
        self.init()
        self.filename = filename
        try:
            f = open(self.filename)
        except Exception:
            return False
        self._lastModified = os.stat(self.filename).st_mtime
        self.cnc.initPath()
        self.cnc.resetAllMargins()
        self._blocksExist = False
        for line in f:
            self._addLine(line[:-1].replace("\x0d", ""))
        self._trim()
        f.close()
        return True

    # ----------------------------------------------------------------------
    # Save to a file
    # ----------------------------------------------------------------------
    def save(self, filename=None):
        if filename is not None:
            self.filename = filename
        try:
            f = open(self.filename, "w")
        except Exception:
            return False

        for block in self.blocks:
            block.write(f)
        f.close()
        self._lastModified = os.stat(self.filename).st_mtime
        self._modified = False
        return True

    # ----------------------------------------------------------------------
    # Save in TXT format
    # -Enabled Blocks only
    # -Cleaned from bCNC metadata and comments
    # -Uppercase
    # ----------------------------------------------------------------------
    def saveTXT(self, filename):
        txt = open(filename, "w")
        for block in self.blocks:
            if block.enable:
                for line in block:
                    cmds = CNC.parseLine(line)
                    if cmds is None:
                        continue
                    txt.write(f"{line.upper()}\n")
        txt.close()
        return True

    # ----------------------------------------------------------------------
    def addBlockFromString(self, name, text):
        if not text:
            return
        block = Block(name)
        block.extend(text.splitlines())
        self.blocks.append(block)

    # ----------------------------------------------------------------------
    # If empty insert a header and a footer
    # ----------------------------------------------------------------------
    def headerFooter(self):
        if not self.blocks:
            self.addBlockFromString("Header", self.header)
            self.addBlockFromString("Footer", self.footer)
            return True
        return False

    # ----------------------------------------------------------------------
    # Load DXF file into gcode
    # ----------------------------------------------------------------------
    def importDXF(self, filename):
        try:
            dxf = DXF(filename, "r")
        except Exception:
            return False
        self.filename = ""

        dxf.readFile()
        dxf.close()

        # prepare dxf file
        dxf.sort()
        dxf.convert2Polylines()
        dxf.expandBlocks()

        empty = len(self.blocks) == 0
        if empty:
            self.addBlockFromString("Header", self.header)

        if CNC.inch:
            units = DXF.INCHES
        else:
            units = DXF.MILLIMETERS

        undoinfo = []
        for name, layer in dxf.layers.items():
            enable = not bool(layer.isFrozen())
            entities = dxf.entities(name)
            if not entities:
                continue
            self.importEntityPoints(None, entities, name, enable, layer.color())
            path = Path(name)
            path.fromDxf(dxf, entities, units)
            path.removeZeroLength()
            if path.color is None:
                path.color = layer.color()
            if path.color == "#FFFFFF":
                path.color = None
            opath = path.split2contours(
                0.0001
            )  # Lowered accuracy due to problems interfacing arcs and lines in DXF
            if not opath:
                continue
            while opath:
                li = 0
                llen = 0.0
                for i, p in enumerate(opath):
                    if p.length() > llen:
                        li = i
                        llen = p.length()
                longest = opath.pop(li)
                longest.directionSet(
                    1
                )  # turn path to CW (conventional when milling outside)

                # Can be time consuming
                if GCode.LOOP_MERGE:
                    longest.mergeLoops(opath)

                undoinfo.extend(self.importPath(None, longest, None, enable))

            undoinfo.extend(self.importPath(None, opath, None, enable))

        if empty:
            self.addBlockFromString("Footer", self.footer)
        return True

    # ----------------------------------------------------------------------
    # Save in DXF format
    # ----------------------------------------------------------------------
    def saveDXF(self, filename):
        try:
            dxf = DXF(filename, "w")
        except Exception:
            return False
        if CNC.inch:
            dxf.units = DXF.INCHES
        else:
            dxf.units = DXF.MILLIMETERS
        dxf.writeHeader()
        for block in self.blocks:
            name = block.name()
            if ":" in name:
                name = name.split(":")[0]
            for line in block:
                cmds = CNC.parseLine(line)
                if cmds is None:
                    continue
                self.cnc.motionStart(cmds)
                if self.cnc.gcode == 1:  # line
                    dxf.line(
                        self.cnc.x,
                        self.cnc.y,
                        self.cnc.xval,
                        self.cnc.yval,
                        name
                    )
                elif self.cnc.gcode in (2, 3):  # arc
                    xc, yc = self.cnc.motionCenter()
                    sphi = math.atan2(self.cnc.y - yc, self.cnc.x - xc)
                    ephi = math.atan2(self.cnc.yval - yc, self.cnc.xval - xc)
                    if ephi <= sphi + 1e-10:
                        ephi += 2.0 * math.pi
                    if self.cnc.gcode == 2:
                        dxf.arc(
                            xc,
                            yc,
                            self.cnc.rval,
                            math.degrees(ephi),
                            math.degrees(sphi),
                            name,
                        )
                    else:
                        dxf.arc(
                            xc,
                            yc,
                            self.cnc.rval,
                            math.degrees(sphi),
                            math.degrees(ephi),
                            name,
                        )
                self.cnc.motionEnd()
        dxf.writeEOF()
        dxf.close()
        return True

    # ----------------------------------------------------------------------
    # Get scaling factor for SVG files
    # ----------------------------------------------------------------------
    def SVGscale(self, dpi=96.0):  # same as inkscape 0.9x (according to jscut)
        if CNC.inch:
            return 1.0 / dpi
        return 25.4 / dpi

    # ----------------------------------------------------------------------
    # Load SVG file into gcode
    # ----------------------------------------------------------------------
    def importSVG(self, filename):
        svgcode = SVGcode(filename)

        empty = len(self.blocks) == 0
        if empty:
            self.addBlockFromString("Header", self.header)

        # FIXME: UI to set SVG samples_per_unit
        ppi = 96.0  # 96 pixels per inch.
        scale = self.SVGscale(ppi)
        # 50 points/mm → 0.02 mm chord error; more than adequate for CNC.
        # Reduce further if import is still slow on very long paths.
        samples_per_unit = 50.0
        for path in svgcode.get_gcode(scale,
                                      samples_per_unit,
                                      CNC.digits,
                                      ppi=ppi):
            # Warning entry injected when Text elements were found in the SVG
            if path.get("skipped_text"):
                names = ", ".join(f'"{t}"' for t in path["skipped_text"])
                warn = Block("WARNING: SVG text not imported")
                warn.enable = False
                warn.append(
                    f"(SVG contained {len(path['skipped_text'])} text element(s)"
                    f" that cannot be converted to toolpaths: {names})")
                warn.append(
                    "(Text requires a font renderer. To include text, open the"
                    " SVG in Inkscape, select all text, then use)")
                warn.append(
                    "(  Path > Object to Path   to convert glyphs to bezier"
                    " curves, then re-import.)")
                self.blocks.append(warn)
                continue
            lines = path["path"]   # list of G-code strings from path2gcode
            if not lines:
                continue
            block = Block(path["id"])
            block.extend(lines)
            self.blocks.append(block)

        if empty:
            self.addBlockFromString("Footer", self.footer)
        return True

    # ----------------------------------------------------------------------
    # get document margins
    # ----------------------------------------------------------------------
    def getMargins(self):
        # Get bounding box of document
        minx, miny, maxx, maxy = 0, 0, 0, 0
        for i, block in enumerate(self.blocks):
            paths = self.toPath(i)
            for path in paths:
                minx2, miny2, maxx2, maxy2 = path.bbox()
                minx, miny, maxx, maxy = (
                    min(minx, minx2),
                    min(miny, miny2),
                    max(maxx, maxx2),
                    max(maxy, maxy2),
                )
        return minx, miny, maxx, maxy

    # ----------------------------------------------------------------------
    # Save in SVG format
    # ----------------------------------------------------------------------
    def saveSVG(self, filename):
        try:
            svg = open(filename, "w")
        except Exception:
            return False

        padding = 10
        scale = self.SVGscale()

        # Get bounding box of document
        minx, miny, maxx, maxy = self.getMargins()

        svg.write(
            "<!-- SVG generated by bCNC: "
            "https://github.com/vlachoudis/bCNC -->\n"
        )
        svg.write(
            f"<svg viewBox=\"{(minx * scale) - padding} "
            f"{(-maxy * scale) - padding} "
            f"{((maxx - minx) * scale) + padding * 2} "
            f"{((maxy - miny) * scale) + padding * 2}\">\n"
        )

        def svgLine(scale, px, py, type_="L"):
            return f"\t{type_} {px * scale} {py * scale}\n"

        def svgArc(scale, gcode, r, ax, ay, bx, by, cx, cy):
            sphi = math.atan2(ay - yc, ax - xc)
            ephi = math.atan2(by - yc, bx - xc)
            arcSweep = ephi - sphi
            arcSweep = 0 if arcSweep <= math.radians(180) else 1
            # Arc
            if gcode == 2:
                if ephi <= sphi + 1e-10:
                    ephi += 2.0 * math.pi
                return "\tA {} {} {} {} {} {} {}\n".format(
                    r * scale,
                    r * scale,
                    0,
                    arcSweep,
                    1,
                    bx * scale,
                    by * scale,
                )
            else:
                if ephi <= sphi + 1e-10:
                    ephi += 2.0 * math.pi
                return "\tA {} {} {} {} {} {} {}\n".format(
                    r * scale,
                    r * scale,
                    0,
                    arcSweep,
                    0,
                    bx * scale,
                    by * scale,
                )

        for block in self.blocks:

            name = block.name()
            color = block.color
            if color is None:
                color = "black"
            width = 2
            if ":" in name:
                name = name.split(":")[0]
            svgpath = ""
            lastx, lasty = 0, 0
            firstx, firsty = None, None

            # Write paths
            for line in block:
                cmds = CNC.parseLine(line)
                if cmds is None:
                    continue
                self.cnc.motionStart(cmds)

                if self.cnc.gcode == 0:  # rapid line (move)
                    svgpath += svgLine(
                        scale, self.cnc.xval, -self.cnc.yval, "M")
                else:
                    lastx, lasty = self.cnc.xval, self.cnc.yval
                    if firstx is None:
                        firstx, firsty = self.cnc.x, self.cnc.y

                if self.cnc.gcode == 1:  # line
                    svgpath += svgLine(scale, self.cnc.xval, -self.cnc.yval)

                elif self.cnc.gcode in (2, 3):  # arc
                    xc, yc = self.cnc.motionCenter()

                    # In case of full circle, we need to split circle
                    # in two arcs:
                    midx = self.cnc.x
                    midy = self.cnc.y
                    if (
                        self.cnc.y == self.cnc.yval
                        and self.cnc.x == self.cnc.xval
                    ):  # is full circle?
                        midx = self.cnc.x + (xc - self.cnc.x) * 2
                        midy = self.cnc.y + (yc - self.cnc.y) * 2
                        svgpath += svgArc(
                            scale,
                            self.cnc.gcode,
                            self.cnc.rval,
                            self.cnc.x,
                            -self.cnc.y,
                            midx,
                            -midy,
                            xc,
                            -yc,
                        )
                    # Finish arc
                    svgpath += svgArc(
                        scale,
                        self.cnc.gcode,
                        self.cnc.rval,
                        midx,
                        -midy,
                        self.cnc.xval,
                        -self.cnc.yval,
                        xc,
                        -yc,
                    )
                self.cnc.motionEnd()

            if firstx == lastx and firsty == lasty:
                svgpath += "\tZ\n"

            if len(svgpath) > 0:
                for line in block.write_header().splitlines():
                    svg.write(f"\t<!-- {line} -->\n")
                svg.write(
                    f"\t<path d=\"\n{svgpath}\t\" stroke=\"{color}\" "
                    f"stroke-width=\"{width}\" fill=\"none\" />\n"
                )

        svg.write("</svg>\n")
        svg.close()
        return True

    # ----------------------------------------------------------------------
    # Import POINTS from entities
    # ----------------------------------------------------------------------
    def importEntityPoints(self, pos, entities, name, enable=True, color=None):
        undoinfo = []
        i = 0
        while i < len(entities):
            if entities[i].type != "POINT":
                i += 1
                continue

            block = Block(f"{name} [P]")
            block.enable = enable

            block.color = entities[i].color()
            if block.color is None:
                block.color = color

            x, y = entities[i].start()
            block.append(f"g0 {self.fmt('x', x, 7)} {self.fmt('y', y, 7)}")
            block.append(CNC.zenter(self.cnc["surface"]))
            block.append(CNC.zsafe())
            undoinfo.append(self.addBlockUndo(pos, block))
            if pos is not None:
                pos += 1
            del entities[i]

        return undoinfo

    # ----------------------------------------------------------------------
    # convert a block to path
    # ----------------------------------------------------------------------
    def toPath(self, bid):
        block = self.blocks[bid]
        paths = []
        path = Path(block.name())
        self.initPath(bid)
        start = Vector(self.cnc.x, self.cnc.y)

        # get only first path that enters the surface
        # ignore the deeper ones
        passno = 0
        for line in block:
            # flatten helical paths
            line = re.sub(r"\s?z-?[0-9\.]+", "", line)

            # break after first depth pass
            if line == "( ---------- cut-here ---------- )":
                passno = 0
                if path:
                    paths.append(path)
                    path = Path(block.name())
            if line[:5] == "(pass":
                passno += 1
            if passno > 1:
                continue

            cmds = CNC.parseLine(line)
            if cmds is None:
                continue
            self.cnc.motionStart(cmds)
            end = Vector(self.cnc.xval, self.cnc.yval)
            if self.cnc.gcode == 0:  # rapid move (new block)
                if path:
                    paths.append(path)
                    path = Path(block.name())
            elif self.cnc.gcode == 1:  # line
                if self.cnc.dx != 0.0 or self.cnc.dy != 0.0:
                    path.append(Segment(1, start, end))
            elif self.cnc.gcode in (2, 3):  # arc
                xc, yc = self.cnc.motionCenter()
                center = Vector(xc, yc)
                path.append(Segment(self.cnc.gcode, start, end, center))
            self.cnc.motionEnd()
            start = end
        if path:
            paths.append(path)
        return paths

    # ----------------------------------------------------------------------
    # create a block from Path
    # @param z      I       ending depth
    # @param zstart I       starting depth
    # ----------------------------------------------------------------------
    def fromPath(self, path, block=None, z=0, *, feed=None, safe=None):
        """Serialize planar artwork; milling ramps, tabs and depth passes are unsupported."""
        from PlotterPath import path_to_block
        return path_to_block(path, block, z=z, feed=self.cnc['cutfeed'] if feed is None else feed,
                             safe=self.cnc['safe'] if safe is None else safe, digits=CNC.digits)

    # ----------------------------------------------------------------------
    # Import paths as block
    # return ids of blocks added in newblocks list if declared
    # ----------------------------------------------------------------------
    def importPath(
            self, pos, paths, newblocks=None, enable=True, multiblock=True):
        undoinfo = []
        if isinstance(paths, Path):
            block = self.fromPath(paths)
            block.enable = enable
            block.color = paths.color
            undoinfo.append(self.addBlockUndo(pos, block))
            if newblocks is not None:
                newblocks.append(pos)
        else:
            block = None
            for path in paths:
                if block is None:
                    block = Block(path.name)
                block = self.fromPath(path, block)
                if multiblock:
                    block.enable = enable
                    undoinfo.append(self.addBlockUndo(pos, block))
                    if newblocks is not None:
                        newblocks.append(pos)
                    if pos is not None:
                        pos += 1
                    block = None
            if not multiblock:
                block.enable = enable
                undoinfo.append(self.addBlockUndo(pos, block))
                if newblocks is not None:
                    newblocks.append(pos)
        return undoinfo

    # ----------------------------------------------------------------------
    # sync file timestamp
    # ----------------------------------------------------------------------
    def syncFileTime(self):
        try:
            self._lastModified = os.stat(self.filename).st_mtime
        except Exception:
            return False

    # ----------------------------------------------------------------------
    # Check if a new version exists
    # ----------------------------------------------------------------------
    def checkFile(self):
        try:
            return os.stat(self.filename).st_mtime > self._lastModified
        except Exception:
            return False

    # ----------------------------------------------------------------------
    def fmt(self, c, v, d=None):
        return self.cnc.fmt(c, v, d)

    # ----------------------------------------------------------------------
    def _trim(self):
        if not self.blocks:
            return
        # Delete last block if empty
        last = self.blocks[-1]
        if len(last) == 1 and len(last[0]) == 0:
            del last[0]
        if len(self.blocks[-1]) == 0:
            self.blocks.pop()

    # ----------------------------------------------------------------------
    # Undo/Redo operations
    # ----------------------------------------------------------------------
    def undo(self):
        self.undoredo.undo()
        self._drawVersion += 1

    # ----------------------------------------------------------------------
    def redo(self):
        self.undoredo.redo()
        self._drawVersion += 1

    # ----------------------------------------------------------------------
    def addUndo(self, undoinfo, msg=None):
        if not undoinfo:
            return
        self.undoredo.add(undoinfo, msg)
        self._modified = True
        self._drawVersion += 1

    # ----------------------------------------------------------------------
    def canUndo(self):
        return self.undoredo.canUndo()

    # ----------------------------------------------------------------------
    def canRedo(self):
        return self.undoredo.canRedo()

    # ----------------------------------------------------------------------
    # Change all lines in editor
    # ----------------------------------------------------------------------
    def setLinesUndo(self, lines):
        undoinfo = (self.setLinesUndo, list(self.lines()))
        # Delete all blocks and create new ones
        del self.blocks[:]
        self.cnc.initPath()
        self._blocksExist = False
        for line in lines:
            self._addLine(line)
        self._trim()
        return undoinfo

    # ----------------------------------------------------------------------
    def setAllBlocksUndo(self, blocks=[]):
        undoinfo = [self.setAllBlocksUndo, self.blocks]
        self.blocks = blocks
        return undoinfo

    # ----------------------------------------------------------------------
    # Change a single line in a block
    # ----------------------------------------------------------------------
    def setLineUndo(self, bid, lid, line):
        undoinfo = (self.setLineUndo, bid, lid, self.blocks[bid][lid])
        self.blocks[bid][lid] = line
        return undoinfo

    # ----------------------------------------------------------------------
    # Insert a new line into block
    # ----------------------------------------------------------------------
    def insLineUndo(self, bid, lid, line):
        undoinfo = (self.delLineUndo, bid, lid)
        block = self.blocks[bid]
        if lid >= len(block):
            block.append(line)
        else:
            block.insert(lid, line)
        return undoinfo

    # ----------------------------------------------------------------------
    # Delete line from block
    # ----------------------------------------------------------------------
    def delLineUndo(self, bid, lid):
        block = self.blocks[bid]
        undoinfo = (self.insLineUndo, bid, lid, block[lid])
        del block[lid]
        return undoinfo

    # ----------------------------------------------------------------------
    # Add a block
    # ----------------------------------------------------------------------
    def addBlockUndo(self, bid, block):
        if bid is None:
            bid = len(self.blocks)
        if bid >= len(self.blocks):
            undoinfo = (self.delBlockUndo, len(self.blocks))
            self.blocks.append(block)
        else:
            undoinfo = (self.delBlockUndo, bid)
            self.blocks.insert(bid, block)
        return undoinfo

    # ----------------------------------------------------------------------
    # Delete a whole block
    # ----------------------------------------------------------------------
    def delBlockUndo(self, bid):
        block = self.blocks.pop(bid)
        undoinfo = (self.addBlockUndo, bid, block)
        return undoinfo

    # ----------------------------------------------------------------------
    # Insert a list of other blocks from another gcode file probably
    # ----------------------------------------------------------------------
    def insBlocksUndo(self, bid, blocks):
        if bid is None or bid >= len(self.blocks):
            bid = len(self.blocks)
        undoinfo = (
            "Insert blocks", self.delBlocksUndo, bid, bid + len(blocks))
        self.blocks[bid:bid] = blocks
        return undoinfo

    # ----------------------------------------------------------------------
    # Delete a range of blocks
    # ----------------------------------------------------------------------
    def delBlocksUndo(self, from_, to_):
        blocks = self.blocks[from_:to_]
        undoinfo = ("Delete blocks", self.insBlocksUndo, from_, blocks)
        del self.blocks[from_:to_]
        return undoinfo

    # ----------------------------------------------------------------------
    # Insert blocks and push the undo info
    # ----------------------------------------------------------------------
    def insBlocks(self, bid, blocks, msg=""):
        if self.headerFooter():  # just in case
            bid = 1
        self.addUndo(self.insBlocksUndo(bid, blocks), msg)

    # ----------------------------------------------------------------------
    # Set block expand
    # ----------------------------------------------------------------------
    def setBlockExpandUndo(self, bid, expand):
        undoinfo = (self.setBlockExpandUndo, bid, self.blocks[bid].expand)
        self.blocks[bid].expand = expand
        return undoinfo

    # ----------------------------------------------------------------------
    # Set block state
    # ----------------------------------------------------------------------

    def _restoreBlockVisibilityUndo(self, bid, enabled, properties):
        block = self.blocks[bid]
        previous = (self._restoreBlockVisibilityUndo, bid, block.enable,
                    block.foil.copy())
        block.enable, block.foil = enabled, properties.copy()
        return previous

    # ----------------------------------------------------------------------
    # Set block color
    # ----------------------------------------------------------------------
    def setBlockColorUndo(self, bid, color):
        undoinfo = (self.setBlockColorUndo, bid, self.blocks[bid].color)
        self.blocks[bid].color = color
        return undoinfo

    # ----------------------------------------------------------------------
    # Set block repeat passes
    # ----------------------------------------------------------------------
    def setBlockPassesUndo(self, bid, passes):
        undoinfo = (self.setBlockPassesUndo, bid, self.blocks[bid].passes)
        self.blocks[bid].passes = passes
        return undoinfo


    # ----------------------------------------------------------------------
    # Swap two blocks
    # ----------------------------------------------------------------------
    def swapBlockUndo(self, a, b):
        undoinfo = (self.swapBlockUndo, a, b)
        tmp = self.blocks[a]
        self.blocks[a] = self.blocks[b]
        self.blocks[b] = tmp
        return undoinfo

    # ----------------------------------------------------------------------
    # Move block from location src to location dst
    # ----------------------------------------------------------------------
    def moveBlockUndo(self, src, dst):
        if src == dst:
            return None
        undoinfo = (self.moveBlockUndo, dst, src)
        if dst > src:
            self.blocks.insert(dst - 1, self.blocks.pop(src))
        else:
            self.blocks.insert(dst, self.blocks.pop(src))
        return undoinfo

    # ----------------------------------------------------------------------
    # Invert selected blocks
    # ----------------------------------------------------------------------
    def invertBlocksUndo(self, blocks):
        undoinfo = []
        first = 0
        last = len(blocks) - 1
        while first < last:
            undoinfo.append(self.swapBlockUndo(blocks[first], blocks[last]))
            first += 1
            last -= 1
        return undoinfo

    # ----------------------------------------------------------------------
    # Move block upwards
    # ----------------------------------------------------------------------
    def orderUpBlockUndo(self, bid):
        if bid == 0:
            return None
        undoinfo = (self.orderDownBlockUndo, bid - 1)
        # swap with the block above
        before = self.blocks[bid - 1]
        self.blocks[bid - 1] = self.blocks[bid]
        self.blocks[bid] = before
        return undoinfo

    # ----------------------------------------------------------------------
    # Move block downwards
    # ----------------------------------------------------------------------
    def orderDownBlockUndo(self, bid):
        if bid >= len(self.blocks) - 1:
            return None
        undoinfo = (self.orderUpBlockUndo, bid + 1)
        # swap with the block below
        after = self[bid + 1]
        self[bid + 1] = self[bid]
        self[bid] = after
        return undoinfo

    # ----------------------------------------------------------------------
    # Insert block lines
    # ----------------------------------------------------------------------
    def insBlockLinesUndo(self, bid, lines):
        undoinfo = (self.delBlockLinesUndo, bid)
        block = Block()
        for line in lines:
            block.append(line)
        self.blocks.insert(bid, block)
        return undoinfo

    # ----------------------------------------------------------------------
    # Delete a whole block lines
    # ----------------------------------------------------------------------
    def delBlockLinesUndo(self, bid):
        lines = [x for x in self.blocks[bid]]
        undoinfo = (self.insBlockLinesUndo, bid, lines)
        del self.blocks[bid]
        return undoinfo

    # ----------------------------------------------------------------------
    # Set Block name
    # ----------------------------------------------------------------------
    def setBlockNameUndo(self, bid, name):
        undoinfo = (self.setBlockNameUndo, bid, self.blocks[bid]._name)
        self.blocks[bid]._name = name
        return undoinfo

    # ----------------------------------------------------------------------
    # Replace the lines of a block
    # ----------------------------------------------------------------------
    def setBlockLinesUndo(self, bid, lines):
        block = self.blocks[bid]
        undoinfo = (self.setBlockLinesUndo, bid, block[:])
        del block[:]
        block.extend(lines)
        return undoinfo

    # ----------------------------------------------------------------------
    # Move line upwards
    # ----------------------------------------------------------------------
    def orderUpLineUndo(self, bid, lid):
        if lid == 0:
            return None
        block = self.blocks[bid]
        undoinfo = (self.orderDownLineUndo, bid, lid - 1)
        block.insert(lid - 1, block.pop(lid))
        return undoinfo

    # ----------------------------------------------------------------------
    # Move line downwards
    # ----------------------------------------------------------------------
    def orderDownLineUndo(self, bid, lid):
        block = self.blocks[bid]
        if lid >= len(block) - 1:
            return None
        undoinfo = (self.orderUpLineUndo, bid, lid + 1)
        block.insert(lid + 1, block.pop(lid))
        return undoinfo

    # ----------------------------------------------------------------------
    # Return string representation of whole file
    # ----------------------------------------------------------------------
    def __repr__(self):
        return "\n".join(list(self.lines()))

    # ----------------------------------------------------------------------
    # Iterate over the items
    # ----------------------------------------------------------------------
    def iterate(self, items):
        for bid, lid in items:
            if lid is None:
                block = self.blocks[bid]
                for i in range(len(block)):
                    yield bid, i
            else:
                yield bid, lid

    # ----------------------------------------------------------------------
    # Iterate over all lines
    # ----------------------------------------------------------------------
    def lines(self):
        for block in self.blocks:
            yield from block

    # ----------------------------------------------------------------------
    # initialize cnc path based on block bid
    # ----------------------------------------------------------------------
    def initPath(self, bid=0):
        if bid == 0:
            self.cnc.initPath()
        else:
            # Use the ending point of the previous block
            # since the starting (sxyz is after the rapid motion)
            block = self.blocks[bid - 1]
            self.cnc.initPath(block.ex, block.ey, block.ez)

    # ----------------------------------------------------------------------
    # Move blocks/lines up
    # ----------------------------------------------------------------------
    def orderUp(self, items):
        sel = []  # new selection
        undoinfo = []
        for bid, lid in items:
            if isinstance(lid, int):
                undoinfo.append(self.orderUpLineUndo(bid, lid))
                sel.append((bid, lid - 1))
            elif lid is None:
                undoinfo.append(self.orderUpBlockUndo(bid))
                if bid == 0:
                    return items
                else:
                    sel.append((bid - 1, None))
        self.addUndo(undoinfo, "Move Up")
        return sel

    # ----------------------------------------------------------------------
    # Move blocks/lines down
    # ----------------------------------------------------------------------
    def orderDown(self, items):
        sel = []  # new selection
        undoinfo = []
        for bid, lid in reversed(items):
            if isinstance(lid, int):
                undoinfo.append(self.orderDownLineUndo(bid, lid))
                sel.append((bid, lid + 1))
            elif lid is None:
                undoinfo.append(self.orderDownBlockUndo(bid))
                if bid >= len(self.blocks) - 1:
                    return items
                else:
                    sel.append((bid + 1, None))
        self.addUndo(undoinfo, "Move Down")
        sel.reverse()
        return sel

    # ----------------------------------------------------------------------
    # Return information for a block
    # return XXX
    # ----------------------------------------------------------------------
    def info(self, bid):
        paths = self.toPath(bid)
        if not paths:
            return None, 1
        if len(paths) > 1:
            closed = paths[0].isClosed()
            return len(paths), paths[0]._direction(closed)
        else:
            closed = paths[0].isClosed()
            return int(closed), paths[0]._direction(closed)

    # ----------------------------------------------------------------------
    # Modify the lines according to the supplied function and arguments
    # ----------------------------------------------------------------------
    def modify(self, items, func, tabFunc, *args):
        undoinfo = []
        old = {}  # Motion commands: Last value
        new = {}  # Motion commands: New value
        relative = False

        for bid, lid in self.iterate(items):
            block = self.blocks[bid]

            if isinstance(lid, int):
                cmds = CNC.parseLine(block[lid])
                if cmds is None:
                    continue
                self.cnc.motionStart(cmds)

                # Collect all values
                new.clear()
                for cmd in cmds:
                    if cmd.upper() == "G91":
                        relative = True
                    if cmd.upper() == "G90":
                        relative = False
                    c = cmd[0].upper()
                    # record only coordinates commands
                    if c not in "XYZIJKR":
                        continue
                    try:
                        new[c] = old[c] = float(cmd[1:]) * self.cnc.unit
                    except Exception:
                        new[c] = old[c] = 0.0

                # Modify values with func
                if func(new, old, relative, *args):
                    # Reconstruct new line
                    newcmd = []
                    present = ""
                    for cmd in cmds:
                        c = cmd[0].upper()
                        if c in "XYZIJKR":  # Coordinates
                            newcmd.append(self.fmt(c, new[c] / self.cnc.unit))
                        # Motion
                        elif c == "G" and int(cmd[1:]) in (0, 1, 2, 3):
                            newcmd.append(f"G{int(self.cnc.gcode)}")
                        else:  # the rest leave unchanged
                            newcmd.append(cmd)
                        present += c
                    # Append motion commands if not exist and changed
                    check = "XYZ"
                    if "I" in new or "J" in new or "K" in new:
                        check += "IJK"
                    for c in check:
                        try:
                            if c not in present and new.get(c) != old.get(c):
                                newcmd.append(
                                    self.fmt(c, new[c] / self.cnc.unit))
                        except Exception:
                            pass
                    undoinfo.append(
                        self.setLineUndo(bid, lid, " ".join(newcmd)))
                self.cnc.motionEnd()
                # reset arc offsets
                for i in "IJK":
                    if i in old:
                        old[i] = 0.0

        # FIXME I should add it later, check all functions using it
        self.addUndo(undoinfo)

    # ----------------------------------------------------------------------
    # Move position by dx,dy,dz
    # ----------------------------------------------------------------------
    def moveFunc(self, new, old, relative, dx, dy, dz):
        if relative:
            return False
        changed = False
        if "X" in new:
            changed = True
            new["X"] += dx
        if "Y" in new:
            changed = True
            new["Y"] += dy
        if "Z" in new:
            changed = True
            new["Z"] += dz
        return changed

    # ----------------------------------------------------------------------
    # Move position by dx,dy,dz
    # ----------------------------------------------------------------------
    def moveLines(self, items, dx, dy, dz=0.0):
        return self.modify(items, self.moveFunc, None, dx, dy, dz)

    # ----------------------------------------------------------------------
    # Rotate position by c(osine), s(ine) of an angle around center (x0,y0)
    # ----------------------------------------------------------------------
    def rotateFunc(self, new, old, relative, c, s, x0, y0):
        if "X" not in new and "Y" not in new:
            return False
        x = getValue("X", new, old)
        y = getValue("Y", new, old)
        new["X"] = c * (x - x0) - s * (y - y0) + x0
        new["Y"] = s * (x - x0) + c * (y - y0) + y0

        if "I" in new or "J" in new:
            i = getValue("I", new, old)
            j = getValue("J", new, old)
            if self.cnc.plane in (XY, XZ):
                new["I"] = c * i - s * j
            if self.cnc.plane in (XY, YZ):
                new["J"] = s * i + c * j
        return True

    # ----------------------------------------------------------------------
    # Rotate items around optional center (on XY plane)
    # ang in degrees (counter-clockwise)
    # ----------------------------------------------------------------------
    def rotateLines(self, items, ang, x0=0.0, y0=0.0):
        a = math.radians(ang)
        c = math.cos(a)
        s = math.sin(a)
        if ang in (0.0, 90.0, 180.0, 270.0, -90.0, -180.0, -270.0):
            c = round(c)  # round numbers to avoid nasty extra digits
            s = round(s)
        return self.modify(items, self.rotateFunc, None, c, s, x0, y0)

    # ----------------------------------------------------------------------
    # Mirror Horizontal
    # ----------------------------------------------------------------------
    def mirrorHFunc(self, new, old, relative, *kw):
        changed = False
        for axis in "XI":
            if axis in new:
                new[axis] = -new[axis]
                changed = True
        if self.cnc.gcode in (2, 3):  # Change  2<->3
            self.cnc.gcode = 5 - self.cnc.gcode
            changed = True
        return changed

    # ----------------------------------------------------------------------
    # Mirror Vertical
    # ----------------------------------------------------------------------
    def mirrorVFunc(self, new, old, relative, *kw):
        changed = False
        for axis in "YJ":
            if axis in new:
                new[axis] = -new[axis]
                changed = True
        if self.cnc.gcode in (2, 3):  # Change  2<->3
            self.cnc.gcode = 5 - self.cnc.gcode
            changed = True
        return changed

    # ----------------------------------------------------------------------
    # Mirror horizontally/vertically
    # ----------------------------------------------------------------------
    def mirrorHLines(self, items):
        return self.modify(items, self.mirrorHFunc, None)

    # ----------------------------------------------------------------------
    def mirrorVLines(self, items):
        return self.modify(items, self.mirrorVFunc, None)

    # ----------------------------------------------------------------------
    # Scale position by (sx, sy) around center (x0, y0)
    # ----------------------------------------------------------------------
    def scaleFunc(self, new, old, relative, sx, sy, x0, y0):
        if "X" not in new and "Y" not in new:
            return False
        x = getValue("X", new, old)
        y = getValue("Y", new, old)
        new["X"] = (x - x0) * sx + x0
        new["Y"] = (y - y0) * sy + y0
        if "I" in new or "J" in new:
            i = getValue("I", new, old)
            j = getValue("J", new, old)
            new["I"] = i * sx
            new["J"] = j * sy
        return True

    # ----------------------------------------------------------------------
    # Scale selected items by sx (and optionally sy) around center (x0, y0)
    # If sy is None, uniform scaling is applied (sy = sx).
    # ----------------------------------------------------------------------
    def scaleLines(self, items, sx, sy=None, x0=0.0, y0=0.0):
        if sy is None:
            sy = sx
        return self.modify(items, self.scaleFunc, None, sx, sy, x0, y0)

    # ----------------------------------------------------------------------
    # Compile enabled cut blocks with source-line tracking
    # ----------------------------------------------------------------------
    def compile(self, queue, stopFunc=None):
        from PlotterPolicy import validate_plotter_commands
        validate_plotter_commands(self.blocks, self.cnc.startup,
                                  compile_line=CNC.compileLine, break_line=CNC.breakLine)
        paths = []

        def add(line, path):
            if line is not None:
                if isinstance(line, str):
                    queue.put(line + "\n")
                else:
                    queue.put(line)
            paths.append(path)

        self.initPath()
        for line in CNC.compile(self.cnc.startup.splitlines()):
            add(line, None)

        every = 1
        for i, block in enumerate(self.blocks):
            if not block.enable:
                continue
            block_lines = list(block) * block.passes
            for j_abs, line in enumerate(block_lines):
                j = j_abs % max(1, len(block))
                every -= 1
                if every <= 0:
                    if stopFunc is not None and stopFunc():
                        return None
                    every = 50

                newcmd = []
                cmds = CNC.compileLine(line)
                if cmds is None:
                    continue
                elif isinstance(cmds, str):
                    cmds = CNC.breakLine(cmds)
                else:
                    # either CodeType or tuple, list[] append at it as is
                    if (isinstance(cmds, types.CodeType)
                            or isinstance(cmds, int)):
                        add(cmds, None)
                    else:
                        add(cmds, (i, j))
                    continue

                self.cnc.motionStart(cmds)

                # FIXME append feed on cut commands. It will be obsolete
                # in grbl v1.0
                if CNC.appendFeed and self.cnc.gcode in (1, 2, 3):
                    # Check is not existing in cmds
                    for c in cmds:
                        if c[0] in ("f", "F"):
                            break
                    else:
                        cmds.append(
                            self.fmt("F", self.cnc.feed / self.cnc.unit))

                self.cnc.motionEnd()

                for cmd in cmds:
                    c = cmd[0]
                    try:
                        value = float(cmd[1:])
                    except Exception:
                        value = 0.0
                    if c.upper() in ("F", "X", "Y", "Z",
                                     "I", "J", "K", "R", "P"):
                        cmd = self.fmt(c, value)
                    else:
                        opt = ERROR_HANDLING.get(cmd.upper(), 0)
                        if opt == SKIP:
                            cmd = None
                    if cmd is not None:
                        newcmd.append(cmd)

                add("".join(newcmd), (i, j))

        return paths
