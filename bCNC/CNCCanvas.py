# $Id: CNCCanvas.py,v 1.7 2014/10/15 15:04:06 bnv Exp $
#
# Author:       vvlachoudis@gmail.com
# Date: 24-Aug-2014

import math
import time
import sys

from tkinter import (
    TclError,
    FALSE,
    N,
    S,
    W,
    E,
    NS,
    EW,
    NSEW,
    CENTER,
    NONE,
    BOTH,
    LEFT,
    RIGHT,
    RAISED,
    HORIZONTAL,
    VERTICAL,
    ALL,
    DISABLED,
    LAST,
    SCROLL,
    UNITS,
    StringVar,
    IntVar,
    BooleanVar,
    Button,
    Canvas,
    Checkbutton,
    Frame,
    Label,
    Radiobutton,
    Scrollbar,
    OptionMenu,
)
import tkinter

import Utils
from CNC import CNC

ANTIALIAS_CHEAP = False


INSERT_WIDTH2 = 3
GANTRY_R = 4
GANTRY_X = GANTRY_R * 2  # 10
GANTRY_Y = GANTRY_R  # 5
GANTRY_H = GANTRY_R * 5  # 20
DRAW_TIME = 5  # Maximum draw time permitted

INSERT_COLOR = "Blue"
GANTRY_COLOR = "Red"
MARGIN_COLOR = "Magenta"
GRID_COLOR = "Gray"
BOX_SELECT = "Cyan"
TAB_COLOR = "DarkOrange"
TABS_COLOR = "Orange"
WORK_COLOR = "Orange"
CANVAS_COLOR = "White"

# ── Cutting-mat visual styling (Req A) ───────────────────────────────────────
MAT_COLOR        = "#ffffff"   # mat background fill
MAT_GRID_COLOR   = "#d8e3de"   # 10 mm grid lines inside mat
MAT_BORDER_COLOR = "#7da997"   # mat perimeter outline
MAT_WARN_COLOR   = "#ff4444"   # boundary-overflow warning outline

ENABLE_COLOR = "Black"
DISABLE_COLOR = "LightGray"
SELECT_COLOR = "Blue"
SELECT2_COLOR = "DarkCyan"
PROCESS_COLOR = "Green"

MOVE_COLOR = "DarkCyan"
RULER_COLOR = "Green"

INFO_COLOR = "Gold"

SELECTION_TAGS = ("sel", "sel2", "sel3", "sel4")

ACTION_SELECT = 0
ACTION_SELECT_SINGLE = 1
ACTION_SELECT_AREA = 2
ACTION_SELECT_DOUBLE = 3

ACTION_PAN = 10
ACTION_ORIGIN = 11

ACTION_MOVE = 20
ACTION_ROTATE = 21
ACTION_MAT_DRAG = 25   # Req B – click-and-drag gcode positioning on mat

ACTION_RULER = 30

SHIFT_MASK = 1
CONTROL_MASK = 4
ALT_MASK = 8
CONTROLSHIFT_MASK = SHIFT_MASK | CONTROL_MASK
CLOSE_DISTANCE = 5
MAXDIST = 10000
ZOOM = 1.25


DEF_CURSOR = ""
MOUSE_CURSOR = {
    ACTION_SELECT: DEF_CURSOR,
    ACTION_SELECT_AREA: "right_ptr",
    ACTION_PAN: "fleur",
    ACTION_ORIGIN: "cross",
    ACTION_MOVE: "hand1",
    ACTION_ROTATE: "exchange",
    ACTION_RULER: "tcross",
    ACTION_MAT_DRAG: "fleur",   # Req B
}


# -----------------------------------------------------------------------------
def mouseCursor(action):
    return MOUSE_CURSOR.get(action, DEF_CURSOR)


# =============================================================================
# Raise an alarm exception
# =============================================================================
class AlarmException(Exception):
    pass


