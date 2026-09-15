"""GRBL dialect parsing and firmware discovery, independent of Tk and transport."""
from dataclasses import dataclass
from copy import copy
import math
import re
import time

MODES = ('AUTO', 'GRBL0', 'GRBL1', 'GRBLHAL')


@dataclass
class Firmware:
    mode: str = 'AUTO'
    family: str = 'Unknown'
    version: str = ''
    dialect: str = ''
    identified: bool = False
    jog: bool = False
    overrides: bool = False
    extended: bool = False
    report_inches: bool = False
    board: str = ''

    def __post_init__(self):
        self.started = time.monotonic()
        self.queries = set()
        self.last_wco = None
        self.last_mpos = None
        self.last_wpos = None
        self.options = set()
        self.mpg = False
        self.units_known = False
        self.manual = False
        self.alarms = {}
        self.errors = {}
        self.settings = {}

    def identify(self, family, version):
        match = re.match(r'(\d+)\.(\d+)', version)
        if not match: return
        major, minor = map(int, match.groups())
        if family == 'GRBL' and not (major == 0 and minor in (8, 9) or major == 1 and minor in (0, 1)):
            return
        self.family, self.version = family, version
        self.identified = True
        modern = family == 'grblHAL' or (major, minor) >= (1, 1)
        self.jog = self.overrides = modern
        # 1.0 status reports must still be observed, not guessed from the major digit.
        if (major, minor) < (1, 0): self.dialect = 'legacy'
        elif modern: self.dialect = 'modern'

    def observe(self, line):
        if line.startswith('[BOARD:'):
            self.board = line[7:-1]
        banner = re.match(r'^(GrblHAL|Grbl)\s+(\d+\.\d+[^\s]*)', line, re.I)
        if banner:
            self.identify('grblHAL' if banner[1].lower() == 'grblhal' else 'GRBL', banner[2])
        if line.startswith('[VER:'):
            version = line[5:].split(':', 1)[0]
            self.identify('grblHAL' if 'grblhal' in line.lower() or self.family == 'grblHAL' else 'GRBL', version)
        if line.startswith('[FIRMWARE:') and 'grblhal' in line.lower():
            self.identify('grblHAL', self.version or '1.1')
        if line.startswith('[NEWOPT:'):
            self.options.update(line[8:-1].split(','))
            # NEWOPT alone can also come from other forks. Preserve identity evidence.
            self.extended = self.family == 'grblHAL' and bool(self.options & {'RT+', 'RT-'})
        if self.family == 'grblHAL':
            self.extended = bool(self.options & {'RT+', 'RT-'})
            for prefix, target in (('[ALARMCODE:', self.alarms), ('[ERRORCODE:', self.errors), ('[SETTING:', self.settings)):
                if line.startswith(prefix):
                    code, _, description = line[len(prefix):-1].partition('|')
                    if code.isdigit():
                        if prefix == '[SETTING:':
                            fields = description.split('|')
                            if len(fields) >= 7:
                                target[int(code)] = dict(zip(('group','name','unit','datatype','format','minimum','maximum','reboot','nullable'), fields))
                        else: target[int(code)] = description.strip('|')
        if line.startswith('$13='):
            inches = line[4:].split()[0] == '1'
            if inches != self.report_inches:
                self.last_wco = self.last_mpos = self.last_wpos = None
            self.report_inches = inches
            self.units_known = True

    def queries_due(self, state):
        # Information queries are allowed only while idle; never reset/unlock to discover.
        if state.split(':')[0] != 'Idle' or self.mpg: return []
        queries = ['$G', '$$'] if self.version.startswith('0.8') else ['$I', '$G', '$$']
        if self.family == 'grblHAL': queries += ['$I+']
        if self.family == 'grblHAL' and 'ENUMS' in self.options: queries += ['$EA', '$EE', '$ES']
        pending = [q for q in queries if q not in self.queries]
        self.queries.update(pending)
        return pending

    @property
    def ready(self):
        return self.identified and self.last_wpos is not None and self.units_known and not self.mpg

    @property
    def timed_out(self):
        return not self.identified and time.monotonic() - self.started > 5

    @property
    def label(self):
        return f'{self.family} {self.version}' + (' · manual profile' if self.manual else '') if self.identified else ('Identification incomplete' if self.timed_out else 'Detecting firmware…')


