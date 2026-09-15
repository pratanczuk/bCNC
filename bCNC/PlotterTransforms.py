"""Source-preserving document transformations with a single undo transaction."""
import math
from PlotterProject import metadata, set_properties, command_matrix
from PlotterEditing import multiply, IDENTITY, contour_points


def transform_document(document, ids, command, *args):
    operations = {'MOVE': document.moveLines, 'ROTATE': document.rotateLines,
                  'SCALE': document.scaleLines, 'MIRRORH': document.mirrorHLines,
                  'MIRRORV': document.mirrorVLines}
    if command not in operations:
        raise ValueError('Choose a supported drawing transformation.')
    if any(value is not None and not math.isfinite(float(value)) for value in args):
        raise ValueError('Transformation values must be finite numbers.')
    ids = sorted(set(ids))
    if not ids or any(i < 0 or i >= len(document.blocks) or document.blocks[i].name() in ('Header','Footer') for i in ids):
        raise ValueError('Select artwork objects to transform.')
    matrix = command_matrix(command, args)
    old = {i: metadata(document.blocks[i]) for i in ids}
    editable = {i: old[i].get('rendered') == list(document.blocks[i]) for i in ids}
    for i in ids:
        if 'text' not in old[i] and (not editable[i] or 'matrix' not in old[i]):
            old[i]['source_outlines'] = [contour_points(path) for path in document.toPath(i)]
            old[i]['matrix'] = list(IDENTITY)
            editable[i] = True
    history = document.undoredo.undoList
    start = len(history)
    operations[command]([(i, None) for i in ids], *args)
    if len(history) > start:
        properties = []
        for i in ids:
            if editable[i]:
                props = old[i].copy()
                props['matrix'] = multiply(matrix, props.get('matrix', IDENTITY))
                props['rendered'] = list(document.blocks[i])
                properties.append(set_properties(document, i, props))
        if properties:
            changes = history[start:]
            del history[start:]
            document.addUndo(changes + properties, 'Transform artwork')
    return ids
