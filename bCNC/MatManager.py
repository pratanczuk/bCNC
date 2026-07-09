"""
MatManager.py  --  Foil / vinyl cutting-mat workspace helpers for bCNC.

Implements (as standalone module so main bCNC files stay clean):

  Req A/D  drawCuttingMat()    ← called from CNCCanvas, lives here as helpers
  Req E    MatStatusPanel       hidden-by-default sensor-status frame
  Req F    (buttons wired in ControlPage.py)
  Req G    CuttingMatSettingsDialog   modal plotter-settings window
  Req H    apply_dragknife_auto()     in-memory drag-knife pipeline
"""

import re
import tkinter as tk
from tkinter import (
    TOP, LEFT, RIGHT, BOTTOM,
    X, Y, BOTH, YES, NO,
    W, E, N, S, NSEW, EW,
    Frame, Label, Button, Entry, Checkbutton, Toplevel,
    BooleanVar, DoubleVar,
)

from CNC import CNC

# ── Default mat dimensions (mm) ──────────────────────────────────────────────
MAT_WIDTH_DEFAULT  = 300.0
MAT_HEIGHT_DEFAULT = 300.0

# Pin letter reported by grblHAL for the physical mat-present sensor.
# grblHAL sends |Pn:P when the probe input is active (mat on platen);
# absence of P in the Pn: field (or no Pn: field at all) means mat is absent.
MAT_SENSOR_PIN = "P"


