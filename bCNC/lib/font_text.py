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
                  line_spacing=1.2, letter_spacing=0, alignment='Left', radius=0):
    """Render Unicode glyph outlines with kerning, spacing and optional circular layout.

    Circular layout rotates each glyph rigidly, preserving its counters. Complex
    script shaping is not provided; unsupported glyphs are reported explicitly.
    """
    import math
    if not text:
        raise ValueError("Enter text to insert")
    from PlotterEditing import number
    height=number(height,.01,1000)
    line_spacing=number(line_spacing,.2,10)
    letter_spacing=number(letter_spacing,-100,100)
    radius=number(radius,0,10000)
    if alignment not in ('Left','Center','Right'): raise ValueError('Choose text alignment.')
    if radius and '\n' in text: raise ValueError('Circular text uses one line. Remove line breaks or use a zero radius.')
    if unary_union is None:
        return _unwelded_text(text,font_filename,height,tolerance,line_spacing,letter_spacing,alignment,radius)
    from shapely.affinity import rotate
    with TTFont(font_filename, lazy=False) as font:
        glyph_set=font.getGlyphSet(); cmap=font.getBestCmap() or {}
        missing=sorted(set(c for c in text if c not in '\n\r' and ord(c) not in cmap))
        if missing:
            raise ValueError('This font does not contain: '+ ' '.join(missing[:12])+'. Choose another font.')
        scale=height/font['head'].unitsPerEm
        metrics=font['hmtx'].metrics
        lines=[]
        for line in text.split('\n'):
            glyphs=[]; cursor=0; previous=None
            for character in line:
                name=cmap[ord(character)]
                if previous is not None: cursor+=_kerning(font,previous,name)*scale+letter_spacing
                pen=_FlattenPen(glyph_set,tolerance/scale)
                glyph_set[name].draw(pen); pen._finish(False)
                geometry=_contours_geometry(pen.contours,scale)
                advance=metrics.get(name,(font['head'].unitsPerEm,0))[0]*scale
                glyphs.append((geometry,cursor,advance))
                cursor+=advance; previous=name
            lines.append((glyphs,cursor))
        maxwidth=max((width for _,width in lines),default=0)
        if radius and maxwidth>2*math.pi*radius:
            raise ValueError('The text wraps beyond a full circle. Increase the radius or reduce text size.')
        geometries=[]
        for row,(glyphs,width) in enumerate(lines):
            shift=0 if alignment=='Left' else (maxwidth-width)/(2 if alignment=='Center' else 1)
            for geometry,x,advance in glyphs:
                if geometry.is_empty: continue
                if radius:
                    theta=(x+advance/2-width/2)/radius
                    geometry=translate(geometry,xoff=-advance/2)
                    geometry=rotate(geometry,-math.degrees(theta),origin=(0,0))
                    geometry=translate(geometry,xoff=radius*math.sin(theta),yoff=radius*math.cos(theta)-radius)
                else:
                    geometry=translate(geometry,xoff=x+shift,yoff=-row*height*line_spacing)
                geometries.append(geometry)
        if not geometries: return []
        return _geometry_paths(unary_union(geometries))


def _unwelded_text(text, filename, height, tolerance, line_spacing, spacing, alignment, radius):
    """Optional-dependency fallback preserves outlines without automatic welding."""
    import math
    from PlotterEditing import transform
    with TTFont(filename,lazy=False) as font:
        glyphs=font.getGlyphSet(); cmap=font.getBestCmap() or {}; scale=height/font['head'].unitsPerEm
        lines=[]
        for line in text.split('\n'):
            cursor=0; previous=None; parts=[]
            for char in line:
                if ord(char) not in cmap: raise ValueError('This font does not contain '+char+'. Choose another font.')
                name=cmap[ord(char)]
                if previous: cursor+=_kerning(font,previous,name)*scale+spacing
                pen=_FlattenPen(glyphs,tolerance/scale); glyphs[name].draw(pen); pen._finish(False)
                advance=font['hmtx'].metrics[name][0]*scale
                parts.append((_contours_paths(pen.contours,scale,0,0,name),cursor,advance))
                cursor+=advance; previous=name
            lines.append((parts,cursor))
        width=max(w for _,w in lines)
        if radius and width>2*math.pi*radius: raise ValueError('Increase the circle radius to fit this text.')
        result=[]
        for row,(parts,w) in enumerate(lines):
            shift=0 if alignment=='Left' else (width-w)/(2 if alignment=='Center' else 1)
            for paths,x,advance in parts:
                if radius:
                    theta=(x+advance/2-w/2)/radius; c=math.cos(theta); s=math.sin(theta)
                    matrix=[c,-s,s,c,radius*s-c*advance/2,radius*c-radius+s*advance/2]
                else: matrix=[1,0,0,1,x+shift,-row*height*line_spacing]
                result.extend(transform(paths,matrix))
        return result
