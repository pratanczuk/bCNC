"""Validated material/tool libraries and portable layer process settings."""
from copy import deepcopy
import math
from PlotterLayers import valid_name, valid_color


def value(raw, low, high, label):
    try:
        result = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f'Enter a valid {label}.') from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f'{label} must be between {low:g} and {high:g}.')
    return result


def validate_profile(kind, raw):
    if not isinstance(raw, dict):
        raise ValueError('A library profile must be a record.')
    result = {'name': valid_name(raw.get('name'), 'profile')}
    notes = raw.get('notes', '')
    if not isinstance(notes, str) or len(notes) > 2000:
        raise ValueError('Use notes of up to 2000 characters.')
    result['notes'] = notes
    if kind == 'materials':
        result.update(speed=value(raw.get('speed', 500), 1, 20000, 'Speed'),
                      pressure=value(raw.get('pressure', 350), 0, 1000, 'Pressure'),
                      thickness=value(raw.get('thickness', 0), 0, 50, 'Thickness'),
                      passes=value(raw.get('passes', 1), 1, 100, 'Passes'))
        if result['passes'] != int(result['passes']):
            raise ValueError('Passes must be a whole number.')
        result['passes'] = int(result['passes'])
        result['compatible'] = raw.get('compatible', 'Both')
        if result['compatible'] not in ('Knife', 'Pen', 'Both'):
            raise ValueError('Choose Knife, Pen or Both for compatible tools.')
    elif kind == 'tools':
        tool = raw.get('kind', 'Knife')
        if tool not in ('Knife', 'Pen'):
            raise ValueError('Choose Knife or Pen.')
        result['kind'] = tool
        result['color'] = valid_color(raw.get('color', '#333333'))
        result['width'] = value(raw.get('width', .5), .01, 20, 'Stroke width')
        # Pen safety is enforced here, regardless of stale or imported knife values.
        result['offset'] = 0 if tool == 'Pen' else value(raw.get('offset', .25), 0, 10, 'Blade offset')
        result['overcut'] = 0 if tool == 'Pen' else value(raw.get('overcut', 0), 0, 20, 'Overcut')
        result['angle'] = 0 if tool == 'Pen' else value(raw.get('angle', 45), 1, 90, 'Blade angle')
        compensation = raw.get('compensate', True)
        if type(compensation) is not bool:
            raise ValueError('Choose whether to compensate for the blade.')
        result['compensate'] = tool == 'Knife' and compensation
    else:
        raise ValueError('Choose the material or tool library.')
    return result


def validate_process(raw):
    if not isinstance(raw, dict):
        raise ValueError('Choose a layer tool and operation.')
    if not isinstance(raw.get('tool'), dict):
        raise ValueError('Choose a saved tool. Add a knife or pen in Materials & tools first.')
    tool = validate_profile('tools', raw.get('tool'))
    operation = raw.get('operation')
    if operation not in ('Cut', 'Draw') or (operation == 'Draw') != (tool['kind'] == 'Pen'):
        raise ValueError('Draw requires a pen; Cut requires a knife.')
    material = raw.get('material')
    if material is not None:
        material = validate_profile('materials', material)
        if material['compatible'] not in ('Both', tool['kind']):
            raise ValueError('This material profile is not compatible with the selected tool.')
    return {'operation': operation, 'tool': tool, 'material': material}


class ProfileLibrary:
    def __init__(self, saved=None, materials=None, blades=None):
        self.records = {'materials': {}, 'tools': {}}
        if saved is not None:
            if not isinstance(saved, dict) or saved.get('version') != 1:
                raise ValueError('The material/tool library format is not supported.')
            for kind in self.records:
                records = saved.get(kind, [])
                if not isinstance(records, list):
                    raise ValueError('The library profile list is invalid.')
                for record in records:
                    self.save(kind, record)
        else:
            for name, record in (materials or {}).items():
                self.save('materials', dict(name=name, speed=record['speed'], pressure=record['strength']))
            for name, record in (blades or {}).items():
                self.save('tools', dict(name=name, offset=record['mat_knife_offset'],
                          overcut=record['mat_overcut'], compensate=record['mat_auto_dragknife']))

    def save(self, kind, raw, previous=None):
        record = validate_profile(kind, raw)
        if record['name'] in ('Current settings', 'Current blade'):
            raise ValueError('Choose a profile name other than Current settings or Current blade.')
        items = self.records[kind]
        if previous is not None and previous not in items:
            raise ValueError('Select the profile to edit.')
        if any(name.casefold() == record['name'].casefold() and name != previous for name in items):
            raise ValueError('A profile with this name already exists.')
        if previous is not None:
            del items[previous]
        items[record['name']] = record
        return record['name']

    def duplicate(self, kind, name):
        record = deepcopy(self.records[kind][name])
        suffix = 2
        candidate = name[:90] + ' copy'
        while any(key.casefold() == candidate.casefold() for key in self.records[kind]):
            candidate = name[:85] + f' copy {suffix}'
            suffix += 1
        record['name'] = candidate
        return self.save(kind, record)

    def delete(self, kind, name):
        if name not in self.records[kind]:
            raise ValueError('Select a profile to delete.')
        del self.records[kind][name]

    def snapshot(self):
        return {'version': 1, **{kind: deepcopy(list(items.values())) for kind, items in self.records.items()}}
