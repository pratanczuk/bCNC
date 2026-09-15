"""Prepare one explicitly selected physical tool pass, using layer snapshots."""
from copy import deepcopy
from CNC import GCode, Block
from PlotterLayers import layer_name, RESERVED
from PlotterLibrary import validate_process
from PlotterPath import tool_path_to_block
from PlotterKnife import compensate_path
from PlotterJob import planned_cut_bounds, bounds_fit

ALL_TOOLS = 'All included layers'
CURRENT_TOOL = 'Current knife settings'


def process_label(process):
    if process is None:
        return CURRENT_TOOL
    tool = process['tool']
    return f"{tool['kind']} · {tool['name']}"


def tool_passes(blocks, processes):
    processes = {name.casefold(): process for name, process in processes.items()}
    return list(dict.fromkeys(process_label(processes.get(layer_name(block).casefold())) for block in blocks
                             if block.enable and block.name() not in RESERVED))


def prepare_processes(blocks, parameters, use_material=True):
    processes = {name.casefold(): validate_process(process) for name, process in parameters.processes.items()}
    passes = tool_passes(blocks, processes)
    chosen = parameters.tool_pass
    if chosen in ('', ALL_TOOLS):
        if len(passes) > 1:
            raise ValueError('This design uses several tools. Start the guided sequence from Review and cut, or choose one Tool pass in Prepare to export an individual pass.')
        chosen = passes[0] if passes else ''
    if chosen not in passes:
        raise ValueError('The selected tool pass has no included objects. Choose another pass in Prepare.')
    document = GCode(); document.blocks = deepcopy(blocks)
    if parameters.inner_first:
        from PlotterEditing import order_blocks
        document.blocks = order_blocks(document.blocks)
    header = Block('Header'); header.append('M5')
    for block in blocks:
        if block.name() == 'Header' and block.enable: header.extend(block)
    # Serialized paths below always use absolute millimeters, independent of imported modes.
    header.extend(['M5', 'G21 G90 G17 G94'])
    prepared = [header]
    for index, source in enumerate(document.blocks):
        if not source.enable or source.name() in RESERVED:
            continue
        process = processes.get(layer_name(source).casefold())
        if process_label(process) != chosen:
            continue
        tool = process['tool'] if process else None
        material = (process['material'] if process else None) or parameters.material
        if material is not None:
            from PlotterLibrary import validate_profile
            material = validate_profile('materials', material)
            if material['compatible'] not in ('Both', tool['kind'] if tool else 'Knife'):
                raise ValueError('The material profile is not compatible with this tool pass. Choose a compatible material.')
        speed = material['speed'] if material else parameters.speed
        pressure = material['pressure'] if material else parameters.pressure
        compensate = tool['compensate'] if tool else parameters.compensate
        # Defense in depth: no compensation or overcut call is reachable for a pen.
        if tool and tool['kind'] == 'Pen':
            compensate = False
        offset = tool['offset'] if tool else parameters.knife_offset
        overcut = tool['overcut'] if tool else parameters.overcut
        if not source.foil.get('vector'):
            raise ValueError('Layer tool profiles require vector artwork. Use SVG, DXF, text or shapes; run imported machine G-code with current settings.')
        paths = document.toPath(index)
        if not paths:
            raise ValueError(f'“{source.name()}” has no usable outlines for its tool. Check the artwork before running this pass.')
        for path in paths:
            if compensate:
                path = compensate_path(path, offset, overcut)
            block = tool_path_to_block(path, feed=speed, pressure=pressure)
            block._name = source.name()
            block.foil = deepcopy(source.foil)
            block.foil['process'] = deepcopy(process)
            block.color = tool['color'] if tool and tool['kind']=='Pen' else source.color
            block.passes = source.passes * (material['passes'] if material else 1)
            if block.passes > 100:
                raise ValueError('Combined object and material passes exceed 100. Reduce the pass count.')
            prepared.append(block)
    footer = Block('Footer'); footer.append('M5')
    for block in blocks:
        if block.name() == 'Footer' and block.enable: footer.extend(block)
    footer.append('M5'); prepared.append(footer)
    if use_material and not bounds_fit(planned_cut_bounds(prepared, parameters.origin, parameters.startup), parameters.width, parameters.height):
        raise ValueError('The planned tool paths extend outside the mat. Move the design inward or check the blade offset.')
    return prepared
