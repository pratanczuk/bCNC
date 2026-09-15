"""Cut-buffer planning from explicit inputs, with no window or sender access."""
from dataclasses import dataclass, field, replace
import copy

from CNC import CNC
from PlotterJob import apply_cut_settings, bounds_fit, planned_cut_bounds
from PlotterPolicy import validate_plotter_commands as validate_commands


@dataclass(frozen=True)
class JobParameters:
    startup: str = 'G90'
    origin: tuple = (0.0, 0.0, 0.0)
    width: float = 300.0
    height: float = 300.0
    speed: float = 500.0
    pressure: float = 500.0
    compensate: bool = False
    knife_offset: float = 0.5
    overcut: float = 0.0
    inner_first: bool = False
    processes: dict = field(default_factory=dict)
    tool_pass: str = ''
    material: dict = None


def validate_plotter_commands(blocks, startup=''):
    validate_commands(blocks, startup, compile_line=CNC.compileLine, break_line=CNC.breakLine)


def prepare_job(blocks, parameters, compensate=None, use_material=True):
    """Return a separate buffer. A compensator returns blocks or raises an error."""
    if parameters.material:
        from PlotterLibrary import validate_profile
        material = validate_profile('materials', parameters.material)
        parameters = replace(parameters, material=material, speed=material['speed'], pressure=material['pressure'])
    validate_plotter_commands(blocks, parameters.startup)
    artwork = [block for block in blocks if block.enable and block.name() not in ('Header', 'Footer')]
    vectors = [block for block in artwork if block.foil.get('vector')]
    if vectors and len(vectors) != len(artwork) and not parameters.processes:
        raise ValueError('This job mixes vector artwork and machine G-code. Run them as separate jobs so explicit machine commands and generated tool movements remain unambiguous.')
    if parameters.processes or vectors:
        from PlotterProcesses import prepare_processes
        return prepare_processes(blocks, parameters, use_material)
    if parameters.compensate:
        if compensate is None:
            raise ValueError('Knife compensation is unavailable.')
        prepared = compensate(parameters)
        if prepared is None:
            raise ValueError('Knife compensation produced no paths. Check the artwork and blade settings.')
        prepared = copy.deepcopy(prepared)
    else:
        prepared = copy.deepcopy(blocks)
        if parameters.inner_first:
            from PlotterEditing import order_blocks
            prepared = order_blocks(prepared)
    if use_material:
        if parameters.material:
            from PlotterLibrary import validate_profile
            material = validate_profile('materials', parameters.material)
            if material['compatible'] not in ('Both', 'Knife'):
                raise ValueError('This material profile requires a pen. Assign a pen to the layer in Layers & objects.')
            for block in prepared:
                if block.name() not in ('Header', 'Footer') and block.enable:
                    block.passes *= material['passes']
                    if block.passes > 100:
                        raise ValueError('Combined object and material passes exceed 100.')
        prepared = apply_cut_settings(prepared, parameters.speed, parameters.pressure, parameters.startup)
        bounds = planned_cut_bounds(prepared, parameters.origin, parameters.startup)
        if not bounds_fit(bounds, parameters.width, parameters.height):
            raise ValueError('The planned cutting paths extend outside the mat. Move the design inward to allow space for blade compensation and overcut.')
    return prepared
