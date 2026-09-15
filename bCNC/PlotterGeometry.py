"""Compound-outline operations for foil designs, including glyph counters."""
from copy import deepcopy

from bmath import Vector
from bpath import Path, Segment

OPERATIONS = {
    'Join / weld': 'union',
    'Subtract': 'difference',
    'Intersect': 'intersection',
    'Exclude overlap': 'symmetric_difference',
    'Combine outlines': 'combine',
}


def outlines_geometry(paths):
    from shapely.geometry import GeometryCollection, Polygon
    geometry = GeometryCollection()
    for path in paths:
        if not path or not path.isClosed():
            raise ValueError('These operations need closed outlines. Close open paths before combining them.')
        points = []
        for segment in path:
            # Arc chords no longer than .04 mm bound deviation by .02 mm.
            points.extend((part.A[0], part.A[1]) for part in segment.linearize(.04))
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.area == 0:
            raise ValueError('An outline crosses itself or has no area. Repair the artwork before combining it.')
        # Nested outlines are holes, independent of winding direction.
        geometry = geometry.symmetric_difference(polygon)
    return geometry


def geometry_paths(geometry):
    if geometry.is_empty:
        return []
    polygons = [geometry] if geometry.geom_type == 'Polygon' else list(getattr(geometry, 'geoms', []))
    paths = []
    for polygon in polygons:
        if polygon.geom_type != 'Polygon':
            continue  # Touching edges alone have no cuttable area.
        for ring in [polygon.exterior] + list(polygon.interiors):
            points = list(ring.coords)
            path = Path('Combined outline')
            for a, b in zip(points, points[1:]):
                path.append(Segment(Segment.LINE, Vector(*a), Vector(*b)))
            paths.append(path)
    return paths


def combine_paths(groups, operation):
    if len(groups) < 2 or any(not group for group in groups):
        raise ValueError('Select at least two objects with outlines in the design list.')
    if operation == 'combine':
        return deepcopy([path for group in groups for path in group])
    if operation not in set(OPERATIONS.values()):
        raise ValueError('Choose a combine operation.')
    result = outlines_geometry(groups[0])
    for group in groups[1:]:
        result = getattr(result, operation)(outlines_geometry(group))
    return geometry_paths(result)


def outline_effect(groups, distance, border=False, rounded=True):
    """Return new outlines at their original coordinates; never mutate sources."""
    import math
    from shapely.geometry import box
    from shapely.ops import unary_union
    distance = float(distance)
    if not math.isfinite(distance) or abs(distance) > 100 or distance == 0:
        raise ValueError('Enter a non-zero distance between −100 and 100 mm.')
    if not groups or any(not group for group in groups):
        raise ValueError('Select artwork in the design list first.')
    if border:
        if distance < 0:
            raise ValueError('A weeding border needs a positive margin.')
        # A bounding rectangle also supports open artwork and arcs.
        bounds = [path.bbox() for group in groups for path in group]
        x0, y0 = min(b[0] for b in bounds), min(b[1] for b in bounds)
        x1, y1 = max(b[2] for b in bounds), max(b[3] for b in bounds)
        return geometry_paths(box(x0-distance, y0-distance, x1+distance, y1+distance))
    geometry = unary_union([outlines_geometry(group) for group in groups])
    result = geometry.buffer(distance, join_style=1 if rounded else 2)
    if result.is_empty:
        raise ValueError('This inset removes the whole design. Use a smaller distance.')
    return geometry_paths(result)
