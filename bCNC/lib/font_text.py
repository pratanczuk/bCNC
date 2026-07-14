"""Convert font glyph outlines into welded bCNC vector paths."""

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

try:
    from shapely import GeometryCollection, Polygon, unary_union
    from shapely.affinity import translate
except ImportError:
    GeometryCollection = None
    Polygon = None
    unary_union = None
    translate = None

from bmath import Vector
from bpath import Path, Segment


class _FlattenPen(BasePen):
    def __init__(self, glyph_set, tolerance):
        super().__init__(glyph_set)
        self.tolerance = max(float(tolerance), 0.01)
        self.contours = []
        self.contour = None
        self.current = None

    def _moveTo(self, point):
        self._finish(False)
        self.contour = [tuple(point)]
        self.current = tuple(point)

    def _lineTo(self, point):
        point = tuple(point)
        if self.contour is not None and point != self.current:
            self.contour.append(point)
        self.current = point

    @staticmethod
    def _distance_to_line(point, start, end):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = (dx * dx + dy * dy) ** 0.5
        if not length:
            return ((point[0] - start[0]) ** 2
                    + (point[1] - start[1]) ** 2) ** 0.5
        return abs(dy * point[0] - dx * point[1]
                   + end[0] * start[1] - end[1] * start[0]) / length

    def _curveToOne(self, control1, control2, end):
        start = self.current
        control1 = tuple(control1)
        control2 = tuple(control2)
        end = tuple(end)
        self._flatten_cubic(start, control1, control2, end, 0)
        self.current = end

    def _flatten_cubic(self, p0, p1, p2, p3, depth):
        flatness = max(
            self._distance_to_line(p1, p0, p3),
            self._distance_to_line(p2, p0, p3),
        )
        if flatness <= self.tolerance or depth >= 12:
            self._lineTo(p3)
            return

        p01 = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
        p12 = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        p23 = ((p2[0] + p3[0]) / 2.0, (p2[1] + p3[1]) / 2.0)
        p012 = ((p01[0] + p12[0]) / 2.0, (p01[1] + p12[1]) / 2.0)
        p123 = ((p12[0] + p23[0]) / 2.0, (p12[1] + p23[1]) / 2.0)
        middle = ((p012[0] + p123[0]) / 2.0,
                  (p012[1] + p123[1]) / 2.0)
        self._flatten_cubic(p0, p01, p012, middle, depth + 1)
        self._flatten_cubic(middle, p123, p23, p3, depth + 1)

    def _closePath(self):
        self._finish(True)

    def _endPath(self):
        self._finish(False)

    def _finish(self, close):
        if self.contour and len(self.contour) >= 3:
            if close and self.contour[-1] != self.contour[0]:
                self.contour.append(self.contour[0])
            self.contours.append(self.contour)
        self.contour = None
        self.current = None


def _kerning(font, left, right):
    if "kern" not in font:
        return 0
    value = 0
    for table in font["kern"].kernTables:
        value += table.kernTable.get((left, right), 0)
    return value


def _contours_geometry(contours, scale):
    geometry = GeometryCollection()
    for contour in contours:
        coordinates = [(x * scale, y * scale) for x, y in contour]
        if len(coordinates) < 4:
            continue
        polygon = Polygon(coordinates)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if not polygon.is_empty:
            # Font contours use winding/even-odd nesting. XOR naturally turns
            # nested contours into counters (holes) regardless of orientation.
            geometry = geometry.symmetric_difference(polygon)
    return geometry


def _geometry_paths(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        polygons = [geometry]
    elif geometry.geom_type == "MultiPolygon":
        polygons = list(geometry.geoms)
    else:
        polygons = [part for part in geometry.geoms
                    if part.geom_type == "Polygon"]

    paths = []
    for index, polygon in enumerate(polygons):
        rings = [polygon.exterior] + list(polygon.interiors)
        for ring_index, ring in enumerate(rings):
            coordinates = list(ring.coords)
            if len(coordinates) < 4:
                continue
            path = Path("Text {}:{}".format(index + 1, ring_index + 1))
            for start, end in zip(coordinates, coordinates[1:]):
                path.append(Segment(
                    Segment.LINE, Vector(*start), Vector(*end)
                ))
            if path:
                paths.append(path)
    return paths


def _contours_paths(contours, scale, x_offset, y_offset, name):
    """Convert flattened font contours directly when Shapely is unavailable."""
    paths = []
    for index, contour in enumerate(contours):
        coordinates = [
            (x_offset + x * scale, y_offset + y * scale)
            for x, y in contour
        ]
        if len(coordinates) < 4:
            continue
        if coordinates[-1] != coordinates[0]:
            coordinates.append(coordinates[0])
        path = Path("{} {}".format(name, index + 1))
        for start, end in zip(coordinates, coordinates[1:]):
            path.append(Segment(
                Segment.LINE, Vector(*start), Vector(*end)
            ))
        if path:
            paths.append(path)
    return paths


def text_to_paths(text, font_filename, height, tolerance=0.02,
                  line_spacing=1.2):
    """Create welded closed paths for text rendered from a TTF/OTF font."""
    if not text:
        raise ValueError("Enter text to insert")
    if height <= 0:
        raise ValueError("Text height must be greater than zero")

    font = TTFont(font_filename, lazy=False)
    try:
        glyph_set = font.getGlyphSet()
        cmap = font.getBestCmap() or {}
        units_per_em = font["head"].unitsPerEm
        scale = float(height) / units_per_em
        tolerance_units = float(tolerance) / scale
        metrics = font["hmtx"].metrics
        fallback = ".notdef" if ".notdef" in glyph_set else None

        geometries = []
        fallback_paths = []
        y_offset = 0.0
        for line in text.split("\n"):
            x_offset = 0.0
            previous = None
            for character in line:
                glyph_name = cmap.get(ord(character), fallback)
                if glyph_name is None:
                    continue
                if previous is not None:
                    x_offset += _kerning(font, previous, glyph_name) * scale

                pen = _FlattenPen(glyph_set, tolerance_units)
                glyph_set[glyph_name].draw(pen)
                pen._finish(False)
                if unary_union is None:
                    fallback_paths.extend(_contours_paths(
                        pen.contours,
                        scale,
                        x_offset,
                        y_offset,
                        glyph_name,
                    ))
                else:
                    glyph_geometry = _contours_geometry(pen.contours, scale)
                    if not glyph_geometry.is_empty:
                        geometries.append(translate(
                            glyph_geometry, xoff=x_offset, yoff=y_offset
                        ))
                x_offset += metrics.get(glyph_name, (units_per_em, 0))[0] * scale
                previous = glyph_name
            y_offset -= float(height) * line_spacing

        if unary_union is None:
            return fallback_paths
        if not geometries:
            return []
        welded = unary_union(geometries)
        if not welded.is_valid:
            welded = welded.buffer(0)
        return _geometry_paths(welded)
    finally:
        font.close()
