"""Planar path serialization with explicit output parameters."""
from bpath import Path, Segment
from CNC import Block


def path_to_block(paths, block=None, *, z=0, feed=500, safe=3, digits=4):
    paths = [paths] if isinstance(paths, Path) else list(paths)
    block = Block(paths[0].name if paths else 'new') if block is None else block
    def fmt(letter, value):
        return letter + str(round(float(value), digits))
    for index, path in enumerate(paths):
        if not path:
            continue
        if index:
            block.append('( ---------- cut-here ---------- )')
        x, y = path[0].A
        block.extend(['g0 ' + fmt('z', safe), 'g0 ' + fmt('x', x) + ' ' + fmt('y', y),
                      'g0 ' + fmt('z', z), '(entered)'])
        for position, segment in enumerate(path):
            line = f'g{segment.type} ' + fmt('x', segment.B[0]) + ' ' + fmt('y', segment.B[1])
            if segment.type in (Segment.CW, Segment.CCW):
                ij = segment.C - segment.A
                line += ' ' + fmt('i', ij[0]) + ' ' + fmt('j', ij[1])
            line += ' ' + fmt('z', z)
            if position == 0:
                line += ' ' + fmt('f', feed)
            block.append(line)
        block.extend(['(exiting)', 'g0 ' + fmt('z', safe)])
    block.foil['vector'] = True
    return block


def tool_path_to_block(path, *, feed, pressure, digits=4):
    """Film/pen actuator output: tool up for travel, pressure only on the outline."""
    from PlotterJob import cut_settings_valid
    if not cut_settings_valid(feed, pressure):
        raise ValueError('Choose a positive speed and pressure from 0 to 1000.')
    if not path:
        raise ValueError('The tool path is empty.')
    def fmt(letter, value):
        return letter + str(round(float(value), digits))
    block = Block(path.name)
    x, y = path[0].A
    block.extend(['M5', 'G0 ' + fmt('X', x) + ' ' + fmt('Y', y), f'M3 S{pressure:.0f}'])
    for segment in path:
        line = f'G{segment.type} ' + fmt('X', segment.B[0]) + ' ' + fmt('Y', segment.B[1])
        if segment.type in (Segment.CW, Segment.CCW):
            ij = segment.C - segment.A
            line += ' ' + fmt('I', ij[0]) + ' ' + fmt('J', ij[1])
        line += ' ' + fmt('F', feed)
        block.append(line)
    block.append('M5')
    block.foil['vector'] = True
    return block
