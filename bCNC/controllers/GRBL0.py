# GRBL <=0.9 motion controller plugin

from _GenericGRBL import _GenericGRBL


class Controller(_GenericGRBL):
    def __init__(self, master):
        self.gcode_case = 0
        self.has_override = False
        self.master = master

    def parseBracketAngle(self, line, cline):
        return self.parseStatus(line, cline)