# =============================================================================
# Drawing canvas
# =============================================================================
class CNCCanvas(Canvas):
    def __init__(self, master, app, *kw, **kwargs):
        Canvas.__init__(self, master, *kw, **kwargs)

        # Global variables
        self.app = app
        self.cnc = app.cnc
        self.gcode = app.gcode
        self.actionVar = IntVar()

        # Canvas binding
        self.bind("<Motion>", self.motion)

        self.bind("<Button-1>", self.click)
        self.bind("<B1-Motion>", self.buttonMotion)
        self.bind("<ButtonRelease-1>", self.release)
        self.bind("<Double-1>", self.double)

        self.bind("<B2-Motion>", self.pan)
        self.bind("<ButtonRelease-2>", self.panRelease)
        self.bind("<Button-4>", self.mouseZoomIn)
        self.bind("<Button-5>", self.mouseZoomOut)
        self.bind("<MouseWheel>", self.wheel)

        self.bind("<Shift-Button-4>", self.panLeft)
        self.bind("<Shift-Button-5>", self.panRight)
        self.bind("<Control-Button-4>", self.panUp)
        self.bind("<Control-Button-5>", self.panDown)

        self.bind("<Control-Key-Left>", self.panLeft)
        self.bind("<Control-Key-Right>", self.panRight)
        self.bind("<Control-Key-Up>", self.panUp)
        self.bind("<Control-Key-Down>", self.panDown)

        self.bind("<Escape>", self.actionCancel)
        self.bind("<Key>", self.handleKey)

        self.bind("<Control-Key-t>", self.__test)

        self.bind("<Control-Key-equal>", self.menuZoomIn)
        self.bind("<Control-Key-minus>", self.menuZoomOut)

        self.x0 = 0.0
        self.y0 = 0.0
        self.zoom = 1.0
        self.__tzoom = 1.0  # delayed zoom (temporary)
        self._items = {}

        self._x = self._y = 0
        self._xp = self._yp = 0
        # Start in the graphical move tool.  This is also reflected in the
        # Editor ribbon radiobutton through actionVar.
        self.action = ACTION_MOVE
        self.actionVar.set(ACTION_MOVE)
        self._mouseAction = None
        self._inDraw = False  # semaphore for parsing
        self._gantry1 = None
        self._gantry2 = None
        self._select = None
        self._margin = None
        self._amargin = None
        self._workarea = None
        self._vector = None
        self._lastActive = None
        self._lastGantry = None


        self.draw_axes = True  # Drawing flags
        self.draw_grid = True
        self.draw_margin = True
        self.draw_workarea = True
        self.draw_paths = True
        self.draw_rapid = True  # draw rapid motions
        self.draw_cutting_mat = True  # Req A – show physical mat background

        # Req A canvas items
        self._cuttingMat     = None
        self._matWarning     = None
        self._wx = self._wy = self._wz = 0.0  # work position
        self._dx = self._dy = self._dz = 0.0  # work-machine position

        self._vx0 = self._vy0 = self._vz0 = 0  # vector move coordinates
        self._vx1 = self._vy1 = self._vz1 = 0  # vector move coordinates


        self.reset()
        self.initPosition()

    # Calculate arguments for antialiasing
    def antialias_args(self, args, winc=0.5, cw=2):
        nargs = {}

        # set defaults
        nargs["width"] = 1
        nargs["fill"] = "#000"

        # get original args
        for arg in args:
            nargs[arg] = args[arg]
        if nargs["width"] == 0:
            nargs["width"] = 1

        # calculate width
        nargs["width"] += winc

        # calculate color
        cbg = self.winfo_rgb(self.cget("bg"))
        cfg = list(self.winfo_rgb(nargs["fill"]))
        cfg[0] = (cfg[0] + cbg[0] * cw) / (cw + 1)
        cfg[1] = (cfg[1] + cbg[1] * cw) / (cw + 1)
        cfg[2] = (cfg[2] + cbg[2] * cw) / (cw + 1)
        nargs["fill"] = "#{:02x}{:02x}{:02x}".format(
            int(cfg[0] / 256), int(cfg[1] / 256), int(cfg[2] / 256)
        )

        return nargs

    # Override alias method if antialiasing enabled:
    if ANTIALIAS_CHEAP:

        def create_line(self, *args, **kwargs):
            nkwargs = self.antialias_args(kwargs)
            super().create_line(*args, **nkwargs)
            return super().create_line(*args, **kwargs)

    # ----------------------------------------------------------------------
    def reset(self):
        self.zoom = 1.0

    # ----------------------------------------------------------------------
    # Set status message
    # ----------------------------------------------------------------------
    def status(self, msg):
        self.event_generate("<<Status>>", data=msg)

    # ----------------------------------------------------------------------
    def setMouseStatus(self, event):
        data = "%.4f %.4f %.4f" % self.canvas2xyz(
            self.canvasx(event.x), self.canvasy(event.y)
        )
        self.event_generate("<<Coords>>", data=data)

    # ----------------------------------------------------------------------
    # Update scrollbars
    # ----------------------------------------------------------------------
    def _updateScrollBars(self):
        """Update scroll region for new size"""
        bb = self.bbox("all")
        if bb is None:
            return
        x1, y1, x2, y2 = bb
        dx = x2 - x1
        dy = y2 - y1
        # make it 3 times bigger in each dimension
        # so when we zoom in/out we don't touch the borders
        self.configure(scrollregion=(x1 - dx, y1 - dy, x2 + dx, y2 + dy))

    # ----------------------------------------------------------------------
    def handleKey(self, event):
        if event.char == "a":
            self.event_generate("<<SelectAll>>")
        elif event.char == "A":
            self.event_generate("<<SelectNone>>")
        elif event.char == "e":
            self.event_generate("<<Expand>>")
        elif event.char == "f":
            self.fit2Screen()
        elif event.char == "g":
            self.app.workflow.open_diagnostics()
        elif event.char == "l":
            self.event_generate("<<EnableToggle>>")
        elif event.char == "m":
            self.setActionMove()
        elif event.char == "n":
            self.event_generate("<<ShowInfo>>")
        elif event.char == "o":
            self.setActionOrigin()
        elif event.char == "r":
            self.setActionRuler()
        elif event.char == "s":
            self.setActionSelect()
        elif event.char == "x":
            self.setActionPan()
        elif event.char == "z":
            self.menuZoomIn()
        elif event.char == "Z":
            self.menuZoomOut()

    # ----------------------------------------------------------------------
    def setAction(self, action):
        self.action = action
        self.actionVar.set(action)
        self._mouseAction = None
        self.config(cursor=mouseCursor(self.action), background="White")

    # ----------------------------------------------------------------------
    def actionCancel(self, event=None):
        if self.action != ACTION_SELECT or (
            self._mouseAction != ACTION_SELECT and self._mouseAction is not None
        ):
            self.setAction(ACTION_SELECT)
            return "break"

    # ----------------------------------------------------------------------
    def setActionSelect(self, event=None):
        self.setAction(ACTION_SELECT)
        self.status(_("Select objects with mouse"))

    # ----------------------------------------------------------------------
    def setActionPan(self, event=None):
        self.setAction(ACTION_PAN)
        self.status(_("Pan viewport"))

    # ----------------------------------------------------------------------
    def setActionOrigin(self, event=None):
        self.setAction(ACTION_ORIGIN)
        self.status(_("Click to set the origin (zero)"))

    # ----------------------------------------------------------------------
    def setActionMove(self, event=None):
        self.setAction(ACTION_MOVE)
        self.status(_("Move graphically objects"))

    # ----------------------------------------------------------------------
    def setActionRuler(self, event=None):
        self.setAction(ACTION_RULER)
        self.status(_("Drag a ruler to measure distances"))

    # ----------------------------------------------------------------------
    # Find item selected
    # ----------------------------------------------------------------------
    def click(self, event):
        self.focus_set()
        self._x = self._xp = event.x
        self._y = self._yp = event.y

        if event.state & CONTROLSHIFT_MASK == CONTROLSHIFT_MASK:
            self.app.workflow.open_diagnostics()
            return

        elif self.action == ACTION_SELECT:
            self._mouseAction = ACTION_SELECT_SINGLE

        elif self.action in (ACTION_MOVE, ACTION_RULER):
            i = self.canvasx(event.x)
            j = self.canvasy(event.y)
            if self.action == ACTION_RULER and self._vector is not None:
                # Check if we hit the existing ruler
                coords = self.coords(self._vector)
                if abs(coords[0] - i) <= CLOSE_DISTANCE and abs(
                    coords[1] - j <= CLOSE_DISTANCE
                ):
                    # swap coordinates
                    coords[0], coords[2] = coords[2], coords[0]
                    coords[1], coords[3] = coords[3], coords[1]
                    self.coords(self._vector, *coords)
                    self._vx0, self._vy0, self._vz0 = self.canvas2xyz(
                        coords[0], coords[1]
                    )
                    self._mouseAction = self.action
                    return
                elif abs(coords[2] - i) <= CLOSE_DISTANCE and abs(
                    coords[3] - j <= CLOSE_DISTANCE
                ):
                    self._mouseAction = self.action
                    return

            if self._vector:
                self.delete(self._vector)
            if self.action == ACTION_MOVE:
                # Check if we clicked on a selected item
                try:
                    for item in self.find_overlapping(
                        i - CLOSE_DISTANCE,
                        j - CLOSE_DISTANCE,
                        i + CLOSE_DISTANCE,
                        j + CLOSE_DISTANCE,
                    ):
                        tags = self.gettags(item)
                        if (
                            "sel" in tags
                            or "sel2" in tags
                            or "sel3" in tags
                            or "sel4" in tags
                        ):
                            break
                    else:
                        self._mouseAction = ACTION_SELECT_SINGLE
                        return
                    fill = MOVE_COLOR
                    arrow = LAST
                except Exception:
                    self._mouseAction = ACTION_SELECT_SINGLE
                    return
            else:
                fill = RULER_COLOR
                arrow = BOTH
            self._vector = self.create_line(
                (i, j, i, j), fill=fill, arrow=arrow)
            self._vx0, self._vy0, self._vz0 = self.canvas2xyz(i, j)
            self._mouseAction = self.action

        # Req B – Mat drag-to-position mode
        elif self.action == ACTION_MAT_DRAG:
            # Auto-select all gcode blocks so they move together
            if not self.bbox("sel"):
                self.app.editor.selectAll()
                self.app.selectionChange()
            i = self.canvasx(event.x)
            j = self.canvasy(event.y)
            if self._vector:
                self.delete(self._vector)
            self._vector = self.create_line(
                (i, j, i, j), fill=MOVE_COLOR, arrow=LAST)
            self._vx0, self._vy0, self._vz0 = self.canvas2xyz(i, j)
            # Delegate to ACTION_MOVE so buttonMotion/release handle it
            self._mouseAction = ACTION_MOVE

        # Set coordinate origin
        elif self.action == ACTION_ORIGIN:
            i = self.canvasx(event.x)
            j = self.canvasy(event.y)
            x, y, z = self.canvas2xyz(i, j)
            self.app.editor.selectAll()
            self.app.workflow.transform("MOVE", -x, -y, -z)
            self.setActionSelect()

        elif self.action == ACTION_PAN:
            self.pan(event)

    # ----------------------------------------------------------------------
    # Canvas motion button 1
    # ----------------------------------------------------------------------
    def buttonMotion(self, event):
        if self._mouseAction == ACTION_SELECT_AREA:
            self.coords(
                self._select,
                self.canvasx(self._x),
                self.canvasy(self._y),
                self.canvasx(event.x),
                self.canvasy(event.y),
            )

        elif self._mouseAction in (ACTION_SELECT_SINGLE, ACTION_SELECT_DOUBLE):
            if abs(event.x - self._x) > 4 or abs(event.y - self._y) > 4:
                self._mouseAction = ACTION_SELECT_AREA
                self._select = self.create_rectangle(
                    self.canvasx(self._x),
                    self.canvasy(self._y),
                    self.canvasx(event.x),
                    self.canvasy(event.y),
                    outline=BOX_SELECT,
                )

        elif self._mouseAction in (ACTION_MOVE, ACTION_RULER):
            coords = self.coords(self._vector)
            i = self.canvasx(event.x)
            j = self.canvasy(event.y)
            coords[-2] = i
            coords[-1] = j
            self.coords(self._vector, *coords)
            if self._mouseAction == ACTION_MOVE:
                self.move("sel", event.x - self._xp, event.y - self._yp)
                self.move("sel2", event.x - self._xp, event.y - self._yp)
                self.move("sel3", event.x - self._xp, event.y - self._yp)
                self.move("sel4", event.x - self._xp, event.y - self._yp)
                self._xp = event.x
                self._yp = event.y

            self._vx1, self._vy1, self._vz1 = self.canvas2xyz(i, j)
            dx = self._vx1 - self._vx0
            dy = self._vy1 - self._vy0
            dz = self._vz1 - self._vz0
            self.status(
                _("dx={:g}  dy={:g}  dz={:g}  length={:g}  angle={:g}").format(
                    dx,
                    dy,
                    dz,
                    math.sqrt(dx**2 + dy**2 + dz**2),
                    math.degrees(math.atan2(dy, dx)),
                )
            )

        elif self._mouseAction == ACTION_PAN:
            self.pan(event)

        self.setMouseStatus(event)

    # ----------------------------------------------------------------------
    # Canvas release button1. Select area
    # ----------------------------------------------------------------------
    def release(self, event):
        if self._mouseAction in (
            ACTION_SELECT_SINGLE,
            ACTION_SELECT_DOUBLE,
            ACTION_SELECT_AREA,
        ):
            if self._mouseAction == ACTION_SELECT_AREA:
                if self._x < event.x:  # From left->right enclosed
                    closest = self.find_enclosed(
                        self.canvasx(self._x),
                        self.canvasy(self._y),
                        self.canvasx(event.x),
                        self.canvasy(event.y),
                    )
                else:  # From right->left overlapping
                    closest = self.find_overlapping(
                        self.canvasx(self._x),
                        self.canvasy(self._y),
                        self.canvasx(event.x),
                        self.canvasy(event.y),
                    )
                self.delete(self._select)
                self._select = None
                items = []
                for i in closest:
                    try:
                        items.append(self._items[i])
                    except Exception:
                        pass

            elif self._mouseAction in (ACTION_SELECT_SINGLE,
                                       ACTION_SELECT_DOUBLE):
                closest = self.find_closest(
                    self.canvasx(event.x),
                    self.canvasy(event.y),
                    CLOSE_DISTANCE
                )
                items = []
                for i in closest:
                    try:
                        items.append(self._items[i])
                    except KeyError:
                        tags = self.gettags(i)
                        pass
            if not items:
                return

            self.app.select(
                items,
                self._mouseAction == ACTION_SELECT_DOUBLE,
                event.state & CONTROL_MASK == 0,
            )
            self._mouseAction = None

        elif self._mouseAction == ACTION_MOVE:
            i = self.canvasx(event.x)
            j = self.canvasy(event.y)
            self._vx1, self._vy1, self._vz1 = self.canvas2xyz(i, j)
            dx = self._vx1 - self._vx0
            dy = self._vy1 - self._vy0
            dz = self._vz1 - self._vz0
            self.status(_("Move by {:g}, {:g}, {:g}").format(dx, dy, dz))
            self.app.workflow.transform("MOVE", dx, dy, dz)

        elif self._mouseAction == ACTION_PAN:
            self.panRelease(event)

    # ----------------------------------------------------------------------
    def double(self, event):
        self._mouseAction = ACTION_SELECT_DOUBLE

    # ----------------------------------------------------------------------
    def motion(self, event):
        self.setMouseStatus(event)

    # -----------------------------------------------------------------------
    # Testing routine
    # -----------------------------------------------------------------------
    def __test(self, event):
        i = self.canvasx(event.x)
        j = self.canvasy(event.y)
        x, y, z = self.canvas2xyz(i, j)

    # ----------------------------------------------------------------------
    # Get margins of selected items
    # ----------------------------------------------------------------------
    def getMargins(self):
        bbox = self.bbox("sel")
        if not bbox:
            return None
        x1, y1, x2, y2 = bbox
        dx = (x2 - x1 - 1) / self.zoom
        dy = (y2 - y1 - 1) / self.zoom
        return dx, dy

    # ----------------------------------------------------------------------
    def pan(self, event):
        if self._mouseAction == ACTION_PAN:
            self.scan_dragto(event.x, event.y, gain=1)

        else:
            self.config(cursor=mouseCursor(ACTION_PAN))
            self.scan_mark(event.x, event.y)
            self._mouseAction = ACTION_PAN

    # ----------------------------------------------------------------------
    def panRelease(self, event):
        self._mouseAction = None
        self.config(cursor=mouseCursor(self.action))

    # ----------------------------------------------------------------------
    def panLeft(self, event=None):
        self.xview(SCROLL, -1, UNITS)

    def panRight(self, event=None):
        self.xview(SCROLL, 1, UNITS)

    def panUp(self, event=None):
        self.yview(SCROLL, -1, UNITS)

    def panDown(self, event=None):
        self.yview(SCROLL, 1, UNITS)

    # ----------------------------------------------------------------------
    # Delay zooming to cascade multiple zoom actions
    # ----------------------------------------------------------------------
    def zoomCanvas(self, x, y, zoom):
        self._tx = x
        self._ty = y
        self.__tzoom *= zoom
        self.after_idle(self._zoomCanvas)

    # ----------------------------------------------------------------------
    # Zoom on screen position x,y by a factor zoom
    # ----------------------------------------------------------------------
    def _zoomCanvas(self, event=None):  # x, y, zoom):
        x = self._tx
        y = self._ty
        zoom = self.__tzoom

        self.__tzoom = 1.0

        self.zoom *= zoom

        x0 = self.canvasx(0)
        y0 = self.canvasy(0)

        for i in self.find_all():
            self.scale(i, 0, 0, zoom, zoom)

        # Update last insert
        if self._lastGantry:
            self._drawGantry(*self.plotCoords([self._lastGantry])[0])
        else:
            self._drawGantry(0, 0)

        self._updateScrollBars()
        x0 -= self.canvasx(0)
        y0 -= self.canvasy(0)

        # Perform pin zoom
        dx = self.canvasx(x) * (1.0 - zoom)
        dy = self.canvasy(y) * (1.0 - zoom)

        # Drag to new location to center viewport
        self.scan_mark(0, 0)
        self.scan_dragto(int(round(dx - x0)), int(round(dy - y0)), 1)


    # ----------------------------------------------------------------------
    # Return selected objects bounding box
    # ----------------------------------------------------------------------
    def selBbox(self):
        x1 = None
        for tag in ("sel", "sel2", "sel3", "sel4"):
            bb = self.bbox(tag)
            if bb is None:
                continue
            elif x1 is None:
                x1, y1, x2, y2 = bb
            else:
                x1 = min(x1, bb[0])
                y1 = min(y1, bb[1])
                x2 = max(x2, bb[2])
                y2 = max(y2, bb[3])

        if x1 is None:
            return self.bbox("all")
        return x1, y1, x2, y2

    # ----------------------------------------------------------------------
    # Zoom to Fit to Screen
    # ----------------------------------------------------------------------

    # New approach by onekk https://github.com/vlachoudis/bCNC/issues/1311
    def fit2Screen(self, event=None):
        """Zoom to Fit to Screen"""

        bb = self.selBbox()
        if bb is None:
            return

        x1, y1, x2, y2 = bb

        # add a factor to improve reability
        bbox_width = (x2 - x1) * 1.05
        bbox_height = (y2 - y1) * 1.05

        try:
            zx = round(float(self.winfo_width() / bbox_width), 2)
        except Exception:
            return

        try:
            zy = round(float(self.winfo_height() / bbox_height), 2)
        except Exception:
            return

        # Fit both dimensions when zooming out as well as when zooming in.
        # Using max while zooming out crops a tall mat on a wide viewport.
        self.__tzoom = min(zx, zy)
        if self.__tzoom <= 0:
            return

        self._tx = self._ty = 0
        self._zoomCanvas()

        # Find position of new selection
        x1, y1, x2, y2 = self.selBbox()
        xm = (x1 + x2) // 2
        ym = (y1 + y2) // 2
        sx1, sy1, sx2, sy2 = map(float, self.cget("scrollregion").split())
        midx = float(xm - sx1) / (sx2 - sx1)
        midy = float(ym - sy1) / (sy2 - sy1)

        a, b = self.xview()
        d = (b - a) / 2.0
        self.xview_moveto(midx - d)

        a, b = self.yview()
        d = (b - a) / 2.0
        self.yview_moveto(midy - d)


    # ----------------------------------------------------------------------
    def menuZoomIn(self, event=None):
        x = int(self.cget("width")) // 2
        y = int(self.cget("height")) // 2
        self.zoomCanvas(x, y, 2.0)

    # ----------------------------------------------------------------------
    def menuZoomOut(self, event=None):
        x = int(self.cget("width")) // 2
        y = int(self.cget("height")) // 2
        self.zoomCanvas(x, y, 0.5)

    # ----------------------------------------------------------------------
    def mouseZoomIn(self, event):
        self.zoomCanvas(event.x, event.y, ZOOM)

    # ----------------------------------------------------------------------
    def mouseZoomOut(self, event):
        self.zoomCanvas(event.x, event.y, 1.0 / ZOOM)

    # ----------------------------------------------------------------------
    def wheel(self, event):
        self.zoomCanvas(event.x, event.y, pow(ZOOM, (event.delta // 120)))

    # ----------------------------------------------------------------------
    # Change the insert marker location
    # ----------------------------------------------------------------------
    def activeMarker(self, item):
        if item is None:
            return
        b, i = item
        if i is None:
            return
        block = self.gcode[b]
        item = block.path(i)

        if item is not None and item != self._lastActive:
            if self._lastActive is not None:
                self.itemconfig(self._lastActive, arrow=NONE)
            self._lastActive = item
            self.itemconfig(self._lastActive, arrow=LAST)

    # ----------------------------------------------------------------------
    # Display gantry
    # ----------------------------------------------------------------------
    def gantry(self, wx, wy, wz, mx, my, mz):
        self._lastGantry = (wx, wy, wz)
        self._drawGantry(*self.plotCoords([(wx, wy, wz)])[0])

        dx = wx - mx
        dy = wy - my
        dz = wz - mz
        if (
            abs(dx - self._dx) > 0.0001
            or abs(dy - self._dy) > 0.0001
            or abs(dz - self._dz) > 0.0001
        ):
            self._dx = dx
            self._dy = dy
            self._dz = dz

            if not self.draw_workarea:
                return
            xmin = self._dx - CNC.travel_x
            ymin = self._dy - CNC.travel_y
            xmax = self._dx
            ymax = self._dy

            xyz = [
                (xmin, ymin, 0.0),
                (xmax, ymin, 0.0),
                (xmax, ymax, 0.0),
                (xmin, ymax, 0.0),
                (xmin, ymin, 0.0),
            ]

            coords = []
            for x, y in self.plotCoords(xyz):
                coords.append(x)
                coords.append(y)
            self.coords(self._workarea, *coords)

    # ----------------------------------------------------------------------
    # Clear highlight of selection
    # ----------------------------------------------------------------------
    def clearSelection(self):
        if self._lastActive is not None:
            self.itemconfig(self._lastActive, arrow=NONE)
            self._lastActive = None

        for i in self.find_withtag("sel"):
            bid, lid = self._items[i]
            if bid:
                try:
                    block = self.gcode[bid]
                    if block.color:
                        fill = block.color
                    else:
                        fill = ENABLE_COLOR
                except IndexError:
                    fill = ENABLE_COLOR
            else:
                fill = ENABLE_COLOR
            self.itemconfig(i, width=1, fill=fill)

        self.itemconfig("sel2", width=1, fill=DISABLE_COLOR)
        self.itemconfig("sel3", width=1, fill=TAB_COLOR)
        self.itemconfig("sel4", width=1, fill=DISABLE_COLOR)
        for i in SELECTION_TAGS:
            self.dtag(i)
        self.delete("info")

    # ----------------------------------------------------------------------
    # Highlight selected items
    # ----------------------------------------------------------------------
    def select(self, items):
        for b, i in items:
            block = self.gcode[b]
            if i is None:
                sel = block.enable and "sel" or "sel2"
                for path in block._path:
                    if path is not None:
                        self.addtag_withtag(sel, path)
                sel = block.enable and "sel3" or "sel4"

            elif isinstance(i, int):
                path = block.path(i)
                if path:
                    sel = block.enable and "sel" or "sel2"
                    self.addtag_withtag(sel, path)

        self.itemconfig("sel", width=2, fill=SELECT_COLOR)
        self.itemconfig("sel2", width=2, fill=SELECT2_COLOR)
        self.itemconfig("sel3", width=2, fill=TAB_COLOR)
        self.itemconfig("sel4", width=2, fill=TABS_COLOR)
        for i in SELECTION_TAGS:
            self.tag_raise(i)
        self.drawMargin()

    # ----------------------------------------------------------------------
    # Display graphical information on selected blocks
    # ----------------------------------------------------------------------
    def showInfo(self, blocks):
        self.delete("info")  # clear any previous information
        for bid in blocks:
            block = self.gcode.blocks[bid]
            xyz = [
                (block.xmin, block.ymin, 0.0),
                (block.xmax, block.ymin, 0.0),
                (block.xmax, block.ymax, 0.0),
                (block.xmin, block.ymax, 0.0),
                (block.xmin, block.ymin, 0.0),
            ]
            self.create_line(self.plotCoords(xyz), fill=INFO_COLOR, tag="info")
            xc = (block.xmin + block.xmax) / 2.0
            yc = (block.ymin + block.ymax) / 2.0
            r = min(block.xmax - xc, block.ymax - yc)
            closed, direction = self.gcode.info(bid)

            if closed == 0:  # open path
                if direction == 1:
                    sf = math.pi / 4.0
                    ef = 2.0 * math.pi - sf
                else:
                    ef = math.pi / 4.0
                    sf = 2.0 * math.pi - ef
            elif closed == 1:
                if direction == 1:
                    sf = 0.0
                    ef = 2.0 * math.pi
                else:
                    ef = 0.0
                    sf = 2.0 * math.pi

            elif closed is None:
                continue

            n = 64
            df = (ef - sf) / float(n)
            xyz = []
            f = sf
            for i in range(n + 1):
                xyz.append(
                    (xc + r * math.sin(f), yc + r * math.cos(f), 0.0)
                )  # towards up
                f += df
            self.create_line(
                self.plotCoords(xyz),
                fill=INFO_COLOR,
                width=5,
                arrow=LAST,
                arrowshape=(32, 40, 12),
                tag="info",
            )

    # ----------------------------------------------------------------------
    # Parse and draw the file from the editor to g-code commands
    # ----------------------------------------------------------------------
    def draw(self):
        if self._inDraw:
            return
        self._inDraw = True

        self.__tzoom = 1.0
        xyz = self.canvas2xyz(
            self.canvasx(self.winfo_width() / 2),
            self.canvasy(self.winfo_height() / 2)
        )


        self._last = (0.0, 0.0, 0.0)
        self.initPosition()

        self.drawCuttingMat()   # Req A – must be first (lowest layer)
        self.drawPaths()
        self.drawGrid()
        self.drawMargin()
        self.drawWorkarea()
        self.drawAxes()
        if self._gantry1:
            self.tag_raise(self._gantry1)
        if self._gantry2:
            self.tag_raise(self._gantry2)
        self._updateScrollBars()

        ij = self.plotCoords([xyz])[0]
        dx = int(round(self.canvasx(self.winfo_width() / 2) - ij[0]))
        dy = int(round(self.canvasy(self.winfo_height() / 2) - ij[1]))
        self.scan_mark(0, 0)
        self.scan_dragto(int(round(dx)), int(round(dy)), 1)

        self._inDraw = False

    # ----------------------------------------------------------------------
    # Initialize gantry position
    # ----------------------------------------------------------------------
    def initPosition(self):
        self.configure(background=CANVAS_COLOR)
        self.delete(ALL)
        gr = max(3, int(CNC.vars["diameter"] / 2.0 * self.zoom))
        self._gantry1 = self.create_oval(
            (-gr, -gr), (gr, gr), width=2, outline=GANTRY_COLOR
        )
        self._gantry2 = None

        self._lastInsert = None
        self._lastActive = None
        self._select = None
        self._vector = None
        self._items.clear()
        self.cnc.initPath()
        self.cnc.resetAllMargins()

    # ----------------------------------------------------------------------
    # Draw gantry location
    # ----------------------------------------------------------------------
    def _drawGantry(self, x, y):
        gr = max(3, int(CNC.vars["diameter"] / 2.0 * self.zoom))
        if self._gantry2 is None:
            self.coords(self._gantry1, (x - gr, y - gr, x + gr, y + gr))
        else:
            gx = gr
            gy = gr // 2
            gh = 3 * gr
            if self._gantry1 is None:
                self.coords(
                    self._gantry2,
                    (x - gx, y - gh, x, y, x + gx, y - gh, x - gx, y - gh),
                )
            else:
                self.coords(
                    self._gantry1, (x - gx, y - gh - gy, x + gx, y - gh + gy))
                self.coords(
                    self._gantry2, (x - gx, y - gh, x, y, x + gx, y - gh))

    # ----------------------------------------------------------------------
    # Draw system axes
    # ----------------------------------------------------------------------
    def drawAxes(self):
        self.delete("Axes")
        if not self.draw_axes:
            return

        dx = self.cnc.bounds["axmax"] - self.cnc.bounds["axmin"]
        dy = self.cnc.bounds["aymax"] - self.cnc.bounds["aymin"]
        d = min(dx, dy)
        try:
            s = math.pow(10.0, int(math.log10(d)))
        except Exception:
            if CNC.inch:
                s = 10.0
            else:
                s = 100.0
        xyz = [(0.0, 0.0, 0.0), (s, 0.0, 0.0)]
        self.create_line(
            self.plotCoords(xyz), tag="Axes", fill="Red",
            dash=(3, 1), arrow=LAST
        )

        xyz = [(0.0, 0.0, 0.0), (0.0, s, 0.0)]
        self.create_line(
            self.plotCoords(xyz), tag="Axes", fill="Green",
            dash=(3, 1), arrow=LAST
        )

        xyz = [(0.0, 0.0, 0.0), (0.0, 0.0, s)]
        self.create_line(
            self.plotCoords(xyz), tag="Axes", fill="Blue",
            dash=(3, 1), arrow=LAST
        )

    # ----------------------------------------------------------------------
    # Draw margins of selected blocks
    # ----------------------------------------------------------------------
    def drawMargin(self):
        if self._margin:
            self.delete(self._margin)
        if self._amargin:
            self.delete(self._amargin)
        self._margin = self._amargin = None
        if not self.draw_margin:
            return

        if self.cnc.isMarginValid():
            xyz = [
                (self.cnc.bounds["xmin"], self.cnc.bounds["ymin"], 0.0),
                (self.cnc.bounds["xmax"], self.cnc.bounds["ymin"], 0.0),
                (self.cnc.bounds["xmax"], self.cnc.bounds["ymax"], 0.0),
                (self.cnc.bounds["xmin"], self.cnc.bounds["ymax"], 0.0),
                (self.cnc.bounds["xmin"], self.cnc.bounds["ymin"], 0.0),
            ]
            self._margin = self.create_line(self.plotCoords(xyz),
                                            fill=MARGIN_COLOR)
            self.tag_lower(self._margin)

        if not self.cnc.isAllMarginValid():
            return
        xyz = [
            (self.cnc.bounds["axmin"], self.cnc.bounds["aymin"], 0.0),
            (self.cnc.bounds["axmax"], self.cnc.bounds["aymin"], 0.0),
            (self.cnc.bounds["axmax"], self.cnc.bounds["aymax"], 0.0),
            (self.cnc.bounds["axmin"], self.cnc.bounds["aymax"], 0.0),
            (self.cnc.bounds["axmin"], self.cnc.bounds["aymin"], 0.0),
        ]
        self._amargin = self.create_line(
            self.plotCoords(xyz), dash=(3, 2), fill=MARGIN_COLOR
        )
        self.tag_lower(self._amargin)

    # ----------------------------------------------------------------------
    # Draw a 3D rectangle
    # ----------------------------------------------------------------------
    def _drawRect(self, xmin, ymin, xmax, ymax, z=0.0, **kwargs):
        xyz = [
            (xmin, ymin, z),
            (xmax, ymin, z),
            (xmax, ymax, z),
            (xmin, ymax, z),
            (xmin, ymin, z),
        ]
        rect = (self.create_line(self.plotCoords(xyz), **kwargs),)
        return rect

    # ----------------------------------------------------------------------
    # Draw a workspace rectangle
    # ----------------------------------------------------------------------
    def drawWorkarea(self):
        if self._workarea:
            self.delete(self._workarea)
        if not self.draw_workarea:
            return

        xmin = self._dx - CNC.travel_x
        ymin = self._dy - CNC.travel_y
        xmax = self._dx
        ymax = self._dy

        self._workarea = self._drawRect(
            xmin, ymin, xmax, ymax, 0.0, fill=WORK_COLOR, dash=(3, 2)
        )
        self.tag_lower(self._workarea)

    # ----------------------------------------------------------------------
    # Req A – Draw the physical cutting mat background with 10 mm grid
    # ----------------------------------------------------------------------
    def drawCuttingMat(self):
        """
        Renders a filled rectangle representing the physical cutting mat,
        bounded by MAT_BORDER_COLOR and filled MAT_COLOR, with a 10 mm
        internal grid (MAT_GRID_COLOR).  The mat occupies machine coordinates
        [0, mat_width] × [0, mat_height].

        Also raises a red boundary-warning outline (Req D) when loaded
        G-code paths extend outside the mat perimeter.
        """
        self.delete("CuttingMat")
        self._cuttingMat = None
        self._matWarning = None

        if not self.draw_cutting_mat:
            return

        mat_w = CNC.vars.get("mat_width",  300.0)
        mat_h = CNC.vars.get("mat_height", 300.0)
        if mat_w <= 0 or mat_h <= 0:
            return

        # ── filled background polygon ────────────────────────────────────
        corners = self.plotCoords([
            (0.0,   0.0,   0.0),
            (mat_w, 0.0,   0.0),
            (mat_w, mat_h, 0.0),
            (0.0,   mat_h, 0.0),
        ])
        flat = [c for xy in corners for c in xy]

        mat_item = self.create_polygon(
            flat,
            fill=MAT_COLOR,
            outline=MAT_BORDER_COLOR,
            width=2,
            tag="CuttingMat",
        )
        self._cuttingMat = mat_item

        # ── 10 mm internal grid ──────────────────────────────────────────
        spacing = 10 if self.zoom >= 2 else 25 if self.zoom >= 1 else 50
        x_steps = int(mat_w) // spacing if self.draw_grid else 0
        y_steps = int(mat_h) // spacing if self.draw_grid else 0

        for yi in range(1, y_steps + 1):
            y = yi * spacing
            if y >= mat_h:
                break
            xyz = [(0.0, y, 0.0), (mat_w, y, 0.0)]
            self.create_line(
                self.plotCoords(xyz),
                fill=MAT_GRID_COLOR,
                tag="CuttingMat",
            )

        for xi in range(1, x_steps + 1):
            x = xi * spacing
            if x >= mat_w:
                break
            xyz = [(x, 0.0, 0.0), (x, mat_h, 0.0)]
            self.create_line(
                self.plotCoords(xyz),
                fill=MAT_GRID_COLOR,
                tag="CuttingMat",
            )
        # Lower all mat items with one Tcl call (O(1) vs O(n))
        self.tag_lower("CuttingMat")

        # ── Req D boundary-overflow warning ─────────────────────────────
        if self.cnc.isMarginValid():
            out = (
                self.cnc.bounds["xmin"] < -0.01
                or self.cnc.bounds["xmax"] > mat_w + 0.01
                or self.cnc.bounds["ymin"] < -0.01
                or self.cnc.bounds["ymax"] > mat_h + 0.01
            )
            if out:
                warn_item = self.create_polygon(
                    flat,
                    fill="",
                    outline=MAT_WARN_COLOR,
                    width=4,
                    tag="CuttingMat",
                )
                self.tag_raise(warn_item)
                self._matWarning = warn_item
                self.status(
                    _("WARNING: G-code paths extend outside the cutting mat!")
                )

    # ----------------------------------------------------------------------
    # Req B – Action mode: drag-to-position layout on the mat
    # ----------------------------------------------------------------------
    def setActionMatDrag(self, event=None):
        """
        Switch to mat-drag mode.  Clicking on any gcode item (or anywhere
        on the canvas) auto-selects all blocks and starts a MOVE operation.
        """
        self.setAction(ACTION_MAT_DRAG)
        self.config(background="#f0fff0")
        self.status(
            _("Click and drag to reposition g-code on the cutting mat")
        )

    # ----------------------------------------------------------------------
    # Draw coordinates grid
    # ----------------------------------------------------------------------
    def drawGrid(self):
        self.delete("Grid")
        if not self.draw_grid:
            return
        xmin = (self.cnc.bounds["axmin"] // 10) * 10
        xmax = (self.cnc.bounds["axmax"] // 10 + 1) * 10
        ymin = (self.cnc.bounds["aymin"] // 10) * 10
        ymax = (self.cnc.bounds["aymax"] // 10 + 1) * 10
        for i in range(
            int(self.cnc.bounds["aymin"] // 10), int(self.cnc.bounds["aymax"] // 10) + 2
        ):
            y = i * 10.0
            xyz = [(xmin, y, 0), (xmax, y, 0)]
            self.create_line(
                self.plotCoords(xyz), tag="Grid",
                fill=GRID_COLOR, dash=(1, 3)
            )

        for i in range(
            int(self.cnc.bounds["axmin"] // 10), int(self.cnc.bounds["axmax"] // 10) + 2
        ):
            x = i * 10.0
            xyz = [(x, ymin, 0), (x, ymax, 0)]
            self.create_line(
                self.plotCoords(xyz), fill=GRID_COLOR, tag="Grid", dash=(1, 3)
            )
        # Lower all grid items with one Tcl call (O(1) vs O(n))
        self.tag_lower("Grid")

    # ----------------------------------------------------------------------
    # Draw the paths for the whole gcode file
    # ----------------------------------------------------------------------
    def drawPaths(self):
        if not self.draw_paths:
            for block in self.gcode.blocks:
                block.resetPath()
            return

        try:
            n = 1
            startTime = before = time.time()
            self.cnc.resetAllMargins()
            drawG = self.draw_rapid or self.draw_paths or self.draw_margin
            curVersion = self.gcode._drawVersion
            for i, block in enumerate(self.gcode.blocks):
                start = True  # start location found
                block.resetPath()

                # Re-use pre-computed xyz geometry when the G-code hasn't
                # changed (e.g. view/zoom-triggered redraws).  Skips the
                # expensive evaluate → compileLine → motionPath pipeline.
                useCache = (
                    block._xyzVersion == curVersion
                    and len(block._xyzPaths) == len(block)
                )
                if not useCache:
                    block._xyzPaths = [None] * len(block)

                # Consecutive G1 segments are merged into one polyline
                # canvas item, cutting Tkinter create_line calls from O(N)
                # to O(runs).  Only applied on the fast cached path where we
                # know the gcode_code up-front without re-parsing.
                _g1_pts = []    # flat screen coords [x1,y1, x2,y2, ...]
                _g1_fill = None
                _g1_j0 = None   # first j of the current G1 run

                # Draw block
                for j, line in enumerate(block):
                    n -= 1
                    if n == 0:
                        if time.time() - startTime > DRAW_TIME:
                            raise AlarmException()
                        # Only pump the event loop on the slow (parsing) path;
                        # cached draws complete quickly enough to skip it.
                        if not useCache and time.time() - before > 1.0:
                            self.update()
                            before = time.time()
                        n = 1000

                    if useCache:
                        cached = block._xyzPaths[j]
                        if cached is None or not drawG:
                            # Flush any pending G1 polyline at a gap
                            if _g1_pts:
                                poly = self.create_line(
                                    _g1_pts, fill=_g1_fill,
                                    width=0, cap="projecting")
                                self._items[poly] = i, _g1_j0
                                block._path[_g1_j0] = poly
                                _g1_pts = []; _g1_fill = None; _g1_j0 = None
                            block.addPath(None)
                            continue
                        xyz_orig, gcode_code = cached
                        # A no-motion command (G21, G90, dwell, spindle, …)
                        # stores (None, gcode_code) in the cache.  Skip it
                        # without flushing the G1 polyline buffer so that
                        # the polyline remains continuous across modal lines.
                        if xyz_orig is None:
                            block.addPath(None)
                            continue
                        # Restore the cnc cursor so that subsequent
                        # relative-coordinate lines compute correctly.
                        self.cnc.gcode = gcode_code
                        end = xyz_orig[-1]
                        self.cnc.x = end[0]
                        self.cnc.y = end[1]
                        self.cnc.z = end[2]
                        # Update path statistics (fast – no parsing)
                        self.cnc.pathLength(block, xyz_orig)
                        if gcode_code in (1, 2, 3):
                            block.pathMargins(xyz_orig)
                            self.cnc.pathMargins(block)
                        # G1 cutting moves: accumulate into polyline buffer
                        if gcode_code == 1 and block.enable and self.draw_paths:
                            coords = self.plotCoords(xyz_orig)
                            if coords:
                                if _g1_j0 is None:
                                    _g1_j0 = j
                                    _g1_fill = block.color or ENABLE_COLOR
                                    for pt in coords:
                                        _g1_pts += [pt[0], pt[1]]
                                else:
                                    # Only add the endpoint; start deduplicates
                                    # with the previous segment's endpoint.
                                    pt = coords[-1]
                                    _g1_pts += [pt[0], pt[1]]
                            self._last = end
                            block.addPath(None)   # placeholder; j0 patched on flush
                            if start:
                                block.startPath(end[0], end[1], end[2])
                                start = False
                        else:
                            # Non-G1 item: flush any pending polyline first
                            if _g1_pts:
                                poly = self.create_line(
                                    _g1_pts, fill=_g1_fill,
                                    width=0, cap="projecting")
                                self._items[poly] = i, _g1_j0
                                block._path[_g1_j0] = poly
                                _g1_pts = []; _g1_fill = None; _g1_j0 = None
                            path = self._drawPathCached(
                                block, xyz_orig, gcode_code)
                            self._items[path] = i, j
                            block.addPath(path)
                            if start and gcode_code in (1, 2, 3):
                                block.startPath(end[0], end[1], end[2])
                                start = False
                    else:
                        try:
                            cmd = self.gcode.evaluate(
                                CNC.compileLine(line), self.app)
                            if isinstance(cmd, tuple):
                                cmd = None
                            else:
                                cmd = CNC.breakLine(cmd)
                        except AlarmException:
                            raise
                        except Exception:
                            sys.stderr.write(
                                _(">>> ERROR: {}\n").format(
                                    str(sys.exc_info()[1]))
                            )
                            sys.stderr.write(
                                _("     line: {}\n").format(line))
                            cmd = None
                        if cmd is None or not drawG:
                            block._xyzPaths[j] = None
                            block.addPath(None)
                        else:
                            _entry = []
                            path = self.drawPath(block, cmd, _entry)
                            block._xyzPaths[j] = _entry[0] if _entry else None
                            self._items[path] = i, j
                            block.addPath(path)
                            if start and self.cnc.gcode in (1, 2, 3):
                                # Mark as start the first non-rapid motion
                                block.startPath(
                                    self.cnc.x, self.cnc.y, self.cnc.z)
                                start = False

                # Flush any G1 polyline remaining at end of block
                if _g1_pts:
                    poly = self.create_line(
                        _g1_pts, fill=_g1_fill, width=0, cap="projecting")
                    self._items[poly] = i, _g1_j0
                    block._path[_g1_j0] = poly

                if not useCache:
                    block._xyzVersion = curVersion
                block.endPath(self.cnc.x, self.cnc.y, self.cnc.z)
        except AlarmException:
            self.status("Rendering takes TOO Long. Interrupted...")

    # ----------------------------------------------------------------------
    # Create path for one g command
    # ----------------------------------------------------------------------
    def drawPath(self, block, cmds, _cache=None):
        self.cnc.motionStart(cmds)
        xyz = self.cnc.motionPath()
        self.cnc.motionEnd()
        if _cache is not None:
            # Snapshot geometry before the draw_rapid xyz[0] correction below;
            # used to populate the per-block xyz cache in drawPaths.
            _cache.append((list(xyz) if xyz else None, self.cnc.gcode))
        if xyz:
            self.cnc.pathLength(block, xyz)
            if self.cnc.gcode in (1, 2, 3):
                block.pathMargins(xyz)
                self.cnc.pathMargins(block)
            if block.enable:
                if self.cnc.gcode == 0 and self.draw_rapid:
                    xyz[0] = self._last
                self._last = xyz[-1]
            else:
                if self.cnc.gcode == 0:
                    return None
            coords = self.plotCoords(xyz)
            if coords:
                if block.enable:
                    if block.color:
                        fill = block.color
                    else:
                        fill = ENABLE_COLOR
                else:
                    fill = DISABLE_COLOR
                if self.cnc.gcode == 0:
                    if self.draw_rapid:
                        return self.create_line(coords, fill=fill,
                                                width=0, dash=(4, 3))
                elif self.draw_paths:
                    return self.create_line(
                        coords, fill=fill, width=0, cap="projecting"
                    )
        return None

    # ----------------------------------------------------------------------
    # Draw a path from pre-computed xyz geometry (no G-code interpretation).
    # Called by drawPaths when the per-block xyz cache is valid.
    # ----------------------------------------------------------------------
    def _drawPathCached(self, block, xyz_orig, gcode_code):
        if xyz_orig is None:
            return None
        if block.enable:
            if gcode_code == 0 and self.draw_rapid:
                xyz = list(xyz_orig)
                xyz[0] = self._last
            else:
                xyz = xyz_orig
            self._last = xyz_orig[-1]
        else:
            if gcode_code == 0:
                return None
            xyz = xyz_orig
        coords = self.plotCoords(xyz)
        if coords:
            fill = (block.color or ENABLE_COLOR) if block.enable else DISABLE_COLOR
            if gcode_code == 0:
                if self.draw_rapid:
                    return self.create_line(coords, fill=fill,
                                            width=0, dash=(4, 3))
            elif self.draw_paths:
                return self.create_line(
                    coords, fill=fill, width=0, cap="projecting"
                )
        return None

    # ----------------------------------------------------------------------
    # Return plotting coordinates for a 3d xyz path
    #
    # NOTE: Use the tkinter._flatten() to pass to self.coords() function
    # ----------------------------------------------------------------------
    def plotCoords(self, xyz):
        coords = None
        coords = [(p[0] * self.zoom, -p[1] * self.zoom) for p in xyz]
        # Check limits
        for i, (x, y) in enumerate(coords):
            if abs(x) > MAXDIST or abs(y) > MAXDIST:
                if x < -MAXDIST:
                    x = -MAXDIST
                elif x > MAXDIST:
                    x = MAXDIST
                if y < -MAXDIST:
                    y = -MAXDIST
                elif y > MAXDIST:
                    y = MAXDIST
                coords[i] = (x, y)
        return coords

    # ----------------------------------------------------------------------
    # Canvas to real coordinates
    # ----------------------------------------------------------------------
    def canvas2xyz(self, i, j):
        x = i / self.zoom
        y = -j / self.zoom
        z = 0

        return x, y, z


# =============================================================================
# Canvas frame and view state
# =============================================================================
class CanvasFrame(Frame):
    def __init__(self, master, app, *kw, **kwargs):
        Frame.__init__(self, master, *kw, **kwargs)
        self.app = app

        self.draw_axes = BooleanVar()
        self.draw_grid = BooleanVar()
        self.draw_margin = BooleanVar()
        self.draw_paths = BooleanVar()
        self.draw_rapid = BooleanVar()
        self.draw_workarea = BooleanVar()

        self.loadConfig()


        self.canvas = CNCCanvas(self, app, takefocus=True, background="White")
        # OpenGL context
        print(f"self.canvas.winfo_id(): {self.canvas.winfo_id()}")
        self.canvas.grid(row=1, column=0, sticky=NSEW)
        sb = Scrollbar(self, orient=VERTICAL, command=self.canvas.yview)
        sb.grid(row=1, column=1, sticky=NS)
        self.canvas.config(yscrollcommand=sb.set)
        sb = Scrollbar(self, orient=HORIZONTAL, command=self.canvas.xview)
        sb.grid(row=2, column=0, sticky=EW)
        self.canvas.config(xscrollcommand=sb.set)


        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

    # ----------------------------------------------------------------------
    def loadConfig(self):
        global CANVAS_COLOR
        global INSERT_COLOR, GANTRY_COLOR, MARGIN_COLOR, GRID_COLOR
        global BOX_SELECT, ENABLE_COLOR, DISABLE_COLOR, SELECT_COLOR
        global SELECT2_COLOR, PROCESS_COLOR, MOVE_COLOR, RULER_COLOR
        global DRAW_TIME

        self.draw_axes.set(bool(int(Utils.getBool("Canvas", "axes", True))))
        self.draw_grid.set(bool(int(Utils.getBool("Canvas", "grid", True))))
        self.draw_margin.set(bool(int(Utils.getBool("Canvas", "margin", True))))
        self.draw_paths.set(bool(int(Utils.getBool("Canvas", "paths", True))))
        self.draw_rapid.set(bool(int(Utils.getBool("Canvas", "rapid", True))))
        self.draw_workarea.set(
            bool(int(Utils.getBool("Canvas", "workarea", True))))


        DRAW_TIME = Utils.getInt("Canvas", "drawtime", DRAW_TIME)

        INSERT_COLOR = Utils.getStr("Color", "canvas.insert", INSERT_COLOR)
        GANTRY_COLOR = Utils.getStr("Color", "canvas.gantry", GANTRY_COLOR)
        MARGIN_COLOR = Utils.getStr("Color", "canvas.margin", MARGIN_COLOR)
        GRID_COLOR = Utils.getStr("Color", "canvas.grid", GRID_COLOR)
        BOX_SELECT = Utils.getStr("Color", "canvas.selectbox", BOX_SELECT)
        ENABLE_COLOR = Utils.getStr("Color", "canvas.enable", ENABLE_COLOR)
        DISABLE_COLOR = Utils.getStr("Color", "canvas.disable", DISABLE_COLOR)
        SELECT_COLOR = Utils.getStr("Color", "canvas.select", SELECT_COLOR)
        SELECT2_COLOR = Utils.getStr("Color", "canvas.select2", SELECT2_COLOR)
        PROCESS_COLOR = Utils.getStr("Color", "canvas.process", PROCESS_COLOR)
        MOVE_COLOR = Utils.getStr("Color", "canvas.move", MOVE_COLOR)
        RULER_COLOR = Utils.getStr("Color", "canvas.ruler", RULER_COLOR)
        CANVAS_COLOR = Utils.getStr("Color", "canvas.background", CANVAS_COLOR)

    # ----------------------------------------------------------------------
    def saveConfig(self):
        Utils.setInt("Canvas", "drawtime", DRAW_TIME)
        Utils.setBool("Canvas", "axes", self.draw_axes.get())
        Utils.setBool("Canvas", "grid", self.draw_grid.get())
        Utils.setBool("Canvas", "margin", self.draw_margin.get())
        Utils.setBool("Canvas", "paths", self.draw_paths.get())
        Utils.setBool("Canvas", "rapid", self.draw_rapid.get())
        Utils.setBool("Canvas", "workarea", self.draw_workarea.get())

    # ----------------------------------------------------------------------
    def toggleDrawFlag(self):
        self.canvas.draw_axes = self.draw_axes.get()
        self.canvas.draw_grid = self.draw_grid.get()
        self.canvas.draw_margin = self.draw_margin.get()
        self.canvas.draw_paths = self.draw_paths.get()
        self.canvas.draw_rapid = self.draw_rapid.get()
        self.canvas.draw_workarea = self.draw_workarea.get()
        self.event_generate("<<ViewChange>>")

    # ----------------------------------------------------------------------
    def drawAxes(self, value=None):
        if value is not None:
            self.draw_axes.set(value)
        self.canvas.draw_axes = self.draw_axes.get()
        self.canvas.drawAxes()

    # ----------------------------------------------------------------------
    def drawGrid(self, value=None):
        if value is not None:
            self.draw_grid.set(value)
        self.canvas.draw_grid = self.draw_grid.get()
        self.canvas.drawGrid()

    # ----------------------------------------------------------------------
    def drawMargin(self, value=None):
        if value is not None:
            self.draw_margin.set(value)
        self.canvas.draw_margin = self.draw_margin.get()
        self.canvas.drawMargin()

    # ----------------------------------------------------------------------
    def drawWorkarea(self, value=None):
        if value is not None:
            self.draw_workarea.set(value)
        self.canvas.draw_workarea = self.draw_workarea.get()
        self.canvas.drawWorkarea()

    # ----------------------------------------------------------------------