# =============================================================================
# Req G  –  Modal plotter-settings dialog
# =============================================================================
class CuttingMatSettingsDialog:
    """
    Blocking (modal) Toplevel window.

    Edits CNC.vars keys:
        mat_pressure        float  (mm / downforce equivalent)
        mat_speed           float  (mm/min feed rate)
        mat_knife_offset    float  (mm from swivel axis to blade tip)
        mat_width           float  (mm)
        mat_height          float  (mm)
        mat_auto_dragknife  bool   (Req H toggle)

    Usage:
        dlg = CuttingMatSettingsDialog(parent_widget, app)
        # blocks until the user closes it
    """

    def __init__(self, parent, app):
        self.app    = app
        self.result = None          # True = saved, False = cancelled

        top = Toplevel(parent)
        top.title("Plotter Settings")
        top.resizable(False, False)
        top.grab_set()              # modal – blocks main window
        self._top = top

        pad = {"padx": 8, "pady": 4}

        # ── parameter fields ─────────────────────────────────────────────
        frm = Frame(top, padx=14, pady=10)
        frm.pack(fill=BOTH, expand=YES)

        def _row(r, text, var):
            Label(frm, text=text, anchor=W).grid(
                row=r, column=0, sticky=W, **pad)
            Entry(frm, textvariable=var, width=12).grid(
                row=r, column=1, **pad)

        self._pressure     = DoubleVar(value=CNC.vars.get("mat_pressure",     500.0))
        self._speed        = DoubleVar(value=CNC.vars.get("mat_speed",        500.0))
        self._knife_offset = DoubleVar(value=CNC.vars.get("mat_knife_offset", 0.5))
        self._load_dist    = DoubleVar(value=CNC.vars.get("mat_load_distance", 20.0))
        self._mat_w        = DoubleVar(value=CNC.vars.get("mat_width",        MAT_WIDTH_DEFAULT))
        self._mat_h        = DoubleVar(value=CNC.vars.get("mat_height",       MAT_HEIGHT_DEFAULT))

        _row(0, "Pressure (PWM 0–1000, M3 S value):", self._pressure)
        _row(1, "Speed (Feed Rate, mm/min):",   self._speed)
        _row(2, "Knife Offset (mm):",           self._knife_offset)
        _row(3, "Load Distance (mm):",        self._load_dist)

        Frame(frm, height=2, bd=1, relief="sunken").grid(
            row=4, column=0, columnspan=2, sticky=EW, padx=8, pady=6)

        _row(5, "Mat Width (mm):",  self._mat_w)
        _row(6, "Mat Height (mm):", self._mat_h)

        Frame(frm, height=2, bd=1, relief="sunken").grid(
            row=7, column=0, columnspan=2, sticky=EW, padx=8, pady=6)

        # ── Req H auto drag-knife toggle ──────────────────────────────────
        self._auto_dk = BooleanVar(
            value=bool(CNC.vars.get("mat_auto_dragknife", False)))
        Checkbutton(
            frm,
            text="Automatically apply drag-knife\ncompensation before sending to machine",
            variable=self._auto_dk,
            anchor=W,
            justify=LEFT,
        ).grid(row=8, column=0, columnspan=2, sticky=W, **pad)

        # ── dialog buttons ───────────────────────────────────────────────
        bf = Frame(top, padx=10, pady=8)
        bf.pack(fill=X)
        Button(bf, text="Cancel", command=self._cancel).pack(side=RIGHT, padx=4)
        Button(bf, text="Save",   command=self._save,
               default="active").pack(side=RIGHT, padx=4)

        top.bind("<Return>", lambda _e: self._save())
        top.bind("<Escape>", lambda _e: self._cancel())

        # centre over parent
        top.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        tw, th = top.winfo_width(), top.winfo_height()
        top.geometry(f"+{px + (pw - tw)//2}+{py + (ph - th)//2}")

        parent.wait_window(top)

    # ------------------------------------------------------------------
    def _save(self):
        try:
            CNC.vars["mat_pressure"]      = float(self._pressure.get())
            CNC.vars["mat_speed"]         = float(self._speed.get())
            CNC.vars["mat_knife_offset"]  = float(self._knife_offset.get())
            CNC.vars["mat_load_distance"] = float(self._load_dist.get())
            CNC.vars["mat_width"]         = float(self._mat_w.get())
            CNC.vars["mat_height"]        = float(self._mat_h.get())
            CNC.vars["mat_auto_dragknife"]= bool(self._auto_dk.get())
        except (ValueError, tk.TclError):
            pass
        # Write M3 S<pressure> into every Header block line that contains M3
        self._apply_pressure_to_header()
        self.result = True
        self._top.destroy()

    def _apply_pressure_to_header(self):
        """Patch M3/M03 lines with S<mat_pressure> in both the header
        template (gcode.header) and the currently loaded Header block.

        Patching the template ensures every subsequent file load also
        gets the correct value, not just the block that is in memory now.
        """
        gcode = self.app.gcode
        if not gcode:
            return
        pressure = int(round(CNC.vars.get("mat_pressure", 500.0)))

        def _patch_line(line):
            """Return line with M3/M03 S-value replaced, or None if unchanged."""
            if not re.search(r'(?i)\bM0?3\b', line):
                return None
            stripped = re.sub(r'(?i)\bS[\d.]+', '', line).strip()
            newline  = re.sub(r'(?i)(M0?3)\b', rf'\1 S{pressure}', stripped)
            newline  = re.sub(r'  +', ' ', newline).strip()
            return newline if newline != line else None

        # 1. Update the header template so future file loads get the right S value
        if gcode.header:
            patched_lines = []
            changed = False
            for ln in gcode.header.splitlines():
                result = _patch_line(ln)
                patched_lines.append(result if result is not None else ln)
                if result is not None:
                    changed = True
            if changed:
                gcode.header = "\n".join(patched_lines)

        # 2. Patch the live Header block(s) in the currently loaded file
        if not gcode.blocks:
            return
        undoinfo = []
        for bid, block in enumerate(gcode.blocks):
            if block.name() != "Header":
                continue
            for lid, line in enumerate(block):
                result = _patch_line(line)
                if result is not None:
                    undoinfo.append(gcode.setLineUndo(bid, lid, result))
        if undoinfo:
            gcode.addUndo(undoinfo)
            # This is a settings-driven auto-patch, not a user edit —
            # reset the modified flag so quit() never shows a "save?" dialog.
            gcode._modified = False
            # Refresh the editor list so the new S value is visible immediately
            self.app.editor.fill()

    def _cancel(self):
        self.result = False
        self._top.destroy()


