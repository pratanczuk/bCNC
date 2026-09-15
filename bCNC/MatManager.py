"""Placement callback for imported artwork; document translation stays undoable."""

def snap_blocks_to_mat(app, block_ids):
    """Translate selected blocks so their bounding box starts at (0, 0)."""
    minx = miny = float("inf")
    found_path = False

    for bid in block_ids:
        if bid < 0 or bid >= len(app.gcode.blocks):
            continue
        for path in app.gcode.toPath(bid):
            x1, y1, x2, y2 = path.bbox()
            minx = min(minx, x1)
            miny = min(miny, y1)
            found_path = True

    if not found_path:
        return

    dx = -minx
    dy = -miny
    if abs(dx) < 0.0001 and abs(dy) < 0.0001:
        return

    items = [(bid, None) for bid in block_ids
             if 0 <= bid < len(app.gcode.blocks)
             and app.gcode.blocks[bid].name() not in ("Header", "Footer")]
    if not items:
        return

    app.gcode.moveLines(items, dx, dy)
    app.editor.fill()
    app.drawAfter()
    app.after(500, app.canvas.fit2Screen)
    app.setStatus(
        f"Imported drawing snapped to mat origin "
        f"(shifted X{dx:+.3f} Y{dy:+.3f} mm)."
    )
