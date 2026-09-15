"""Persisted application settings and fallback firmware labels; no plugin loading."""
import Utils

class _Base:
    def __init__(self, master):
        self.master = master
        self.values = {}

    def __getitem__(self, name):
        return self.values.get(name, '')

    def __setitem__(self, name, value):
        self.values[name] = value

    def load(self):
        for key, kind, default, *_ in self.variables:
            reader = Utils.getFloat if kind in ('mm', 'float') else Utils.getInt if kind in ('int', 'bool') else Utils.getStr
            self.values[key] = reader(self.name, key, default)
        self.update()

    def save(self):
        Utils.addSection(self.name)
        for key, kind, default, *_ in self.variables:
            Utils.setStr(self.name, key, str(self.values.get(key, default)))

    def update(self):
        pass

class Config(_Base):

    def __init__(self, master):
        _Base.__init__(self, master)
        self.name = 'CNC'
        self.variables = [('units', 'bool', 0, _('Units (inches)')), ('acceleration_x', 'mm', 25.0, _('Acceleration x')), ('acceleration_y', 'mm', 25.0, _('Acceleration y')), ('acceleration_z', 'mm', 5.0, _('Acceleration z')), ('feedmax_x', 'mm', 3000.0, _('Feed max x')), ('feedmax_y', 'mm', 3000.0, _('Feed max y')), ('feedmax_z', 'mm', 2000.0, _('Feed max z')), ('travel_x', 'mm', 200, _('Travel x')), ('travel_y', 'mm', 200, _('Travel y')), ('travel_z', 'mm', 100, _('Travel z')), ('round', 'int', 4, _('Decimal digits')), ('accuracy', 'mm', 0.1, _('Plotting Arc accuracy')), ('startup', 'str', 'G90', _('Start up')), ('header', 'text', 'M5\nG21 G90 G17 G94', _('Header gcode')), ('footer', 'text', 'M5', _('Footer gcode'))]

    def update(self):
        self.master.inches = self['units']
        self.master.digits = int(self['round'])
        self.master.gcode.cnc.decimal = self.master.digits
        self.master.gcode.cnc.startup = self['startup']
        self.master.gcode.header = self['header']
        self.master.gcode.footer = self['footer']
        return False

class Controller(_Base):

    def __init__(self, master):
        _Base.__init__(self, master)
        self.name = 'Controller'
        self.variables = [('grbl_0', 'float', 10, _('$0 Step pulse time [us]')), ('grbl_1', 'int', 25, _('$1 Step idle delay [ms]')), ('grbl_2', 'int', 0, _('$2 Step port invert [mask]')), ('grbl_3', 'int', 0, _('$3 Direction port invert [mask]')), ('grbl_4', 'bool', 0, _('$4 Step enable invert')), ('grbl_5', 'bool', 0, _('$5 Limit pins invert')), ('grbl_6', 'bool', 0, _('$6 Probe pin invert')), ('grbl_10', 'int', 1, _('$10 Status report [mask]')), ('grbl_11', 'float', 0.01, _('$11 Junction deviation [mm]')), ('grbl_12', 'float', 0.002, _('$12 Arc tolerance [mm]')), ('grbl_13', 'bool', 0, _('$13 Report inches')), ('grbl_20', 'bool', 0, _('$20 Soft limits')), ('grbl_21', 'bool', 0, _('$21 Hard limits')), ('grbl_22', 'bool', 0, _('$22 Homing cycle')), ('grbl_23', 'int', 0, _('$23 Homing direction invert [mask]')), ('grbl_24', 'float', 25.0, _('$24 Homing feed [mm/min]')), ('grbl_25', 'float', 500.0, _('$25 Homing seek [mm/min]')), ('grbl_26', 'int', 250, _('$26 Homing debounce [ms]')), ('grbl_27', 'float', 1.0, _('$27 Homing pull-off [mm]')), ('grbl_30', 'float', 1000.0, _('$30 Max spindle speed [RPM]')), ('grbl_31', 'float', 0.0, _('$31 Min spindle speed [RPM]')), ('grbl_32', 'bool', 0, _('$32 Laser mode enable')), ('grbl_100', 'float', 250.0, _('$100 X steps/mm')), ('grbl_101', 'float', 250.0, _('$101 Y steps/mm')), ('grbl_102', 'float', 250.0, _('$102 Z steps/mm')), ('grbl_110', 'float', 500.0, _('$110 X max rate [mm/min]')), ('grbl_111', 'float', 500.0, _('$111 Y max rate [mm/min]')), ('grbl_112', 'float', 500.0, _('$112 Z max rate [mm/min]')), ('grbl_120', 'float', 10.0, _('$120 X acceleration [mm/sec^2]')), ('grbl_121', 'float', 10.0, _('$121 Y acceleration [mm/sec^2]')), ('grbl_122', 'float', 10.0, _('$122 Z acceleration [mm/sec^2]')), ('grbl_130', 'float', 200.0, _('$130 X max travel [mm]')), ('grbl_131', 'float', 200.0, _('$131 Y max travel [mm]')), ('grbl_132', 'float', 200.0, _('$132 Z max travel [mm]')), ('grbl_140', 'float', 200.0, _('$140 X homing pull-off [mm]')), ('grbl_141', 'float', 200.0, _('$141 Y homing pull-off [mm]')), ('grbl_142', 'float', 200.0, _('$142 Z homing pull-off [mm]'))]


class Tools:
    def __init__(self, gcode):
        self.gcode = gcode
        self.tools = {'CNC': Config(self), 'CONTROLLER': Controller(self)}

    def __getitem__(self, name):
        return self.tools[name.upper()]

    def loadConfig(self):
        for tool in self.tools.values():
            tool.load()

    def saveConfig(self):
        Utils.config.remove_option(Utils.__prg__, 'tool')
        for tool in self.tools.values():
            tool.save()
