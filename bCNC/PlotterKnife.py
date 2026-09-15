"""Drag-knife geometry with explicit inputs and no UI, sender or configuration state.

Tangential-offset algorithm adapted from Tomas Mudrunka's dragknife implementation.
"""
from copy import deepcopy
from math import acos, degrees, sqrt, isfinite
from bmath import Vector
from bpath import Path, Segment, eq

def entry_point(point, offset):
    return Vector(point[0] + offset, point[1])

def segmentLength(seg):
    return sqrt(
        (seg.B[0] - seg.A[0]) ** 2 +
        (seg.B[1] - seg.A[1]) ** 2
    )

def addPathOvercut(path, distance, precision):
    """Repeat the beginning of a CLOSED original path.

    This is done before dragknife compensation, so the added overcut
    follows the original geometry. Arcs are approximated using
    path.linearize(precision, True), so curved starts are followed
    using short line segments.
    """
    if distance <= 0:
        return

    if len(path) < 1:
        return

    # Only closed paths can be overcut by repeating their beginning.
    # For open paths there is no meaningful "wrap to start".
    if not eq(path[-1].B, path[0].A):
        return

    # Work from a linearized copy so arcs can be partially repeated.
    lpath = path.linearize(precision, True)
    if len(lpath) < 1:
        return

    remaining = distance
    current = Vector(path[-1].B[0], path[-1].B[1])

    # Repeat the start of the path until requested distance is consumed.
    # This permits overcut longer than the first segment.
    safety = 0
    while remaining > 0 and safety < 10000:
        safety += 1
        consumed_something = False

        for seg in lpath:
            seglen = segmentLength(seg)
            if seglen <= 0:
                continue

            direction = (seg.B - seg.A).unit()

            if remaining >= seglen:
                newB = current + direction * seglen
                path.append(Segment(Segment.LINE, current, newB))
                current = newB
                remaining -= seglen
                consumed_something = True
            else:
                newB = current + direction * remaining
                path.append(Segment(Segment.LINE, current, newB))
                remaining = 0
                consumed_something = True
                break

        if not consumed_something:
            break


def compensate_path(path, offset, overcut=0.0, angle_threshold=20.0, precision=0.5):
    """Return a compensated contour without modifying the source path."""
    for value in (offset, overcut, angle_threshold, precision):
        if not isfinite(float(value)):
            raise ValueError('Blade parameters must be finite numbers.')
    if offset < 0 or overcut < 0 or precision <= 0 or not 0 <= angle_threshold <= 180:
        raise ValueError('Invalid blade offset, overcut or curve precision.')
    if not path:
        return Path(path.name)
    opath = deepcopy(path)
    dragoff, angleth, simpreci = offset, angle_threshold, precision
    npath = Path(f'dragknife {offset}: {path.name}')
    # Entry vector
    ventry = Segment(
        Segment.LINE,
        entry_point(opath[0].A, -dragoff),
        opath[0].A
    )

    # Path-following overcut:
    # Repeat the beginning of the original closed path before
    # tangential drag-knife offset is generated.
    addPathOvercut(opath, overcut, simpreci)

    # Exit vector
    vexit = Segment(
        Segment.LINE,
        opath[-1].B,
        entry_point(opath[-1].B, dragoff)
    )

    opath.append(vexit)
    prevseg = ventry

    # Generate path with tangential lag for dragknife operation
    for i, seg in enumerate(opath):
        # Get adjacent tangential vectors in this point
        TA = prevseg.tangentEnd()
        TB = seg.tangentStart()

        # Compute difference between tangential vectors of
        # two neighbor segments
        angle = degrees(acos(max(-1.0, min(1.0, TA.dot(TB)))))

        # Compute swivel direction
        arcdir = (TA[0] * TB[1]) - (TA[1] * TB[0])
        if arcdir < 0:
            arcdir = Segment.CW
        else:
            arcdir = Segment.CCW

        # Append swivel if needed
        # with an angle threshold of 1 degree on entry/exit segments
        if abs(angle) > angleth or (
            abs(angle) > 1 and (i == 0 or i == len(opath) - 1)
        ):
            arca = Segment(
                arcdir,
                prevseg.tangentialOffset(dragoff).B,
                seg.tangentialOffset(dragoff).A,
                prevseg.B,
            )

            npath.append(arca)

        # Append segment with tangential offset
        if i < len(opath) - 1:
            newSeg = seg.tangentialOffset(dragoff)

            # To keep the path connected, we use the end of the
            # previous segment as the start of this segment.
            # If there is no previous entry, use the ventry vector.
            if len(npath) == 0:
                newSeg.setStart(ventry.B)
            else:
                newSeg.setStart(npath[-1].B)

            npath.append(newSeg)

        prevseg = seg

    return npath
