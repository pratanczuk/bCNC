"""Bitmap preparation and vector tracing helpers for bCNC image plugins."""

import math

import numpy as np


def _cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for bitmap contour tracing") from exc
    return cv2


def foreground_mask(image, tolerance):
    """Return the opaque pixels unlike the median colour at the image edge."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.int16)
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3] > 0
    border = np.concatenate(
        (rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]), axis=0
    )
    background = np.median(border, axis=0)
    distance = np.sqrt(np.sum((rgb - background) ** 2, axis=2))
    return (alpha & (distance > max(0, tolerance))).astype(np.uint8)


def threshold_mask(image, threshold, invert=False):
    """Create a foreground mask from a luminance threshold and transparency."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    luminance = np.asarray(image.convert("L"), dtype=np.uint8)
    if invert:
        mask = luminance >= threshold
    else:
        mask = luminance <= threshold
    return (mask & (rgba[:, :, 3] > 0)).astype(np.uint8)


def prepare_mask(image, threshold, invert, remove_background, tolerance):
    """Combine thresholding with optional automatic edge-colour removal."""
    mask = threshold_mask(image, threshold, invert)
    if remove_background:
        mask &= foreground_mask(image, tolerance)
    return mask


def multi_threshold_masks(image, levels, invert, remove_background, tolerance):
    """Return nested masks covering evenly spaced luminance thresholds."""
    levels = max(1, int(levels))
    return [
        prepare_mask(
            image,
            int((index + 1) * 255 / (levels + 1)),
            invert,
            remove_background,
            tolerance,
        )
        for index in range(levels)
    ]


def trace_image(
    image,
    mode="Contours",
    threshold=128,
    levels=4,
    invert=False,
    remove_background=True,
    tolerance=24,
    minimum_area=16,
    simplify=1.0,
    spur_length=4,
    bleed_pixels=0,
):
    """Trace an image and return ``(name, points, closed)`` records."""
    records = []
    if mode == "Multi-threshold":
        for level, mask in enumerate(
            multi_threshold_masks(
                image, levels, invert, remove_background, tolerance
            ),
            start=1,
        ):
            records.extend(
                ("ImageTrace-%d" % level, points, True)
                for points in contours(
                    mask, minimum_area=minimum_area, simplify=simplify
                )
            )
    elif mode == "Centerline":
        mask = prepare_mask(
            image, threshold, invert, remove_background, tolerance
        )
        skeleton = prune_spurs(zhang_suen(mask), spur_length)
        records.extend(
            ("ImageTrace-centerline", points, False)
            for points in skeleton_paths(skeleton)
        )
    elif mode == "Print then cut":
        if remove_background:
            mask = foreground_mask(image, tolerance)
        else:
            mask = prepare_mask(image, threshold, invert, False, tolerance)
        records.extend(
            ("PrintThenCut", points, True)
            for points in print_then_cut_contour(
                mask,
                minimum_area=minimum_area,
                simplify=simplify,
                bleed_pixels=bleed_pixels,
            )
        )
    else:
        mask = prepare_mask(
            image, threshold, invert, remove_background, tolerance
        )
        records.extend(
            ("ImageTrace", points, True)
            for points in contours(
                mask, minimum_area=minimum_area, simplify=simplify
            )
        )
    return records


def _binary(mask):
    return (np.asarray(mask, dtype=np.uint8) > 0).astype(np.uint8) * 255


def contours(mask, external=False, minimum_area=0, simplify=0):
    """Extract pixel contours, optionally retaining only external outlines."""
    cv2 = _cv2()
    mode = cv2.RETR_EXTERNAL if external else cv2.RETR_TREE
    result = cv2.findContours(_binary(mask), mode, cv2.CHAIN_APPROX_NONE)
    found = result[-2]
    paths = []
    for contour in found:
        if abs(cv2.contourArea(contour)) < minimum_area:
            continue
        if simplify > 0:
            contour = cv2.approxPolyDP(contour, simplify, True)
        points = [(int(point[0][0]), int(point[0][1])) for point in contour]
        if len(points) >= 3:
            paths.append(points)
    return paths


def print_then_cut_contour(mask, minimum_area=0, simplify=0, bleed_pixels=0):
    """Return one external loop surrounding the isolated foreground mask."""
    cv2 = _cv2()
    binary = _binary(mask)
    radius = max(0, int(math.ceil(bleed_pixels)))
    if radius:
        size = radius * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        binary = cv2.dilate(binary, kernel)
    loops = contours(binary, external=True, minimum_area=minimum_area, simplify=simplify)
    if not loops:
        return []
    return [max(loops, key=lambda points: abs(cv2.contourArea(np.asarray(points))))]