def vector(text):
    values = tuple(float(v) for v in text.split(','))
    if len(values) < 2 or not all(math.isfinite(v) for v in values):
        raise ValueError('Invalid position report')
    return values


def status_report(line, firmware):
    candidate = copy(firmware)
    result = _parse_status(line, candidate)
    firmware.__dict__.update(candidate.__dict__)
    return result


def _parse_status(line, firmware):
    """Parse a complete report before deriving coordinates; unknown fields are preserved."""
    if not line.startswith('<') or not line.endswith('>'): raise ValueError('Incomplete status report')
    body = line[1:-1]
    if '|' in body:
        parts = body.split('|'); state = parts[0]
        fields = dict(part.split(':', 1) for part in parts[1:] if ':' in part)
        firmware.dialect = 'modern'
    else:
        state = body.split(',', 1)[0]
        fields = {m[1]:m[2] for m in re.finditer(r'(\w+):([^:]+?)(?=,\w+:|$)', body)}
        firmware.dialect = 'legacy'
    if not firmware.identified and firmware.mode != 'AUTO':
        family, version = ('grblHAL', '1.1') if firmware.mode == 'GRBLHAL' else ('GRBL', '0.9' if firmware.mode == 'GRBL0' else '1.1')
        firmware.identify(family, version)
        firmware.manual = True
    result = {'state': state, 'pins': fields.get('Pn', '')}
    scale = 25.4 if firmware.report_inches else 1.0
    positions = {k: tuple(v * scale for v in vector(fields[k])) for k in ('MPos','WPos','WCO') if k in fields}
    if 'WCO' in positions: firmware.last_wco = positions['WCO']
    if 'MPos' in positions: firmware.last_mpos = positions['MPos']
    if 'WPos' in positions: firmware.last_wpos = positions['WPos']
    if 'MPos' in positions and 'WPos' in positions:
        firmware.last_wco = tuple(m-w for m,w in zip(positions['MPos'], positions['WPos']))
    elif firmware.last_wco is not None:
        if 'MPos' in positions:
            firmware.last_wpos = tuple(m-w for m,w in zip(firmware.last_mpos, firmware.last_wco))
        elif 'WPos' in positions:
            firmware.last_mpos = tuple(w+c for w,c in zip(firmware.last_wpos, firmware.last_wco))
        elif 'WCO' in positions and firmware.last_mpos:
            firmware.last_wpos = tuple(m-w for m,w in zip(firmware.last_mpos, firmware.last_wco))
    for prefix, coords in (('m', firmware.last_mpos), ('w', firmware.last_wpos), ('wco', firmware.last_wco)):
        if coords:
            result.update({prefix+axis:value for axis,value in zip('xyzabc',coords)})
            if len(coords) == 2: result[prefix+'z'] = 0.0
    if 'FS' in fields:
        fs = vector(fields['FS']); result.update(curfeed=fs[0]*scale, curspindle=fs[1])
    elif 'F' in fields: result['curfeed'] = float(fields['F'])*scale
    for key, names in (('Ov', ('OvFeed','OvRapid','OvSpindle')), ('Bf', ('planner','rxbytes'))):
        if key in fields:
            values = [int(v) for v in fields[key].split(',')]
            if len(values) < len(names): raise ValueError('Incomplete '+key+' report')
            result.update(zip(names,values))
    if 'MPG' in fields: firmware.mpg = fields['MPG'] != '0'
    result['mpg'] = firmware.mpg
    if any(isinstance(v, (int, float)) and not math.isfinite(v) for v in result.values()):
        raise ValueError('Non-finite telemetry value')
    return result


class LineFramer:
    """Retain partial serial/TCP lines across read timeouts; bound invalid traffic."""
    def __init__(self):
        self.pending = bytearray()

    def feed(self, data):
        lines = []
        for byte in data:
            if byte in (10, 13):
                if self.pending:
                    lines.append(self.pending.decode('ascii', 'replace').strip())
                    self.pending.clear()
            else:
                self.pending.append(byte)
                if len(self.pending) > 65536:
                    self.pending.clear()
                    raise ValueError('Controller sent an oversized response without a line ending.')
        return lines