# =============================================================================
# =============================================================================
# Req E  –  Always-visible mat status panel
# =============================================================================
class MatStatusPanel(Frame):
    """
    A thin toolbar Frame shown permanently above the canvas area.

    Displays only the mat-present sensor status read from grblHAL telemetry:
        |Pn:P   →  Mat: DETECTED  (probe input active)
        |Pn:    →  Mat: not detected

    Load/Unload/Settings buttons are available elsewhere in the UI and are
    intentionally not duplicated here.
    """

    def __init__(self, master, app):
        Frame.__init__(self, master, relief="raised", bd=1,
                       background="#ffffd0")
        self.app        = app
        self._visible   = True
        self._prev_pins = ""
        self._poll_id   = None   # after() handle for the sensor-poll loop

        Label(self,
              text="✂ Cutting Mat",
              font=("Helvetica", 9, "bold"),
              background="#ffffd0",
              ).pack(side=LEFT, padx=6)

        self._status_lbl = Label(self,
                                  text="Mat: not detected",
                                  background="#ffffd0",
                                  foreground="#888888")
        self._status_lbl.pack(side=LEFT, padx=8)

        # Kick off the sensor-poll loop after the Tk event loop is running.
        self.after(1000, self._poll)

    # ------------------------------------------------------------------
    def show(self):
        """Pack above the canvas (before canvasFrame). No-op if already visible."""
        if not self._visible:
            self.pack(side=TOP, fill=X,
                      before=self.app.canvasFrame)
            self._visible = True
        # Ensure the poll loop is running.
        if self._poll_id is None:
            self._poll_id = self.after(500, self._poll)

    def hide(self):
        if self._visible:
            try:
                self.pack_forget()
            except Exception:
                pass
            self._visible = False
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None

    def toggle(self):
        self.hide() if self._visible else self.show()

    # ------------------------------------------------------------------
    def _poll(self):
        """Periodic sensor poll (runs while the panel is visible).

        Sends the '?' realtime status command so grblHAL returns a fresh
        status report.  The GRBL1 parser then stores the 'Pn:' field value
        in CNC.vars["pins"]; we read that on the *next* poll cycle (the
        response arrives asynchronously a few ms later).

            |Pn:P   →  mat present   (probe input active)
            |Pn:    →  mat absent    (probe input inactive / field missing)
        """
        self._poll_id = None
        try:
            if getattr(self.app, 'serial', None) \
                    and getattr(self.app, 'mcontrol', None):
                self.app.mcontrol.viewStatusReport()  # sends b"?"
        except Exception:
            pass

        pins = CNC.vars.get("pins", "")
        if pins != self._prev_pins:
            self._prev_pins = pins
            if MAT_SENSOR_PIN in pins:
                self._status_lbl.config(
                    text="Mat: DETECTED \u2713", foreground="green")
            else:
                self._status_lbl.config(
                    text="Mat: not detected", foreground="#888888")

        # Always reschedule — panel is permanently visible.
        self._poll_id = self.after(2000, self._poll)

    # ------------------------------------------------------------------
    def updateSensorState(self):
        """
        Called from Application._monitorSerial() on every position update.
        Delegates to _poll() logic: sends '?' and checks the Pn: field
        reported by grblHAL.

            |Pn:P  → mat present   (probe / mat-sensor input active)
            |Pn:   → mat absent    (probe input inactive or field absent)
        """
        # If the poll loop is already running (panel visible) do nothing –
        # _poll() handles everything.  Only act when the panel is hidden so
        # we can auto-show it the moment grblHAL reports the mat.
        if self._visible:
            return

        pins = CNC.vars.get("pins", "")
        if MAT_SENSOR_PIN in pins:
            self._status_lbl.config(
                text="Mat: DETECTED \u2713", foreground="green")
            self.show()   # show() also starts the polling loop
        else:
            self._status_lbl.config(
                text="Mat: not detected", foreground="#888888")


