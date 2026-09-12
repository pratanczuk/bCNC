"""Path-smoothing utilities: Ramer-Douglas-Peucker + Chaikin subdivision."""

from bmath import Vector
from bpath import Path, Segment


# --------------------------------------------------------------------------
def _douglas_peucker(pts, tol):
    """Reduce a polyline via Ramer-Douglas-Peucker. Returns reduced list."""
    if len(pts) <= 2:
        return list(pts)
    x0, y0 = pts[0]
    x1, y1 = pts[-1]
    dx, dy = x1 - x0, y1 - y0
    length_sq = dx * dx + dy * dy
    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(pts) - 1):
        px = pts[i][0] - x0
        py = pts[i][1] - y0
        if length_sq > 0:
            dist = abs(px * dy - py * dx) / length_sq ** 0.5
        else:
            dist = (px * px + py * py) ** 0.5
        if dist > max_dist:
            max_dist, max_idx = dist, i
    if max_dist > tol:
        left = _douglas_peucker(pts[:max_idx + 1], tol)
        right = _douglas_peucker(pts[max_idx:], tol)
        return left[:-1] + right
    return [pts[0], pts[-1]]


# --------------------------------------------------------------------------
def _chaikin(pts, iterations, closed):
    """Chaikin corner-cutting subdivision, preserving open/closed topology."""
    for _ in range(iterations):
        out = []
        n = len(pts)
        limit = n if closed else n - 1
        for i in range(limit):
            a = pts[i]
            b = pts[(i + 1) % n]
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        if not closed:
            out = [pts[0]] + out + [pts[-1]]
        pts = out
    return pts


# --------------------------------------------------------------------------
def smooth_path(path, tolerance=0.1, iterations=3):
    """Smooth a bpath.Path using Douglas-Peucker + Chaikin subdivision.

    Contiguous LINE segments are simplified then smoothed. Arc segments
    (G2/G3) are forwarded unchanged.  Returns a new Path with the same
    name and color.
    """
    result = Path(path.name, path.color)

    def _emit(run):
        if len(run) < 2:
            return
        closed = (
            (run[-1][0] - run[0][0]) ** 2 + (run[-1][1] - run[0][1]) ** 2
            < 1e-8
        )
        pts = _douglas_peucker(run, tolerance) if tolerance > 0 else list(run)
        if len(pts) < 2:
            return
        if iterations > 0:
            pts = _chaikin(pts, iterations, closed)
        if closed and len(pts) >= 2:
            pts.append(pts[0])  # close the loop after Chaikin opens it
        s = Vector(pts[0][0], pts[0][1])
        for p in pts[1:]:
            e = Vector(p[0], p[1])
            result.append(Segment(Segment.LINE, s, e))
            s = e

    run = []
    prev_end = None
    for seg in path:
        if seg.type == Segment.LINE:
            if not run:
                run.append((seg.A[0], seg.A[1]))
            elif prev_end is not None:
                # flush on discontinuity
                if (seg.A[0] - prev_end[0]) ** 2 + (seg.A[1] - prev_end[1]) ** 2 > 1e-8:
                    _emit(run)
                    run = [(seg.A[0], seg.A[1])]
            run.append((seg.B[0], seg.B[1]))
            prev_end = (seg.B[0], seg.B[1])
        else:
            _emit(run)
            run = []
            prev_end = None
            result.append(seg)

    _emit(run)
    return result
