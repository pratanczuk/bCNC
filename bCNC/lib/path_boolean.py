"""Boolean operations for two closed bCNC paths."""

from copy import deepcopy

from bpath import EPS, Path


_OPERATIONS = {"intersection", "union", "difference", "symmetric_difference"}


def _path_signature(path):
    """Return an orientation-independent signature for an exact contour."""
    signature = []
    for segment in path:
        endpoints = sorted((
            (round(segment.A[0], 7), round(segment.A[1], 7)),
            (round(segment.B[0], 7), round(segment.B[1], 7)),
        ))
        center = None
        if hasattr(segment, "C"):
            center = (round(segment.C[0], 7), round(segment.C[1], 7))
        signature.append((
            endpoints[0], endpoints[1], center, round(segment.length(), 7)
        ))
    return sorted(signature)


def _segment_signature(segment):
    endpoints = sorted((
        (round(segment.A[0], 7), round(segment.A[1], 7)),
        (round(segment.B[0], 7), round(segment.B[1], 7)),
    ))
    center = None
    if hasattr(segment, "C"):
        center = (round(segment.C[0], 7), round(segment.C[1], 7))
    return endpoints[0], endpoints[1], center, round(segment.length(), 7)


def _operation_value(operation, inside_a, inside_b):
    if operation == "intersection":
        return inside_a and inside_b
    if operation == "union":
        return inside_a or inside_b
    if operation == "difference":
        return inside_a and not inside_b
    return inside_a != inside_b


def boolean_paths(path_a, path_b, operation):
    """Return reconstructed contours for a boolean operation on two paths.

    The input paths are copied because intersection splitting mutates paths and
    their segments.  Boundaries are split at every crossing, classified by
    their midpoint, and then reconstructed into continuous contours.
    """
    if operation not in _OPERATIONS:
        raise ValueError("Unknown path boolean operation: {}".format(operation))
    if not path_a.isClosed() or not path_b.isClosed():
        raise ValueError("Path boolean operations require two closed paths")

    if _path_signature(path_a) == _path_signature(path_b):
        if operation in ("intersection", "union"):
            return [deepcopy(path_a)]
        return []

    a = deepcopy(path_a)
    b = deepcopy(path_b)
    a.intersectPath(b)
    b.intersectPath(a)

    def collect_boundaries(left, right, selected_operation):
        result = Path(selected_operation)
        seen = set()
        for segment in list(left) + list(right):
            length = segment.length()
            if length <= EPS:
                continue

            midpoint = segment.midPoint()
            if hasattr(segment, "C"):
                normal = midpoint - segment.C
            else:
                normal = segment.AB.orthogonal()
            normal.norm()
            offset = max(EPS * 100.0, min(length * 0.0001, 0.00001))
            side_a = midpoint + normal * offset
            side_b = midpoint - normal * offset

            value_a = _operation_value(
                selected_operation,
                left.isInside(side_a),
                right.isInside(side_a),
            )
            value_b = _operation_value(
                selected_operation,
                left.isInside(side_b),
                right.isInside(side_b),
            )
            if value_a == value_b:
                continue

            signature = _segment_signature(segment)
            if signature in seen:
                continue
            seen.add(signature)
            result.append(segment)
        return result

    if operation == "symmetric_difference":
        contours = collect_boundaries(a, b, "difference").split2contours()
        contours.extend(
            collect_boundaries(b, a, "difference").split2contours()
        )
        return [path for path in contours if path]

    result = collect_boundaries(a, b, operation)
    return [path for path in result.split2contours() if path]