_NEIGHBOURS = (
    (-1, 0), (-1, 1), (0, 1), (1, 1),
    (1, 0), (1, -1), (0, -1), (-1, -1),
)


def zhang_suen(mask):
    """Thin a binary image with the Zhang--Suen skeletonization algorithm."""
    pixels = (np.asarray(mask, dtype=np.uint8) > 0).astype(np.uint8)
    if pixels.ndim != 2:
        raise ValueError("A two-dimensional bitmap mask is required")
    changed = True
    while changed:
        changed = False
        for first_pass in (True, False):
            delete = []
            for row in range(1, pixels.shape[0] - 1):
                for column in range(1, pixels.shape[1] - 1):
                    if not pixels[row, column]:
                        continue
                    neighbours = [
                        pixels[row + dr, column + dc]
                        for dr, dc in _NEIGHBOURS
                    ]
                    count = sum(neighbours)
                    transitions = sum(
                        neighbours[index] == 0
                        and neighbours[(index + 1) % 8] == 1
                        for index in range(8)
                    )
                    if count < 2 or count > 6 or transitions != 1:
                        continue
                    north, east, south, west = (
                        neighbours[0], neighbours[2], neighbours[4], neighbours[6]
                    )
                    if first_pass:
                        valid = north * east * south == 0 and east * south * west == 0
                    else:
                        valid = north * east * west == 0 and north * south * west == 0
                    if valid:
                        delete.append((row, column))
            if delete:
                changed = True
                for row, column in delete:
                    pixels[row, column] = 0
    return pixels


def _neighbours(point, pixels):
    row, column = point
    return [
        (row + dr, column + dc)
        for dr, dc in _NEIGHBOURS
        if 0 <= row + dr < pixels.shape[0]
        and 0 <= column + dc < pixels.shape[1]
        and pixels[row + dr, column + dc]
    ]


def prune_spurs(pixels, length):
    """Remove endpoint branches no longer than *length* pixels."""
    pixels = (np.asarray(pixels, dtype=np.uint8) > 0).astype(np.uint8)
    if length <= 0:
        return pixels
    changed = True
    while changed:
        changed = False
        endpoints = [
            (row, column)
            for row, column in zip(*np.nonzero(pixels))
            if len(_neighbours((row, column), pixels)) == 1
        ]
        for endpoint in endpoints:
            if not pixels[endpoint]:
                continue
            branch = [endpoint]
            previous = None
            current = endpoint
            while len(_neighbours(current, pixels)) <= 2:
                candidates = [
                    point for point in _neighbours(current, pixels) if point != previous
                ]
                if not candidates:
                    break
                previous, current = current, candidates[0]
                branch.append(current)
            if len(branch) - 1 <= length and len(_neighbours(current, pixels)) >= 3:
                for row, column in branch[:-1]:
                    pixels[row, column] = 0
                changed = True
    return pixels


def skeleton_paths(pixels):
    """Turn a one-pixel skeleton into open and closed pixel polylines."""
    pixels = (np.asarray(pixels, dtype=np.uint8) > 0).astype(np.uint8)
    nodes = set(zip(*np.nonzero(pixels)))
    edge_seen = set()

    def edge(a, b):
        return tuple(sorted((a, b)))

    def degree(point):
        return len(_neighbours(point, pixels))

    paths = []
    starts = [point for point in nodes if degree(point) != 2]
    for start in starts:
        for next_point in _neighbours(start, pixels):
            if edge(start, next_point) in edge_seen:
                continue
            path = [start]
            previous, current = start, next_point
            edge_seen.add(edge(previous, current))
            while degree(current) == 2:
                path.append(current)
                candidates = [
                    point for point in _neighbours(current, pixels) if point != previous
                ]
                if not candidates:
                    break
                previous, current = current, candidates[0]
                edge_seen.add(edge(previous, current))
            path.append(current)
            if len(path) > 1:
                paths.append([(column, row) for row, column in path])

    for start in nodes:
        neighbours = _neighbours(start, pixels)
        if not neighbours or edge(start, neighbours[0]) in edge_seen:
            continue
        path = [start]
        previous, current = start, neighbours[0]
        edge_seen.add(edge(previous, current))
        while current != start:
            path.append(current)
            candidates = [
                point for point in _neighbours(current, pixels) if point != previous
            ]
            if not candidates:
                break
            previous, current = current, candidates[0]
            edge_seen.add(edge(previous, current))
        if current == start:
            path.append(start)
        if len(path) > 2:
            paths.append([(column, row) for row, column in path])
    return paths