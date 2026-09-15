"""Layer catalog and undoable object management, independent of Tk and transport."""
from copy import deepcopy
import re
import uuid

DEFAULT = 'Default'
DEFAULT_COLOR = '#166c5e'
RESERVED = ('Header', 'Footer')


def valid_name(value, kind='layer'):
    if not isinstance(value, str):
        raise ValueError(f'Enter a {kind} name.')
    value = value.strip()
    if not value or len(value) > 100 or any(ord(c) < 32 for c in value):
        raise ValueError(f'Use a {kind} name of 1–100 characters without line breaks.')
    if kind == 'object' and value in RESERVED:
        raise ValueError('Header and Footer are reserved for the job setup.')
    return value


def valid_color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Choose a valid preview color.')
    return value.lower()


def layer_name(block):
    return getattr(block, 'foil', {}).get('layer') or DEFAULT


def validate_catalog(layers):
    if not isinstance(layers, list) or not 1 <= len(layers) <= 128:
        raise ValueError('A project needs 1–128 layers.')
    names = set()
    result = []
    for layer in layers:
        if not isinstance(layer, dict):
            raise ValueError('A layer record is invalid.')
        name = valid_name(layer.get('name'))
        if name.casefold() in names:
            raise ValueError('Each layer needs a unique name.')
        names.add(name.casefold())
        enabled = layer.get('enabled', True)
        if type(enabled) is not bool:
            raise ValueError('A layer visibility value is invalid.')
        record = {'name': name, 'color': valid_color(layer.get('color', DEFAULT_COLOR)), 'enabled': enabled}
        if 'process' in layer:
            from PlotterLibrary import validate_process
            record['process'] = validate_process(layer['process'])
        result.append(record)
    if DEFAULT not in [layer['name'] for layer in result]:
        raise ValueError('The Default layer is required for unassigned artwork.')
    return result


