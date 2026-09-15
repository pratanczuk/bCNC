"""Document adapter for pure blade geometry; never changes source or global feed."""
from copy import deepcopy
from CNC import GCode
from PlotterKnife import compensate_path
from PlotterPath import path_to_block


def compensate_blocks(blocks, offset, speed, overcut=0, *, safe=3, digits=4):
    document = GCode()
    document.blocks = deepcopy(blocks)
    result = []
    contours = 0
    for index, source in enumerate(document.blocks):
        if source.name() in ('Header', 'Footer') or not source.enable:
            result.append(source)
            continue
        paths = document.toPath(index)
        if not paths:
            result.append(source)
            continue
        for path in paths:
            compensated = compensate_path(path, offset, overcut)
            block = path_to_block(compensated, feed=speed, safe=safe, digits=digits)
            block.enable, block.passes, block.color = source.enable, source.passes, source.color
            block.foil = deepcopy(getattr(source, 'foil', {}))
            result.append(block)
            contours += 1
    return result if contours else None
