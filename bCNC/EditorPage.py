# $Id$
#
# Author: vvlachoudis@gmail.com
# Date: 18-Jun-2015

import math

from tkinter import (
    FALSE,
    TRUE,
    W,
    E,
    X,
    NSEW,
    Y,
    BOTH,
    LEFT,
    TOP,
    RIGHT,
    VERTICAL,
    EXTENDED,
    Menu,
    Scrollbar,
    Toplevel,
    Frame,
    Label,
    Entry,
    Button,
    StringVar,
)
from tkinter.simpledialog import askstring

import CNCList
import CNCRibbon
import Ribbon
import tkExtra
import Utils
from CNCCanvas import ACTION_MOVE, ACTION_ORIGIN
from CNC import CNC
from MatManager import apply_dragknife_auto  # kept for manual Execute button

from Helpers import N_

__author__ = "Vasilis Vlachoudis"
__email__ = "vvlachoudis@gmail.com"


# =============================================================================
# Clipboard Group
# =============================================================================
class ClipboardGroup(CNCRibbon.ButtonGroup):
    def __init__(self, master, app):
        CNCRibbon.ButtonGroup.__init__(self, master, N_("Clipboard"), app)
        self.grid2rows()

        # ---
        b = Ribbon.LabelButton(
            self.frame,
            self,
            "<<Cut>>",
            image=Utils.icons["cut"],
            text=_("Cut"),
            compound=LEFT,
            anchor=W,
            takefocus=FALSE,
            background=Ribbon._BACKGROUND,
        )
        tkExtra.Balloon.set(b, _("Cut [Ctrl-X]"))
        b.grid(row=0, column=1, padx=0, pady=1, sticky=NSEW)
        self.addWidget(b)

        # ---
        b = Ribbon.LabelButton(
            self.frame,
            self,
            "<<Copy>>",
            image=Utils.icons["copy"],
            text=_("Copy"),
            compound=LEFT,
            anchor=W,
            takefocus=FALSE,
            background=Ribbon._BACKGROUND,
        )
        tkExtra.Balloon.set(b, _("Copy [Ctrl-C]"))
        b.grid(row=1, column=1, padx=0, pady=1, sticky=NSEW)
        self.addWidget(b)


