"""GUI-independent preparation and readiness policy for planar foil jobs."""

import copy
import math
import re
from itertools import chain

from CNC import CNC, Block


SETTING_FIELDS = {
    "mat_speed": ("Cutting speed", 500, False, None),
    "mat_pressure": ("Cutting pressure", 500, True, 1000),
    "mat_knife_offset": ("Blade offset", 0.5, True, None),
    "mat_overcut": ("Overcut", 0, True, None),
    "mat_width": ("Mat width", 300, False, None),
    "mat_height": ("Mat height", 300, False, None),
    "mat_load_distance": ("Load distance", 20, False, None),
}


def validate_settings(values):
    """Validate an entire settings draft before changing live configuration."""
    result = {}
    for key, (label, default, allow_zero, maximum) in SETTING_FIELDS.items():
        try:
            value = float(values[key])
        except (ValueError, TypeError, KeyError):
            raise ValueError(f"{label}: enter a number.") from None
        if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
            raise ValueError(f"{label}: enter a finite {'nonnegative' if allow_zero else 'positive'} number.")
        if maximum is not None and value > maximum:
            raise ValueError(f"{label}: use a value from 0 to {maximum}.")
        result[key] = value
    if not isinstance(values.get("mat_auto_dragknife"), bool):
        raise ValueError("Choose whether to enable blade compensation.")
    result["mat_auto_dragknife"] = values["mat_auto_dragknife"]
    return result


def validate_blade_profile(values):
    draft = {key: default for key, (_, default, _, _) in SETTING_FIELDS.items()}
    for key in ("mat_knife_offset", "mat_overcut", "mat_auto_dragknife"):
        draft[key] = values.get(key)
    validated = validate_settings(draft)
    return {key: validated[key] for key in
            ("mat_knife_offset", "mat_overcut", "mat_auto_dragknife")}


def calibration_blocks():
    """Three independent, closed outlines using the existing blade-lift convention."""
    from PlotterShapes import SimpleRectangle
    from PlotterShapes import SimpleArc
    blocks = SimpleRectangle("Pressure test · square").calc(5, 5, 15, 15, 0, True)
    blocks += SimpleArc("Curve test · circle").calc(25, 10, 5, 0, 360)
    triangle = Block("Corner test · triangle")
    triangle.extend([CNC.grapid(x=35, y=5), CNC.grapid(z=0),
                     CNC.gline(x=45, y=5), CNC.gline(x=40, y=15),
                     CNC.gline(x=35, y=5), CNC.grapid(z=CNC.vars["safe"])])
    blocks.append(triangle)
    return blocks


def design_bounds(blocks):
    """Bounds of enabled design blocks, excluding machine header/footer."""
    boxes = [(b.xmin, b.ymin, b.xmax, b.ymax) for b in blocks
             if b.enable and b.name() not in ("Header", "Footer")
             and b.xmin <= b.xmax and b.ymin <= b.ymax]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def bounds_fit(bounds, width, height):
    if bounds is None or not all(math.isfinite(v) for v in (*bounds, width, height)):
        return False
    x0, y0, x1, y1 = bounds
    return width > 0 and height > 0 and x0 >= -0.01 and y0 >= -0.01 \
        and x1 <= width + 0.01 and y1 <= height + 0.01


