# SVGcode 0.2
# Converts SVG paths to g-code
# (c) 2018 - Tomas 'Harvie' Mudrunka
# https://github.com/harvie
# License: GPLv2+

# Usage:
# svgcode = SVGcode('./image.svg')
# for path in svgcode.get_gcode():
#   print(path['id'])
#   print(path['path'])

import numpy
from svgelements import SVG, Arc, Close, Line, Move, Path, Shape, Text


class SVGcode:
    def __init__(self, filepath=None):
        self._filepath = filepath

    def path2gcode(self, path, samples_per_unit=100, d=4):
        gcode = []
        if isinstance(path, str):
            path = Path(path)

        # Pre-build the format string once; avoid round() per call.
        _fmt = f"%.{d}f"

        def rv(v, _fmt=_fmt):
            s = _fmt % v
            s = s.rstrip("0")
            return s[:-1] if s[-1] == "." else s

        for segment in path:
            if isinstance(segment, Move):
                gcode.append(f"G0 X{rv(segment.end.x)} Y{rv(-segment.end.y)}")
            elif isinstance(segment, (Line, Close)):
                gcode.append(f"G1 X{rv(segment.end.x)} Y{rv(-segment.end.y)}")
            elif (isinstance(segment, Arc)
                  and abs(segment.rx - segment.ry) < 1e-9):
                # Strictly speaking, svg arcs can be non circular,
                # whereas gcode only permits circular arcs.
                garc = "G02" if segment.sweep > 0 else "G03"
                gcode.append(" ".join([
                    f"{garc}", f"X{rv(segment.end.x)}",
                    f"Y{rv(-segment.end.y)}", f"R{rv(segment.rx)}"
                ]))
            else:  # Non-circular arc, Cubic or Quad Bezier Curves.
                # Only compute arc length (expensive) when actually needed.
                subdiv = max(1, round(segment.length(
                    error=1e-5) * samples_per_unit))
                t = numpy.linspace(0, 1, subdiv, endpoint=True)[1:]
                pts = segment.npoint(t)
                # Vectorized rounding: numpy round+tolist avoids per-point
                # rv() call overhead for the common bezier subdivision path.
                xs = pts[:, 0].round(d).tolist()
                ys = (-pts[:, 1]).round(d).tolist()
                gcode += [f"G1 X{x} Y{y}" for x, y in zip(xs, ys)]

        # Return a list; callers join if they need a string.
        return gcode

    # ------------------------------------------------------------------
    def _text2gcode(self, element, scale, digits):
        """
        Convert an SVG Text element to gcode using matplotlib's FreeType-based
        font renderer.

        matplotlib is already a bCNC dependency (Pillow/numpy imply it in
        most setups).  If it is unavailable, returns None so the caller can
        fall back to a warning block.

        Coordinate mapping
        ------------------
        SVG text anchor (el.x, el.y) is the baseline-left corner in SVG pixel
        units.  matplotlib TextPath at size=1 produces glyph outlines in
        em-space where 1 unit ≈ 1 em (the font_size in SVG pixels).

        Steps:
          glyph unit → SVG pixels : multiply by font_size
          SVG pixels  → output mm  : multiply by scale
          Y flip      : SVG y-down → CNC y-up via negation
        """
        try:
            from matplotlib.textpath import TextPath
            from matplotlib.font_manager import FontProperties
            import matplotlib.path as mpath
            import logging as _logging
            # Suppress "findfont: Font family not found" chatter.
            # matplotlib silently falls back to the best available match.
            _logging.getLogger('matplotlib.font_manager').setLevel(
                _logging.ERROR)
        except ImportError:
            return None

        txt = (element.text or "").strip()
        if not txt:
            return []

        font_size   = float(element.font_size or 12.0)
        font_family = element.font_family or "sans-serif"
        weight = str((element.values or {}).get("font-weight", "normal"))
        style  = str((element.values or {}).get("font-style",  "normal"))

        # CSS font-family is a comma-separated priority list
        families = [f.strip().strip("'\"") for f in font_family.split(",")]

        # For heavy/black weights, append system-available bold alternatives so
        # matplotlib finds the closest match without degenerating to a roman face.
        _wv = 400
        if str(weight).isdigit():
            _wv = int(weight)
        elif str(weight).lower() in ('black', 'heavy', 'ultrabold',
                                     'ultra-bold', 'extrabold', 'extra-bold'):
            _wv = 900
        elif str(weight).lower() == 'bold':
            _wv = 700
        if _wv >= 700:
            families = families + [
                'Liberation Sans', 'Carlito',
                'Nimbus Sans', 'NimbusSans L',
                'FreeSans', 'Ubuntu',
                'DejaVu Sans', 'sans-serif',
            ]

        fp = FontProperties(family=families, weight=weight,
                            style=style, size=1.0)
        tp = TextPath((0, 0), txt, prop=fp)

        # Scaling: 1 em-unit → font_size SVG px → mm
        coord_scale = font_size * scale
        ox = float(element.x or 0) * scale   # baseline x in output units
        oy = -float(element.y or 0) * scale  # baseline y, Y flipped

        _fmt = f"%.{digits}f"

        def rv(v):
            s = _fmt % v
            s = s.rstrip("0")
            return s[:-1] if s[-1] == "." else s

        MOVETO    = mpath.Path.MOVETO
        LINETO    = mpath.Path.LINETO
        CURVE3    = mpath.Path.CURVE3
        CURVE4    = mpath.Path.CURVE4
        CLOSEPOLY = mpath.Path.CLOSEPOLY

        gcode = []
        current = numpy.zeros(2)
        contour_start = numpy.zeros(2)

        for verts, code in tp.iter_segments():
            if code == MOVETO:
                current = numpy.array([verts[0], verts[1]])
                contour_start = current.copy()
                x = current[0] * coord_scale + ox
                y = current[1] * coord_scale + oy
                gcode.append(f"G0 X{rv(x)} Y{rv(y)}")

            elif code == LINETO:
                current = numpy.array([verts[0], verts[1]])
                x = current[0] * coord_scale + ox
                y = current[1] * coord_scale + oy
                gcode.append(f"G1 X{rv(x)} Y{rv(y)}")

            elif code == CURVE3:
                # verts = [ctrl_x, ctrl_y, end_x, end_y]
                cp = numpy.array([verts[0], verts[1]])
                ep = numpy.array([verts[2], verts[3]])
                # Subdivide quadratic bezier B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
                t = numpy.linspace(0, 1, 9)[1:]  # 8 line segments
                u = 1.0 - t
                pts = (numpy.outer(u * u, current)
                       + numpy.outer(2 * u * t, cp)
                       + numpy.outer(t * t, ep))
                for p in pts:
                    gcode.append(
                        f"G1 X{rv(p[0]*coord_scale+ox)}"
                        f" Y{rv(p[1]*coord_scale+oy)}")
                current = ep

            elif code == CURVE4:
                # verts = [c1x, c1y, c2x, c2y, end_x, end_y]
                c1 = numpy.array([verts[0], verts[1]])
                c2 = numpy.array([verts[2], verts[3]])
                ep = numpy.array([verts[4], verts[5]])
                # Subdivide cubic bezier
                t = numpy.linspace(0, 1, 9)[1:]
                u = 1.0 - t
                pts = (numpy.outer(u ** 3, current)
                       + numpy.outer(3 * u ** 2 * t, c1)
                       + numpy.outer(3 * u * t ** 2, c2)
                       + numpy.outer(t ** 3, ep))
                for p in pts:
                    gcode.append(
                        f"G1 X{rv(p[0]*coord_scale+ox)}"
                        f" Y{rv(p[1]*coord_scale+oy)}")
                current = ep

            elif code == CLOSEPOLY:
                x = contour_start[0] * coord_scale + ox
                y = contour_start[1] * coord_scale + oy
                gcode.append(f"G1 X{rv(x)} Y{rv(y)}")
                current = contour_start.copy()

        return gcode

    def get_gcode(self,
                  scale=1.0 / 96.0,
                  samples_per_unit=100,
                  digits=4,
                  ppi=96.0):
        """
        Parse gcode from an SVG file.

        scale: unit scaling between svg pixels and desired units. 1.0/96.0 is inches.
        subdivratio: How many subdivisions per unit? 1/100th inch steps.
        digits: How many digits of gcode accuracy.
        ppi: pixels per inch of the file being loaded. 96 is standard.
        """
        gcode = []
        skipped_text = []
        transform = f"scale({scale:g})" if scale != 1.0 else None
        svg = SVG.parse(self._filepath, reify=False,
                        ppi=ppi, transform=transform)
        for element in svg.elements():
            if isinstance(element, Text):
                txt = (element.text or "").strip()
                if not txt:
                    continue
                # Try to render text via matplotlib's FreeType font engine.
                # Falls back to a warning block if matplotlib is unavailable.
                lines = self._text2gcode(element, scale, digits)
                if lines is not None:
                    gcode.append({
                        "id": element.id or f"text_{txt[:20]}",
                        "path": lines,
                    })
                else:
                    skipped_text.append(txt)
            elif isinstance(element, Shape):
                if not isinstance(element, Path):
                    # Skip fill-only non-Path shapes (Rect, Circle, etc.) that
                    # have no visible stroke.  These are decorative elements
                    # (background rects, icon fills) — converting them produces
                    # spurious cut paths.  Explicitly drawn <path> elements are
                    # always kept regardless of stroke.
                    stroke = getattr(element, 'stroke', None)
                    if stroke is None or str(stroke).strip().lower() in (
                            'none', 'transparent'):
                        continue
                    element = Path(element)
                gcode.append(
                    {
                        "id": element.id,
                        "path": self.path2gcode(
                            element.reify(), samples_per_unit, digits
                        ),
                    }
                )
        if skipped_text:
            gcode.append({
                "id": "_text_warning",
                "path": [],
                "skipped_text": skipped_text,
            })
        return gcode