# =============================================================================
# Select Group
# =============================================================================
class SelectGroup(CNCRibbon.ButtonGroup):
    def __init__(self, master, app):
        CNCRibbon.ButtonGroup.__init__(self, master, N_("Select"), app)
        self.grid3rows()

        # ---
        col, row = 0, 0
        b = Ribbon.LabelButton(
            self.frame,
            app,
            "<<SelectAll>>",
            image=Utils.icons["select_all"],
            text=_("All"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Select all blocks [Ctrl-A]"))
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            app,
            "<<SelectNone>>",
            image=Utils.icons["select_none"],
            text=_("None"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Unselect all blocks [Ctrl-Shift-A]"))
        self.addWidget(b)

        # ---
        col, row = 0, 1
        b = Ribbon.LabelButton(
            self.frame,
            app,
            "<<SelectInvert>>",
            image=Utils.icons["select_invert"],
            text=_("Invert"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Invert selection [Ctrl-I]"))
        self.addWidget(b)

        # ---
        col += 1
        b = Ribbon.LabelButton(
            self.frame,
            app,
            "<<SelectLayer>>",
            image=Utils.icons["select_layer"],
            text=_("Layer"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Select all blocks from current layer"))
        self.addWidget(b)

        # ---
        col, row = 0, 2
        self.filterString = tkExtra.LabelEntry(
            self.frame,
            _("Filter"),
            "DarkGray",
            background=tkExtra.GLOBAL_CONTROL_BACKGROUND,
            width=16,
        )
        self.filterString.grid(
            row=row, column=col, columnspan=2, padx=0, pady=0, sticky=NSEW
        )
        tkExtra.Balloon.set(self.filterString, _("Filter blocks"))
        self.addWidget(self.filterString)
        self.filterString.bind("<Return>", self.filter)
        self.filterString.bind("<KP_Enter>", self.filter)

    # -----------------------------------------------------------------------
    def filter(self, event=None):
        txt = self.filterString.get()
        self.app.insertCommand(f"FILTER {txt}", True)


# =============================================================================
# Edit Group
# =============================================================================
class EditGroup(CNCRibbon.ButtonMenuGroup):
    def __init__(self, master, app):
        CNCRibbon.ButtonMenuGroup.__init__(
            self,
            master,
            N_("Edit"),
            app,
            [
                (
                    _("Autolevel"),
                    "level",
                    lambda a=app: a.insertCommand("AUTOLEVEL", True),
                ),
                (
                    _("Color"),
                    "color",
                    lambda a=app: a.event_generate("<<ChangeColor>>"),
                ),
                (_("Import"), "load", lambda a=app: a.insertCommand("IMPORT", True)),
                (
                    _("LibreCAD drawing"),
                    "pencil",
                    lambda a=app: a.event_generate("<<LibreCAD>>"),
                ),
                (
                    _("Inkscape drawing"),
                    "inkscape",
                    lambda a=app: a.event_generate("<<Inkscape>>"),
                ),
                (
                    _("Trace bitmap"),
                    "heightmap",
                    lambda a=app: a.event_generate("<<ImageTrace>>"),
                ),
                (
                    _("Postprocess Inkscape g-code"),
                    "inkscape",
                    lambda a=app: a.insertCommand("INKSCAPE all", True),
                ),
                (_("Round"), "digits", lambda s=app: s.insertCommand("ROUND", True)),
            ],
        )
        self.grid3rows()

        add_menu = [
            (
                _("Line"),
                "add",
                lambda a=self.app: a.event_generate("<<AddLine>>")
            ),
            (
                _("Block"),
                "add",
                lambda a=self.app: a.event_generate("<<AddBlock>>")
            ),
        ]
        b = Ribbon.MenuButton(
            self.frame,
            add_menu,
            text=_("Add"),
            image=Utils.icons["add"],
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=0, column=0, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Insert a new block or line of code [Ins or Ctrl-Enter]")
        )

        b = Ribbon.LabelButton(
            self.frame,
            app,
            "<<Clone>>",
            image=Utils.icons["clone"],
            text=_("Clone"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=1, column=0, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Clone selected lines or blocks [Ctrl-D]"))
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            app,
            "<<Delete>>",
            image=Utils.icons["x"],
            text=_("Delete"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=2, column=0, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Delete selected lines or blocks [Del]"))
        self.addWidget(b)

        active_menu = [
            (
                _("Enable"),
                "enable",
                lambda a=self.app: a.event_generate("<<Enable>>")
            ),
            (
                _("Disable"),
                "disable",
                lambda a=self.app: a.event_generate("<<Disable>>"),
            ),
        ]
        b = Ribbon.MenuButton(
            self.frame,
            active_menu,
            text=_("Active"),
            image=Utils.icons["toggle"],
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=0, column=1, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Enable or disable blocks of gcode"))

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<Expand>>",
            image=Utils.icons["expand"],
            text=_("Expand"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=1, column=1, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b,
            _("Toggle expand/collapse blocks of gcode [Ctrl-E]")
        )
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<Comment>>",
            image=Utils.icons["comment"],
            text=_("Comment"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=2, column=1, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("(Un)Comment selected lines"))
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<Join>>",
            image=Utils.icons["union"],
            text=_("Join"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=0, column=2, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Join selected blocks"))
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<Split>>",
            image=Utils.icons["cut"],
            text=_("Split"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=1, column=2, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Split selected blocks"))
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<InsertText>>",
            image=Utils.icons["text"],
            text=_("Text"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=2, column=2, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Insert welded vector text from a TTF or OTF font")
        )
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<LibreCAD>>",
            image=Utils.icons["pencil"],
            text=_("LibreCAD"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=0, column=3, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Create a DXF drawing in LibreCAD and import it when closed")
        )
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<Inkscape>>",
            image=Utils.icons["inkscape"],
            text=_("Inkscape"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=1, column=3, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Create an SVG drawing in Inkscape and import it when closed")
        )
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["color"],
            text=_("Color"),
            compound=LEFT,
            anchor=W,
            command=lambda a=self.app: a.event_generate("<<ChangeColor>>"),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=0, column=4, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Change the drawing color"))
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["load"],
            text=_("Import"),
            compound=LEFT,
            anchor=W,
            command=lambda a=self.app: a.insertCommand("IMPORT", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=1, column=4, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Import g-code"))
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<ImageTrace>>",
            image=Utils.icons["heightmap"],
            text=_("Bitmap"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=2, column=4, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Load a bitmap and trace contours, centerlines, or a cut outline")
        )
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<Intersection>>",
            image=Utils.icons["intersection"],
            text=_("Intersection"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=0, column=5, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Keep graphics present in both selections"))
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<Union>>",
            image=Utils.icons["union"],
            text=_("Union"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=1, column=5, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Combine both selected graphics"))
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<Difference>>",
            image=Utils.icons["diff"],
            text=_("Difference"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=0, column=6, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Subtract the second selection from the first"))
        self.addWidget(b)

        b = Ribbon.LabelButton(
            self.frame,
            self.app,
            "<<SymmetricDifference>>",
            image=Utils.icons["xor"],
            text=_("Sym. Difference"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=1, column=6, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Keep graphics present in either selection, but not both")
        )
        self.addWidget(b)

# =============================================================================
# Move Group
# =============================================================================
class MoveGroup(CNCRibbon.ButtonMenuGroup):
    def __init__(self, master, app):
        CNCRibbon.ButtonMenuGroup.__init__(self, master, N_("Move"), app)
        self.grid3rows()

        # ===
        col, row = 0, 0
        b = Ribbon.LabelRadiobutton(
            self.frame,
            image=Utils.icons["move32"],
            text=_("Move"),
            compound=TOP,
            anchor=W,
            variable=app.canvas.actionVar,
            value=ACTION_MOVE,
            command=app.canvas.setActionMove,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, rowspan=3, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Move objects [M]"))
        self.addWidget(b)

        # ---
        col += 1
        b = Ribbon.LabelRadiobutton(
            self.frame,
            image=Utils.icons["origin32"],
            text=_("Origin"),
            compound=TOP,
            anchor=W,
            variable=app.canvas.actionVar,
            value=ACTION_ORIGIN,
            command=app.canvas.setActionOrigin,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, rowspan=3, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Move all gcode such as origin is on mouse location [O]")
        )
        self.addWidget(b)

    # ----------------------------------------------------------------------
    def createMenu(self):
        menu = Menu(self, tearoff=0)
        for i, n, c in (
            ("tl", _("Top-Left"), "MOVE TL"),
            ("lc", _("Left"), "MOVE LC"),
            ("bl", _("Bottom-Left"), "MOVE BL"),
            ("tc", _("Top"), "MOVE TC"),
            ("center", _("Center"), "MOVE CENTER"),
            ("bc", _("Bottom"), "MOVE BC"),
            ("tr", _("Top-Right"), "MOVE TR"),
            ("rc", _("Right"), "MOVE RC"),
            ("br", _("Bottom-Right"), "MOVE BR"),
        ):
            menu.add_command(
                label=n,
                image=Utils.icons[i],
                compound=LEFT,
                command=lambda a=self.app, c=c: a.insertCommand(c, True),
            )
        return menu


# =============================================================================
# Order Group
# =============================================================================
class OrderGroup(CNCRibbon.ButtonMenuGroup):
    def __init__(self, master, app):
        CNCRibbon.ButtonMenuGroup.__init__(
            self,
            master,
            N_("Order"),
            app,
            [
                (
                    _("Optimize"),
                    "optimize",
                    lambda a=app: a.insertCommand("OPTIMIZE", True),
                ),
            ],
        )
        self.grid2rows()

        # ===
        col, row = 0, 0
        b = Ribbon.LabelButton(
            self.frame,
            self,
            "<Control-Key-Prior>",
            image=Utils.icons["up"],
            text=_("Up"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b,
            _("Move selected g-code up [Ctrl-Up, Ctrl-PgUp]")
        )
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            self,
            "<Control-Key-Next>",
            image=Utils.icons["down"],
            text=_("Down"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b,
            _("Move selected g-code down [Ctrl-Down, Ctrl-PgDn]")
        )
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            self,
            "<<Invert>>",
            image=Utils.icons["swap"],
            text=_("Invert"),
            compound=LEFT,
            anchor=W,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Invert cutting order of selected blocks"))
        self.addWidget(b)


# =============================================================================
# Transform Group
# =============================================================================
class TransformGroup(CNCRibbon.ButtonGroup):
    def __init__(self, master, app):
        CNCRibbon.ButtonGroup.__init__(self, master, N_("Transform"), app)
        self.grid3rows()

        # ---
        col, row = 0, 0
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["rotate_90"],
            text=_("CW"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand("ROTATE CW", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Rotate selected gcode clock-wise (-90deg)"))
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["rotate_180"],
            text=_("Flip"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand("ROTATE FLIP", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Rotate selected gcode by 180deg"))
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["rotate_270"],
            text=_("CCW"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand("ROTATE CCW", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Rotate selected gcode counter-clock-wise (90deg)"))
        self.addWidget(b)

        # ---
        col, row = 1, 0
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["flip_horizontal"],
            text=_("Horizontal"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand("MIRROR horizontal", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Mirror horizontally X=-X selected gcode"))
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["flip_vertical"],
            text=_("Vertical"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand("MIRROR vertical", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Mirror vertically Y=-Y selected gcode"))
        self.addWidget(b)

        # ---
        col, row = 2, 0
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["scale"],
            text=_("Scale"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: self._scaleDialog(s),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, rowspan=3, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b,
            _("Scale selected gcode\n"
              "Enter: sx [sy [x0 y0]]\n"
              "sx/sy = scale factors, x0/y0 = center (default 0,0)")
        )
        self.addWidget(b)

    # ----------------------------------------------------------------------
    def _scaleDialog(self, app):
        val = askstring(
            _("Scale"),
            _("Scale factor(s): sx [sy [x0 y0]]\n"
              "One value = uniform scale.\n"
              "Two values = separate X and Y scale."),
            initialvalue="1.0",
            parent=app,
        )
        if val and val.strip():
            app.insertCommand(f"SCALE {val.strip()}", True)


# =============================================================================
# Route Group
# =============================================================================
class RouteGroup(CNCRibbon.ButtonGroup):
    def __init__(self, master, app):
        CNCRibbon.ButtonGroup.__init__(self, master, N_("Route"), app)
        self.grid3rows()

        # ---
        col, row = 0, 0
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["conventional"],
            text=_("Conventional"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand(
                "DIRECTION CONVENTIONAL", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b,
            _("Change cut direction to conventional for selected gcode blocks")
        )
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["climb"],
            text=_("Climb"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand("DIRECTION CLIMB", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Change cut direction to climb for selected gcode blocks")
        )
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["reverse"],
            text=_("Reverse"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand("REVERSE", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Reverse cut direction for selected gcode blocks"))
        self.addWidget(b)

        # ---
        col, row = 1, 0
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["rotate_90"],
            text=_("Cut CW"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand("DIRECTION CW", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Change cut direction to CW for selected gcode blocks")
        )
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["rotate_270"],
            text=_("Cut CCW"),
            compound=LEFT,
            anchor=W,
            command=lambda s=app: s.insertCommand("DIRECTION CCW", True),
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Change cut direction to CCW for selected gcode blocks")
        )
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["redo"],
            text=_("Passes"),
            compound=LEFT,
            anchor=W,
            command=self._passesDialog,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Set how many times the selected blocks will be re-cut")
        )
        self.addWidget(b)

    # ------------------------------------------------------------------
    def _passesDialog(self):
        vals = _ask_shape_params(self.app, _("Repeat Cuts"), [
            (_("Number of passes (1 = no repeat)"), 2),
        ])
        if vals is None:
            return
        try:
            n = max(1, int(float(vals[0])))
        except (ValueError, IndexError):
            return
        self.app.insertCommand(f"PASSES {n}", True)


# =============================================================================
# Draw Group - basic shape generators
# =============================================================================
def _apply_dk_auto(app):
    """No-op: drag-knife is now applied transparently at send time (run()),
    so the editor always shows the original unmodified design."""
    pass


def _ask_shape_params(parent, title, fields):
    """Modal dialog with labeled entry fields.
    fields = [(label, default_value), ...]
    Returns list of value strings on OK, None on cancel.
    """
    result = [None]
    top = Toplevel(parent)
    top.title(title)
    top.resizable(False, False)
    top.grab_set()

    frm = Frame(top, padx=12, pady=8)
    frm.pack(fill=X)
    entries = []
    for i, (lbl, default) in enumerate(fields):
        Label(frm, text=lbl + ":", anchor=W, width=22).grid(
            row=i, column=0, sticky=W, pady=2, padx=(0, 8))
        var = StringVar(value=str(default))
        ent = Entry(frm, textvariable=var, width=14)
        ent.grid(row=i, column=1, sticky=W + E, pady=2)
        entries.append(var)
    if entries:
        frm.winfo_children()[1].focus_set()

    def _ok(event=None):
        result[0] = [v.get() for v in entries]
        top.destroy()

    def _cancel(event=None):
        top.destroy()

    bf = Frame(top, padx=10, pady=6)
    bf.pack(fill=X)
    Button(bf, text="Cancel", command=_cancel).pack(side=RIGHT, padx=4)
    Button(bf, text="OK", command=_ok, default="active").pack(side=RIGHT, padx=4)
    top.bind("<Return>", _ok)
    top.bind("<Escape>", _cancel)

    top.update_idletasks()
    px, py = parent.winfo_rootx(), parent.winfo_rooty()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    tw, th = top.winfo_width(), top.winfo_height()
    top.geometry(f"+{px + (pw - tw) // 2}+{py + (ph - th) // 2}")

    parent.wait_window(top)
    return result[0]


def _gen_polygon(name, n, cx, cy, r, start_deg):
    """Return a list of Blocks for a regular n-sided polygon."""
    from CNC import CNC, Block
    n = max(3, int(round(n)))
    block = Block(name)
    start_rad = math.radians(start_deg)
    pts = [
        (cx + r * math.cos(start_rad + 2 * math.pi * k / n),
         cy + r * math.sin(start_rad + 2 * math.pi * k / n))
        for k in range(n)
    ]
    block.append(CNC.grapid(x=pts[0][0], y=pts[0][1]))
    block.append(CNC.grapid(z=0.0))
    block.append("(entered)")
    for x, y in pts[1:]:
        block.append(CNC.gline(x=x, y=y))
    block.append(CNC.gline(x=pts[0][0], y=pts[0][1]))  # close
    block.append("(exiting)")
    block.append(CNC.grapid(z=CNC.vars["safe"]))
    return [block]


def _gen_star(name, n, cx, cy, r_outer, r_inner, start_deg):
    """Return a list of Blocks for an n-pointed star."""
    from CNC import CNC, Block
    n = max(3, int(round(n)))
    block = Block(name)
    start_rad = math.radians(start_deg)
    pts = []
    for k in range(n):
        a_out = start_rad + 2 * math.pi * k / n
        a_in  = a_out + math.pi / n
        pts.append((cx + r_outer * math.cos(a_out), cy + r_outer * math.sin(a_out)))
        pts.append((cx + r_inner * math.cos(a_in),  cy + r_inner * math.sin(a_in)))
    block.append(CNC.grapid(x=pts[0][0], y=pts[0][1]))
    block.append(CNC.grapid(z=0.0))
    block.append("(entered)")
    for x, y in pts[1:]:
        block.append(CNC.gline(x=x, y=y))
    block.append(CNC.gline(x=pts[0][0], y=pts[0][1]))  # close
    block.append("(exiting)")
    block.append(CNC.grapid(z=CNC.vars["safe"]))
    return [block]


class DrawGroup(CNCRibbon.ButtonGroup):
    def __init__(self, master, app):
        CNCRibbon.ButtonGroup.__init__(self, master, N_("Draw"), app)
        self.grid2rows()

        # --- Line ---
        col, row = 0, 0
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["SimpleLine"],
            text=_("Line"),
            compound=LEFT,
            anchor=W,
            command=self._draw_line,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Insert a straight line"))
        self.addWidget(b)

        # --- Rectangle ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["SimpleRectangle"],
            text=_("Rectangle"),
            compound=LEFT,
            anchor=W,
            command=self._draw_rectangle,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Insert a rectangle or square"))
        self.addWidget(b)

        # --- Circle ---
        col, row = 1, 0
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["SimpleArc"],
            text=_("Circle"),
            compound=LEFT,
            anchor=W,
            command=self._draw_circle,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Insert a circle"))
        self.addWidget(b)

        # --- Polygon ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["boolean"],
            text=_("Polygon"),
            compound=LEFT,
            anchor=W,
            command=self._draw_polygon,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Insert a regular polygon (3+ sides)"))
        self.addWidget(b)

        # --- Star ---
        col, row = 2, 0
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["spirograph"],
            text=_("Star"),
            compound=LEFT,
            anchor=W,
            command=self._draw_star,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Insert a star shape"))
        self.addWidget(b)

    # ------------------------------------------------------------------
    def _draw_line(self):
        vals = _ask_shape_params(self.app, _("Line"), [
            (_("X Start"), 0),
            (_("Y Start"), 0),
            (_("X End"),   10),
            (_("Y End"),   10),
        ])
        if vals is None:
            return
        try:
            p = self.app.tools["SimpleLine"]
            p["xstart"] = float(vals[0])
            p["ystart"] = float(vals[1])
            p["xend"]   = float(vals[2])
            p["yend"]   = float(vals[3])
            p.execute(self.app)
            _apply_dk_auto(self.app)
        except (ValueError, KeyError):
            pass

    # ------------------------------------------------------------------
    def _draw_rectangle(self):
        vals = _ask_shape_params(self.app, _("Rectangle"), [
            (_("X Start"),               0),
            (_("Y Start"),               0),
            (_("X End"),                20),
            (_("Y End"),                20),
            (_("Corner Radius"),         0),
            (_("Clockwise (1=yes, 0=no)"), 1),
        ])
        if vals is None:
            return
        try:
            p = self.app.tools["SimpleRectangle"]
            p["xstart"] = float(vals[0])
            p["ystart"] = float(vals[1])
            p["xend"]   = float(vals[2])
            p["yend"]   = float(vals[3])
            p["radius"] = float(vals[4])
            p["cw"]     = int(float(vals[5])) != 0
            p.execute(self.app)
            _apply_dk_auto(self.app)
        except (ValueError, KeyError):
            pass

    # ------------------------------------------------------------------
    def _draw_circle(self):
        vals = _ask_shape_params(self.app, _("Circle"), [
            (_("Center X"), 0),
            (_("Center Y"), 0),
            (_("Radius"),  10),
        ])
        if vals is None:
            return
        try:
            p = self.app.tools["SimpleArc"]
            p["xcenter"]    = float(vals[0])
            p["ycenter"]    = float(vals[1])
            p["radius"]     = float(vals[2])
            p["startangle"] = 0.0
            p["endangle"]   = 360.0
            p.execute(self.app)
            _apply_dk_auto(self.app)
        except (ValueError, KeyError):
            pass

    # ------------------------------------------------------------------
    def _draw_polygon(self):
        vals = _ask_shape_params(self.app, _("Polygon"), [
            (_("Center X"),    0),
            (_("Center Y"),    0),
            (_("Radius"),     10),
            (_("Sides"),       6),
            (_("Start Angle"), 90),
        ])
        if vals is None:
            return
        try:
            blocks = _gen_polygon(
                "Polygon",
                float(vals[3]), float(vals[0]), float(vals[1]),
                float(vals[2]), float(vals[4]),
            )
            active = self.app.activeBlock()
            if active == 0:
                active = 1
            self.app.gcode.insBlocks(active, blocks, _("Create Polygon"))
            self.app.refresh()
            self.app.setStatus(_("Generated: Polygon"))
            _apply_dk_auto(self.app)
        except (ValueError, ZeroDivisionError):
            pass

    # ------------------------------------------------------------------
    def _draw_star(self):
        vals = _ask_shape_params(self.app, _("Star"), [
            (_("Center X"),      0),
            (_("Center Y"),      0),
            (_("Outer Radius"), 10),
            (_("Inner Radius"),  4),
            (_("Points"),        5),
            (_("Start Angle"),  90),
        ])
        if vals is None:
            return
        try:
            blocks = _gen_star(
                "Star",
                float(vals[4]), float(vals[0]), float(vals[1]),
                float(vals[2]), float(vals[3]), float(vals[5]),
            )
            active = self.app.activeBlock()
            if active == 0:
                active = 1
            self.app.gcode.insBlocks(active, blocks, _("Create Star"))
            self.app.refresh()
            self.app.setStatus(_("Generated: Star"))
            _apply_dk_auto(self.app)
        except (ValueError, ZeroDivisionError):
            pass


# =============================================================================
# Info Group
# =============================================================================
class InfoGroup(CNCRibbon.ButtonGroup):
    def __init__(self, master, app):
        CNCRibbon.ButtonGroup.__init__(self, master, N_("Info"), app)
        self.grid2rows()

        # ---
        col, row = 0, 0
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["stats"],
            text=_("Statistics"),
            compound=LEFT,
            anchor=W,
            command=app.showStats,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(b, _("Show statistics for enabled gcode"))
        self.addWidget(b)

        # ---
        row += 1
        b = Ribbon.LabelButton(
            self.frame,
            image=Utils.icons["info"],
            text=_("Info"),
            compound=LEFT,
            anchor=W,
            command=app.showInfo,
            background=Ribbon._BACKGROUND,
        )
        b.grid(row=row, column=col, padx=0, pady=0, sticky=NSEW)
        tkExtra.Balloon.set(
            b, _("Show cutting information on selected blocks [Ctrl-n]")
        )
        self.addWidget(b)


# =============================================================================
# Main Frame of Editor
# =============================================================================
class EditorFrame(CNCRibbon.PageFrame):
    def __init__(self, master, app):
        CNCRibbon.PageFrame.__init__(self, master, "Editor", app)
        self.editor = CNCList.CNCListbox(
            self,
            app,
            selectmode=EXTENDED,
            exportselection=0,
            background=tkExtra.GLOBAL_CONTROL_BACKGROUND,
        )
        self.editor.pack(side=LEFT, expand=TRUE, fill=BOTH)
        self.addWidget(self.editor)

        sb = Scrollbar(self, orient=VERTICAL, command=self.editor.yview)
        sb.pack(side=RIGHT, fill=Y)
        self.editor.config(yscrollcommand=sb.set)


# =============================================================================
# Editor Page
# =============================================================================
class EditorPage(CNCRibbon.Page):
    __doc__ = _("GCode editor")
    _name_ = N_("Editor")
    _icon_ = "edit"

    # ----------------------------------------------------------------------
    # Add a widget in the widgets list to enable disable during the run
    # ----------------------------------------------------------------------
    def register(self):
        self._register(
            (
                ClipboardGroup,
                SelectGroup,
                EditGroup,
                OrderGroup,
                MoveGroup,
                TransformGroup,
                RouteGroup,
                DrawGroup,
                InfoGroup,
            ),
            (EditorFrame,),
        )