# =============================================================================
# Req H  –  In-memory drag-knife auto-pipeline
# =============================================================================
def apply_dragknife_auto(app):
    """
    Transparently runs the bCNC DragKnife plugin on the entire loaded
    G-code buffer and replaces the raw paths with knife-compensated ones.

    Steps
    ─────
    1.  Record identity of all blocks currently in the buffer.
    2.  Select all blocks (plugin processes selected blocks only).
    3.  Override plugin 'offset' and 'feed' with values from CNC.vars.
    4.  Call plugin.execute() – appends drag-knife blocks to the buffer.
    5.  Collect newly added blocks (not in original set).
    6.  Replace the entire block list with only the drag-knife blocks,
        preserving undo history via setAllBlocksUndo().
    7.  Refresh editor and canvas.
    """
    if not app.gcode.blocks:
        return

    try:
        dk_plugin = app.tools["DragKnife"]
    except (KeyError, TypeError, AttributeError):
        # Plugin not loaded – silently skip
        return

    # 1. snapshot
    orig_ids = {id(b) for b in app.gcode.blocks}

    # 2. configure plugin parameters from CNC.vars
    dk_plugin["offset"]   = CNC.vars.get("mat_knife_offset", 0.5)
    dk_plugin["feed"]     = CNC.vars.get("mat_speed",        500.0)
    dk_plugin["simulate"] = False

    # 3. select only blocks that have exactly ONE continuous sub-path.
    #
    #    The dragknife plugin calls toPath(bid)[0], so it can only process
    #    single-contour blocks correctly.  Blocks with 0 paths (comments,
    #    warning text, empty blocks) or >1 paths (text glyph blocks, where
    #    each character is a separate G0-separated contour) must be excluded
    #    from the plugin and preserved verbatim in the final output.
    app.editor.selectAll()

    preserved_blocks = []   # blocks the plugin must NOT touch
    for bid in range(len(app.gcode.blocks)):
        block = app.gcode.blocks[bid]
        if block.name() in ("Header", "Footer"):
            continue
        npaths = len(app.gcode.toPath(bid))
        if npaths != 1:
            # Deselect this block so the plugin skips it
            pos = app.editor._blockPos[bid]
            if pos is not None:
                app.editor.selection_clear(pos)
            preserved_blocks.append(block)

    # 4. run – the plugin appends new blocks via gcode.insBlocks()
    dk_plugin.execute(app)

    # 5. partition the current block list into
    #      a) original Header / Footer blocks  – must be preserved
    #      b) new drag-knife content blocks    – the replacement payload
    orig_blocks_ordered = [b for b in app.gcode.blocks if id(b) in orig_ids]
    header_blocks = [b for b in orig_blocks_ordered if b.name() == "Header"]
    footer_blocks = [b for b in orig_blocks_ordered if b.name() == "Footer"]
    dk_blocks     = [b for b in app.gcode.blocks if id(b) not in orig_ids]

    if not dk_blocks:
        # plugin produced nothing (e.g. no valid paths) – leave as-is
        return

    # 6. reassemble: Header(s) + drag-knife content + preserved blocks
    #    (multi-path / zero-path blocks that the plugin skipped) + Footer(s)
    final_blocks = header_blocks + dk_blocks + preserved_blocks + footer_blocks
    app.addUndo(app.gcode.setAllBlocksUndo(final_blocks))

    # 7. refresh
    app.editor.fill()
    # Use drawAfter() instead of draw() so this is safe even when
    # apply_dragknife_auto fires via self.update() inside drawPaths()
    # (which sets _inDraw=True).  drawAfter() defers past any active draw.
    app.drawAfter()
    app.after(500, app.canvas.fit2Screen)
    app.setStatus("Drag-knife compensation applied automatically.")