def catalog(document):
    """Include legacy implicit layer names without mutating the document on read."""
    saved = deepcopy(getattr(document, 'foil_layers', []))
    if not saved:
        saved = [{'name': DEFAULT, 'color': DEFAULT_COLOR, 'enabled': True}]
    saved = validate_catalog(saved)
    names = {layer['name'].casefold() for layer in saved}
    for block in document.blocks:
        if block.name() in RESERVED:
            continue
        name = valid_name(layer_name(block))
        if name.casefold() not in names:
            color = block.color if isinstance(block.color, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', block.color) else DEFAULT_COLOR
            saved.append({'name': name, 'color': color, 'enabled': True})
            names.add(name.casefold())
    return validate_catalog(saved)


def synchronize(blocks, layers, track=False):
    """Cache effective visibility for the existing canvas/compiler consumers."""
    lookup = {layer['name'].casefold(): layer for layer in layers}
    for block in blocks:
        if block.name() in RESERVED:
            continue
        layer = lookup.get(layer_name(block).casefold())
        if layer is None:
            raise ValueError('An object references a missing layer.')
        props = block.foil
        own_enabled = props.get('object_enabled', bool(block.enable))
        if type(own_enabled) is not bool:
            raise ValueError('An object visibility value is invalid.')
        if track or not layer['enabled']:
            props['object_enabled'] = own_enabled
        if track:
            props.setdefault('color_override', block.color is not None and block.color != layer['color'])
        block.enable = own_enabled and layer['enabled']
        if track and not props.get('color_override'):
            block.color = layer['color']


def apply_visibility(document):
    """Refresh the legacy visibility cache, including newly created artwork."""
    layers = catalog(document)
    lookup = {layer['name'].casefold(): layer for layer in layers}
    for block in document.blocks:
        if block.name() not in RESERVED and not lookup[layer_name(block).casefold()]['enabled']:
            block.foil.setdefault('object_enabled', bool(block.enable))
    synchronize(document.blocks, layers)


def replace_state(document, blocks, layers):
    old = document.blocks, document.foil_layers
    document.blocks, document.foil_layers = blocks, layers
    return replace_state, document, *old


def signature(document):
    return (catalog(document), [(id(b), b.name(), list(b), b.enable, b.color, b.passes,
                                deepcopy(getattr(b, 'foil', {}))) for b in document.blocks])


class LayerManager:
    def __init__(self, document, running=lambda: False):
        self.document = document
        self.running = running

    def _state(self):
        if self.running():
            raise ValueError('Wait until the cut finishes before editing layers or objects.')
        layers = catalog(self.document)
        blocks = deepcopy(self.document.blocks)
        synchronize(blocks, layers, track=True)
        return blocks, layers

    def _commit(self, blocks, layers, title):
        layers = validate_catalog(layers)
        synchronize(blocks, layers, track=True)
        self.document.addUndo(replace_state(self.document, blocks, layers), title)

    def _layer(self, layers, name):
        for layer in layers:
            if layer['name'].casefold() == name.casefold():
                return layer
        raise ValueError('Choose an existing layer.')

    def _ids(self, blocks, ids, groups=False):
        ids = sorted(set(ids))
        if not ids:
            raise ValueError('Select one or more objects in the list.')
        if any(type(i) is not int or not 0 <= i < len(blocks) or blocks[i].name() in RESERVED for i in ids):
            raise ValueError('Select artwork objects. Job headers and footers cannot be edited here.')
        if groups:
            selected = {blocks[i].foil.get('group') for i in ids} - {None, ''}
            ids = sorted(set(ids) | {i for i, b in enumerate(blocks)
                         if b.name() not in RESERVED and b.foil.get('group') in selected})
        return ids

    def add(self, name, color=DEFAULT_COLOR):
        blocks, layers = self._state()
        name, color = valid_name(name), valid_color(color)
        if any(layer['name'].casefold() == name.casefold() for layer in layers):
            raise ValueError('A layer with that name already exists. Choose another name.')
        layers.append({'name': name, 'color': color, 'enabled': True})
        self._commit(blocks, layers, 'Add layer')
        return name

    def rename_layer(self, name, replacement):
        blocks, layers = self._state()
        target = self._layer(layers, name)
        if target['name'] == DEFAULT:
            raise ValueError('Default is the permanent home for unassigned objects. Add a named layer instead.')
        replacement = valid_name(replacement)
        if any(layer is not target and layer['name'].casefold() == replacement.casefold() for layer in layers):
            raise ValueError('A layer with that name already exists.')
        for block in blocks:
            if block.name() not in RESERVED and layer_name(block).casefold() == name.casefold():
                block.foil['layer'] = replacement
        target['name'] = replacement
        self._commit(blocks, layers, 'Rename layer')
        return replacement

    def delete_layer(self, name, delete_objects=False, destination=DEFAULT):
        blocks, layers = self._state()
        target = self._layer(layers, name)
        if target['name'] == DEFAULT:
            raise ValueError('Default cannot be deleted. It holds unassigned artwork.')
        if not delete_objects:
            destination = self._layer(layers, destination)['name']
            if destination.casefold() == name.casefold():
                raise ValueError('Choose another layer for these objects.')
        kept = []
        for block in blocks:
            belongs = block.name() not in RESERVED and layer_name(block).casefold() == name.casefold()
            if belongs and delete_objects:
                continue
            if belongs:
                block.foil['layer'] = destination
            kept.append(block)
        layers.remove(target)
        self._commit(kept, layers, 'Delete layer and objects' if delete_objects else 'Delete layer; keep objects')
        return destination if not delete_objects else DEFAULT

    def layer_properties(self, name, *, enabled=None, color=None, only=False):
        blocks, layers = self._state()
        target = self._layer(layers, name)
        if only:
            for layer in layers:
                layer['enabled'] = layer is target
        elif enabled is not None:
            target['enabled'] = bool(enabled)
        if color is not None:
            target['color'] = valid_color(color)
        self._commit(blocks, layers, 'Change layer properties')
        return target['name']

    def set_process(self, name, process):
        blocks, layers = self._state()
        target = self._layer(layers, name)
        if process is None:
            target.pop('process', None)
        else:
            from PlotterLibrary import validate_process
            target['process'] = validate_process(process)
        self._commit(blocks, layers, 'Change layer tool and operation')
        return target['name']

    def show_all(self):
        blocks, layers = self._state()
        for layer in layers:
            layer['enabled'] = True
        self._commit(blocks, layers, 'Include all layers')
        return DEFAULT

    def order_layer(self, name, direction):
        blocks, layers = self._state()
        target = self._layer(layers, name)
        index = layers.index(target)
        other = index + (-1 if direction < 0 else 1)
        if not 0 <= other < len(layers):
            return name
        layers[index], layers[other] = layers[other], layers[index]
        rank = {layer['name'].casefold(): i for i, layer in enumerate(layers)}
        slots = [i for i, b in enumerate(blocks) if b.name() not in RESERVED]
        artwork = sorted((blocks[i] for i in slots), key=lambda b: rank[layer_name(b).casefold()])
        for i, block in zip(slots, artwork):
            blocks[i] = block
        self._commit(blocks, layers, 'Reorder layers')
        return name

    def object_properties(self, ids, *, name=None, enabled=None, passes=None, color=None):
        blocks, layers = self._state()
        ids = self._ids(blocks, ids)
        if name is not None:
            if len(ids) != 1:
                raise ValueError('Select one object to rename.')
            blocks[ids[0]]._name = valid_name(name, 'object')
        if passes is not None:
            from PlotterEditing import number
            passes = number(passes, 1, 100)
            if int(passes) != passes:
                raise ValueError('Cut passes must be a whole number from 1 to 100.')
        for i in ids:
            if enabled is not None:
                blocks[i].foil['object_enabled'] = bool(enabled)
            if passes is not None:
                blocks[i].passes = int(passes)
            if color is not None:
                blocks[i].foil['color_override'] = color != 'layer'
                if color != 'layer':
                    blocks[i].color = valid_color(color)
        self._commit(blocks, layers, 'Change object properties')
        return ids

    def move(self, ids, destination, before=None):
        blocks, layers = self._state()
        ids = self._ids(blocks, ids, groups=True)
        destination = self._layer(layers, destination)['name']
        if before is not None:
            self._ids(blocks, [before])
            if layer_name(blocks[before]).casefold() != destination.casefold():
                raise ValueError('Drop onto an object in the destination layer.')
            if before in ids:
                return ids
        moving = [blocks[i] for i in ids]
        anchor = blocks[before] if before is not None else None
        rest = [b for i, b in enumerate(blocks) if i not in ids]
        if anchor is not None:
            position = next(i for i, b in enumerate(rest) if b is anchor)
        else:
            same = [i for i, b in enumerate(rest) if b.name() not in RESERVED and layer_name(b).casefold() == destination.casefold()]
            position = same[-1] + 1 if same else next((i for i, b in enumerate(rest) if b.name() == 'Footer'), len(rest))
        for block in moving:
            block.foil['layer'] = destination
        rest[position:position] = moving
        self._commit(rest, layers, 'Move objects to layer')
        return list(range(position, position + len(moving)))

    def duplicate(self, ids):
        blocks, layers = self._state()
        ids = self._ids(blocks, ids, groups=True)
        copies = deepcopy([blocks[i] for i in ids])
        groups = {}
        for block in copies:
            block._name = block.name()[:95] + ' copy'
            group = block.foil.get('group')
            if group:
                block.foil['group'] = groups.setdefault(group, uuid.uuid4().hex)
        position = max(ids) + 1
        blocks[position:position] = copies
        self._commit(blocks, layers, 'Duplicate objects')
        return list(range(position, position + len(copies)))

    def delete_objects(self, ids):
        blocks, layers = self._state()
        ids = self._ids(blocks, ids)
        self._commit([b for i, b in enumerate(blocks) if i not in ids], layers, 'Delete objects')
        return []

    def order_objects(self, ids, direction):
        blocks, layers = self._state()
        ids = self._ids(blocks, ids, groups=True)
        names = {layer_name(blocks[i]).casefold() for i in ids}
        if len(names) != 1:
            raise ValueError('Select objects in one layer to reorder them.')
        slots = [i for i, b in enumerate(blocks) if b.name() not in RESERVED and layer_name(b).casefold() in names]
        values = [blocks[i] for i in slots]
        selected = {id(blocks[i]) for i in ids}
        order = range(len(values)) if direction < 0 else range(len(values)-1, -1, -1)
        for index in order:
            other = index + (-1 if direction < 0 else 1)
            if id(values[index]) in selected and 0 <= other < len(values) and id(values[other]) not in selected:
                values[index], values[other] = values[other], values[index]
        for i, block in zip(slots, values):
            blocks[i] = block
        self._commit(blocks, layers, 'Reorder objects')
        return [i for i, b in enumerate(blocks) if id(b) in selected]

    def group(self, ids, attached=True):
        blocks, layers = self._state()
        ids = self._ids(blocks, ids, groups=True)
        if attached and len(ids) < 2:
            raise ValueError('Select at least two objects to attach.')
        group = uuid.uuid4().hex
        for i in ids:
            if attached:
                blocks[i].foil['group'] = group
            else:
                blocks[i].foil.pop('group', None)
        self._commit(blocks, layers, 'Attach objects' if attached else 'Detach objects')
        return ids