def planned_cut_bounds(blocks, start=(0, 0, 0), startup=""):
    """Exact XY line/arc cutting bounds for a static, planar plotter job.

    This checks cutting geometry, not homing, machine travel, or blade height.
    Runtime expressions and coordinate-system changes need diagnostics review.
    """
    from bmath import Vector
    from bpath import Segment
    cnc = CNC()
    cnc.initPath(*start)
    boxes = []
    allowed = {0, 1, 2, 3, 4, 17, 20, 21, 90, 91, 90.1, 91.1, 94}
    startup_block = Block("Header")
    startup_block.extend(startup.splitlines())
    for block in chain((startup_block,), blocks):
        if not block.enable:
            continue
        design = block.name() not in ("Header", "Footer")
        for line in chain.from_iterable(block for _ in range(block.passes)):
            if line.lstrip().startswith("$") and not design:
                continue
            code = re.sub(r"\([^)]*\)|;.*", "", line).strip()
            if design and any(ch in code for ch in "[]%$_{}"):
                raise ValueError("Use static G-code for the cutting workspace; review expressions in diagnostics.")
            cmds = CNC.parseLine(line)
            if not cmds:
                if design and code:
                    raise ValueError("This job contains commands that cannot be checked in the cutting workspace.")
                continue
            if design:
                for cmd in cmds:
                    try:
                        value = float(cmd[1:])
                    except ValueError:
                        raise ValueError("Use static G-code for the cutting workspace; review expressions in diagnostics.")
                    if not math.isfinite(value) or (cmd[0].upper() == "G" and value not in allowed):
                        raise ValueError("This job uses unsupported motion or coordinate modes. Review it in diagnostics.")
                    if cmd[0].upper() in "ABCT" or (cmd[0].upper() == "M" and value not in (0, 1, 2, 3, 4, 5, 30)):
                        raise ValueError("This job uses extra axes or tool commands. Review it in diagnostics.")
                    if cmd[0].upper() not in "GXYZIJKRFSMNP":
                        raise ValueError("This job contains unsupported cutting commands. Review it in diagnostics.")
            # GRBL modal words apply to the whole line, independent of order.
            cmds = [c for c in cmds if c[0].upper() == "G"] + [c for c in cmds if c[0].upper() != "G"]
            cnc.motionStart(cmds)
            if design and cnc.gcode in (1, 2, 3) and (cnc.dx or cnc.dy or cnc.gcode in (2, 3)):
                start, end = Vector(cnc.x, cnc.y), Vector(cnc.xval, cnc.yval)
                center = Vector(*cnc.motionCenter()) if cnc.gcode in (2, 3) else None
                segment = Segment(cnc.gcode, start, end, center)
                boxes.append((segment.minx, segment.miny, segment.maxx, segment.maxy))
            cnc.motionEnd()
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def cut_settings_valid(speed, strength):
    return math.isfinite(speed) and speed > 0 and math.isfinite(strength) and 0 <= strength <= 1000


def apply_cut_settings(blocks, speed, strength, startup=""):
    """Apply material values to a disposable send buffer, retaining source art.

    Strength uses this fork's M3/S actuator convention. Explicit Z blade motion
    is preserved. Feed is converted when the cut file switches to inches.
    """
    if not cut_settings_valid(speed, strength):
        raise ValueError("Choose a positive cutting speed and strength from 0 to 1000.")
    result = copy.deepcopy(blocks)
    unit = 1.0
    motion = None
    startup_block = Block("Header")
    startup_block.extend(startup.splitlines())
    for block in chain((startup_block,), result):
        if not block.enable:
            continue
        for i, line in enumerate(block):
            words = CNC.parseLine(line)
            if not words:
                continue
            codes = {w.upper() for w in words}
            for word in words:
                if word[0].upper() == 'G':
                    try:
                        code = float(word[1:])
                    except ValueError:
                        continue
                    if code == 20:
                        unit = 25.4
                    elif code == 21:
                        unit = 1.0
                    elif code in (0, 1, 2, 3):
                        motion = code
            changed = False
            if codes.intersection({'M3', 'M03'}):
                words = [w for w in words if w[0].upper() != 'S']
                words.append(f'S{strength:.0f}')
                changed = True
            if block.name() not in ('Header', 'Footer') and motion in (1, 2, 3) and \
                    any(w[0].upper() in 'XYIJR' for w in words):
                words = [w for w in words if w[0].upper() != 'F']
                words.append(f'F{speed/unit:.4f}')
                changed = True
            if changed:
                block[i] = ' '.join(words)
    return result


def readiness(connected, state, running, bounds, width, height, confirmed):
    """A single readiness policy shared by the UI and Start keyboard shortcut."""
    if running:
        return "A cut is already running."
    if not connected:
        return "Connect your plotter in Prepare."
    if state != "Idle":
        return "Wait for the plotter to be idle, or open Advanced settings."
    if bounds is None:
        return "Import a design or add a shape first."
    if not bounds_fit(bounds, width, height):
        return "Move or resize your design to fit inside the mat."
    if not confirmed:
        return "Load the mat, then tick “Mat is loaded and aligned”."
    return ""