# =============================================================================
# Req H2 – Compute drag-knife blocks for pre-send injection (non-destructive)
# =============================================================================
def _compute_dragknife_blocks(app):
    """
    Run the DragKnife plugin on a *temporary copy* of gcode.blocks and return
    the resulting knife-compensated block list WITHOUT modifying the real buffer.

    Called by run() just before gcode.compile() so that:
      • The editor always shows the original design.
      • Scaling / editing after load produces correct compensation at send time.

    Returns the full block list to hand to compile(), or None when the plugin
    is unavailable or produces no output (caller should compile the original).

    State restored on return: app.gcode.blocks, undo/redo stacks,
    editor selection.
    """
    if not app.gcode.blocks:
        return None

    try:
        dk_plugin = app.tools["DragKnife"]
    except (KeyError, TypeError, AttributeError):
        return None

    # Configure plugin from mat settings
    dk_plugin["offset"]   = CNC.vars.get("mat_knife_offset", 0.5)
    dk_plugin["feed"]     = CNC.vars.get("mat_speed",        500.0)
    dk_plugin["simulate"] = False

    # ── Save state ────────────────────────────────────────────────────────
    original_blocks = app.gcode.blocks
    saved_undo      = list(app.gcode.undoredo.undoList)
    saved_redo      = list(app.gcode.undoredo.redoList)

    # ── Give the plugin a working copy ───────────────────────────────────
    app.gcode.blocks = list(original_blocks)
    orig_ids = {id(b) for b in app.gcode.blocks}

    # Select valid single-contour blocks; deselect the rest
    app.editor.selectAll()
    preserved_blocks = []
    for bid in range(len(app.gcode.blocks)):
        block = app.gcode.blocks[bid]
        if block.name() in ("Header", "Footer"):
            continue
        npaths = len(app.gcode.toPath(bid))
        if npaths != 1:
            pos = app.editor._blockPos[bid]
            if pos is not None:
                app.editor.selection_clear(pos)
            preserved_blocks.append(block)

    # Suppress UI side-effects while the plugin runs
    orig_refresh = app.refresh
    app.refresh = lambda: None
    try:
        dk_plugin.execute(app)
    finally:
        app.refresh = orig_refresh

    # ── Collect results before restoring ─────────────────────────────────
    working_blocks = app.gcode.blocks

    # ── Restore original state fully ─────────────────────────────────────
    app.gcode.blocks = original_blocks
    app.gcode.undoredo.undoList[:] = saved_undo
    app.gcode.undoredo.redoList[:] = saved_redo
    app.editor.selectClear()

    # ── Assemble final block list ─────────────────────────────────────────
    orig_ordered  = [b for b in working_blocks if id(b) in orig_ids]
    header_blocks = [b for b in orig_ordered if b.name() == "Header"]
    footer_blocks = [b for b in orig_ordered if b.name() == "Footer"]
    dk_blocks     = [b for b in working_blocks if id(b) not in orig_ids]

    if not dk_blocks:
        return None

    return header_blocks + dk_blocks + preserved_blocks + footer_blocks


# =============================================================================
# Snap loaded design to mat origin (0, 0)
# =============================================================================
def snap_to_mat(app):
    """Translate all G-code blocks so the bounding box starts at (0, 0).

    Called via after_idle() right after a full file load so
    CNC.vars["xmin"] / "ymin" are already populated by draw().
    This is an automatic load-time adjustment, NOT a user edit:
      - the undo entry added by moveLines() is discarded
      - _modified is reset to False so the close-confirmation dialog
        is not triggered just because of the auto-snap.

    IMPORTANT: we MUST NOT call app.draw() directly here.
    drawPaths() calls self.update() periodically for large drawings, which
    processes all pending Tkinter events including after_idle callbacks.
    If apply_dragknife_auto is also pending it would fire INSIDE the draw
    loop and modify gcode.blocks while drawPaths() is iterating → corrupt
    drawing / frozen UI.  Using drawAfter() schedules the redraw safely
    AFTER all pending after_idle callbacks have completed.
    """
    xmin = CNC.vars.get("xmin", 1e9)
    ymin = CNC.vars.get("ymin", 1e9)

    # Sentinel: bCNC initialises these to 1 000 000 when no paths exist
    if xmin >= 999999.0 or ymin >= 999999.0:
        return

    dx = -xmin
    dy = -ymin

    # Already at mat origin – nothing to do
    if abs(dx) < 0.0001 and abs(dy) < 0.0001:
        return

    # Only translate actual content blocks.
    # Header and Footer contain absolute positioning commands (return-to-home,
    # spindle on/off) that must NOT be shifted – otherwise e.g. a "G0 Y0"
    # return-to-origin in the Footer becomes "G0 Y105.68" after the snap.
    items = [
        (bid, None)
        for bid in range(len(app.gcode.blocks))
        if app.gcode.blocks[bid].name() not in ("Header", "Footer")
    ]
    if not items:
        return

    app.gcode.moveLines(items, dx, dy)

    # Discard the undo entry and modified flag – this is a transparent
    # load-time adjustment, not a user edit that should prompt "save?"
    app.gcode.undoredo.reset()
    app.gcode._modified = False

    app.editor.fill()

    # Schedule a safe deferred redraw (300 ms) so we are fully out of any
    # active draw loop before the canvas re-renders the moved geometry.
    # fit2Screen runs 150 ms after that, once the canvas items are updated.
    app.drawAfter()
    app.after(500, app.canvas.fit2Screen)

    app.setStatus(
        f"Design snapped to mat origin "
        f"(shifted X{dx:+.3f} Y{dy:+.3f} mm)."
    )
