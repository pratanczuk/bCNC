#!/usr/bin/env python3
# $Id: bCNC.py,v 1.6 2014/10/15 15:04:48 bnv Exp bnv $
#
# Author: vvlachoudis@gmail.com
# Date: 24-Aug-2014

import os
import shlex
import subprocess
import sys
import tempfile
import time
import traceback
import webbrowser
from datetime import datetime
import tkinter
from queue import Empty
from tkinter import (
    TclError,
    NO,
    YES,
    TRUE,
    W,
    E,
    NW,
    NE,
    EW,
    X,
    BOTH,
    LEFT,
    TOP,
    RIGHT,
    BOTTOM,
    RAISED,
    SUNKEN,
    HORIZONTAL,
    END,
    NORMAL,
    DISABLED,
    Tk,
    Toplevel,
    Button,
    Entry,
    Frame,
    Label,
    Listbox,
    Text,
    PhotoImage,
    Spinbox,
    LabelFrame,
    PanedWindow,
    messagebox,
)

try:
    import serial
except ImportError:
    serial = None
    print("testing mode, could not import serial")

import Utils

from tkinter import filedialog
import CNCCanvas

import Updates
import PlotterTk
# Load configuration before anything else
# and if needed replace the  translate function _()
# before any string is initialized
from CNC import CNC, WAIT, GCode
from MatManager import snap_blocks_to_mat
from Sender import NOT_CONNECTED, STATECOLOR, STATECOLORDEF, Sender
from PlotterTools import Tools

Utils.loadConfiguration()

__version__ = Utils.__version__
__date__ = Utils.__date__
__author__ = Utils.__author__
__email__ = Utils.__email__

if not (sys.version_info.major == 3 and sys.version_info.minor >= 8):
    print("ERROR: Python3.8 or newer is required to run bCNC!!")
    exit(1)

__platform_fingerprint__ = "".join([
    f"({sys.platform} ",
    f"py{sys.version_info.major}.",
    f"{sys.version_info.minor}.",
    f"{sys.version_info.micro})"
])

_openserial = True  # override ini parameters
_device = None
_baud = None

MONITOR_AFTER = 200  # ms
DRAW_AFTER = 300  # ms

RX_BUFFER_SIZE = 128

MAX_HISTORY = 500

FILETYPES = [
    (
        _("All accepted"),
        (
            "*.foil",
            "*.ngc",
            "*.cnc",
            "*.nc",
            "*.tap",
            "*.gcode",
            "*.dxf",
            "*.svg",
        ),
    ),
    ("Foil Studio project", "*.foil"),
    (_("G-Code"), ("*.ngc", "*.cnc", "*.nc", "*.tap", "*.gcode")),
    (_("G-Code clean"), ("*.txt")),
    ("DXF", "*.dxf"),
    ("SVG", "*.svg"),
    (_("All"), "*"),
]

geometry = None


# =============================================================================
# Main Application window
# =============================================================================
class Application(Tk):
    def destroy(self):
        if hasattr(self, 'workflow'):
            self.workflow.adaptive_ready = False
        # Tcl timers otherwise outlive their Python callbacks when a window is
        # closed and a new application is opened in the same process.
        for timer in self.tk.call('after', 'info'):
            self.after_cancel(timer)
        super().destroy()

    def showTextInsertion(self, event=None):
        """Use the same vector editor in the workspace and diagnostics."""
        self.workflow.add_text()
        return "break"

    def showImageTrace(self, event=None):
        """Use the same trace preview in the workspace and diagnostics."""
        self.workflow.design_dialog('TraceDialog')
        return "break"

    def __init__(self, **kw):
        Tk.__init__(self, **kw)
        CNC.loadConfig(Utils.config)
        self.gcode = GCode()
        self.cnc = self.gcode.cnc
        self.sender = Sender(self.gcode)
        self._quit = 0
        from PlotterFiles import DocumentFiles
        self.files = DocumentFiles(self.gcode)
        from PlotterEngine import PlotterEngine
        from PlotterMachine import MachineService
        from PlotterAdapters import DocumentJobPort, SenderMachinePort, ApplicationConfigurationStore
        self.plotter = PlotterEngine(DocumentJobPort(self))
        self.machine = MachineService(SenderMachinePort(self))
        from PlotterMat import MatHandling
        self.mat_handling = MatHandling(SenderMachinePort(self), self.matStatus)
        from PlotterSequence import ToolSequence
        self.tool_sequence = ToolSequence(SenderMachinePort(self), self.submitToolPass, self.sequenceStatus)
        from PlotterConnections import ConnectionService
        from PlotterAdapters import SenderConnectionPort
        self.connection = ConnectionService(SenderConnectionPort(self))
        self.configuration = ApplicationConfigurationStore(self)

        Utils.loadIcons()
        PlotterTk.bindClasses(self)

        photo = PhotoImage(file=f"{Utils.prgpath}/bCNC.png")
        self.iconphoto(True, photo)
        self.title(f"Foil Studio {__version__} {__platform_fingerprint__}")
        self.widgets = []

        # Global variables
        self.tools = Tools(self.gcode)
        self.sender.controller = None
        self.loadConfig()
        # Application state has no hidden Tk presentation.
        from PlotterSelection import DocumentEditor
        from PlotterSession import ConnectionPreferences, DiagnosticLog
        self.connection_preferences = ConnectionPreferences.load()
        self.sender.connection_preferences = self.connection_preferences
        self.diagnostic_log = DiagnosticLog()
        self.editor = DocumentEditor(self)
        self.paned = PanedWindow(self, orient=HORIZONTAL)
        self.paned.pack(fill=BOTH, expand=YES)
        frame = Frame(self.paned)
        self.canvasPane = frame
        self.paned.add(frame)
        self.canvasFrame = CNCCanvas.CanvasFrame(frame, self)
        self.canvasFrame.pack(side=TOP, fill=BOTH, expand=YES)
        self.canvas = self.canvasFrame.canvas

        # Global bindings
        self.bind("<<Undo>>", self.undo)
        self.bind("<<Redo>>", self.redo)
        self.bind("<<Copy>>", self.copy)
        self.bind("<<Cut>>", self.cut)
        self.bind("<<Paste>>", self.paste)

        self.bind("<<Connect>>", self.openClose)

        self.bind("<<New>>", self.newFile)
        self.bind("<<Open>>", self.loadDialog)
        self.bind("<<Import>>", lambda x, s=self: s.importFile())
        self.bind("<<LibreCAD>>", lambda x, s=self: s.openLibreCAD())
        self.bind("<<Inkscape>>", lambda x, s=self: s.openInkscape())
        self.bind("<<Save>>", self.saveAll)
        self.bind("<<SaveAs>>", self.saveDialog)
        self.bind("<<Reload>>", self.reload)

        self.bind("<<Recent0>>", lambda event, index=0: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)
        self.bind("<<Recent1>>", lambda event, index=1: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)
        self.bind("<<Recent2>>", lambda event, index=2: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)
        self.bind("<<Recent3>>", lambda event, index=3: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)
        self.bind("<<Recent4>>", lambda event, index=4: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)
        self.bind("<<Recent5>>", lambda event, index=5: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)
        self.bind("<<Recent6>>", lambda event, index=6: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)
        self.bind("<<Recent7>>", lambda event, index=7: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)
        self.bind("<<Recent8>>", lambda event, index=8: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)
        self.bind("<<Recent9>>", lambda event, index=9: self.load(Utils.getRecent(index)) if Utils.getRecent(index) else None)

        self.bind("<<TerminalClear>>", self.diagnostic_log.clear)
        self.bind("<<AlarmClear>>", self.alarmClear)
        self.bind("<<Help>>", lambda event: webbrowser.open("https://github.com/vlachoudis/bCNC/wiki", new=2))
        # Do not send the event otherwise it will skip the feedHold/resume
        self.bind("<<FeedHold>>", lambda event: self.sender.feedHold())
        self.bind("<<Resume>>", lambda event: self.sender.resume())
        self.bind("<<Run>>", lambda e, s=self: s.run())
        self.bind("<<Stop>>", self.sender.stopRun)
        self.bind("<<Pause>>", self.sender.pause)

        # Req D / E / F / G event hooks ──────────────────────────────────
        self.bind("<<LoadMat>>",       lambda e, s=self: s.loadMat())
        self.bind("<<UnloadMat>>",     lambda e, s=self: s.unloadMat())
        self.bind("<<PlotterSettings>>",
                  lambda e, s=self: s.openPlotterSettings())
        self.bind("<<MatDrag>>",
                  lambda e, s=self: s.canvas.setActionMatDrag())

        PlotterTk.bindEventData(self, "<<Status>>", self.updateStatus)
        PlotterTk.bindEventData(self, "<<Coords>>", self.updateCanvasCoords)

        # Editor bindings
        self.bind("<<Add>>", self.editor.insertItem)
        self.bind("<<AddBlock>>", self.editor.insertBlock)
        self.bind("<<AddLine>>", self.editor.insertLine)
        self.bind("<<Clone>>", self.editor.clone)
        self.canvas.bind("<Control-Key-Prior>", self.editor.orderUp)
        self.canvas.bind("<Control-Key-Next>", self.editor.orderDown)
        self.canvas.bind("<Control-Key-d>", self.editor.clone)
        self.canvas.bind("<Control-Key-c>", self.copy)
        self.canvas.bind("<Control-Key-x>", self.cut)
        self.canvas.bind("<Control-Key-v>", self.paste)
        self.bind("<<Delete>>", self.editor.deleteBlock)
        self.canvas.bind("<Delete>", self.editor.deleteBlock)
        self.canvas.bind("<BackSpace>", self.editor.deleteBlock)
        try:
            self.canvas.bind("<KP_Delete>", self.editor.deleteBlock)
        except Exception:
            pass
        self.bind("<<Invert>>", self.editor.invertBlocks)
        self.bind("<<Expand>>", self.editor.toggleExpand)
        self.bind("<<EnableToggle>>", self.editor.toggleEnable)
        self.bind("<<Enable>>", self.editor.enable)
        self.bind("<<Disable>>", self.editor.disable)
        self.bind("<<ChangeColor>>", self.editor.changeColor)
        self.bind("<<Comment>>", self.editor.commentRow)
        self.bind("<<Join>>", self.editor.joinBlocks)
        self.bind("<<Split>>", self.editor.splitBlocks)
        self.bind("<<SmoothPath>>", self.editor.smoothBlocks)
        self.bind("<<InsertText>>", self.showTextInsertion)
        self.bind("<<ImageTrace>>", self.showImageTrace)
        self.bind("<<Intersection>>", self.editor.intersectPaths)
        self.bind("<<Union>>", self.editor.unionPaths)
        self.bind("<<Difference>>", self.editor.differencePaths)
        self.bind(
            "<<SymmetricDifference>>",
            self.editor.symmetricDifferencePaths,
        )

        # Canvas X-bindings
        self.bind("<<ViewChange>>", self.viewChange)
        self.bind("<<MoveGantry>>", lambda event: self.workflow.open_diagnostics())
        self.bind("<<SetWPOS>>", lambda event: self.workflow.open_diagnostics())


        self.bind("<<CanvasFocus>>", self.canvasFocus)
        self.bind("<<Draw>>", self.draw)
        self.bind("<<ListboxSelect>>", self.selectionChange)
        self.bind("<<Modified>>", self.drawAfter)

        self.bind("<Control-Key-a>", self.selectAll)
        self.bind("<Control-Key-A>", self.unselectAll)
        self.bind("<Escape>", self.unselectAll)
        self.bind("<Control-Key-i>", self.selectInvert)

        self.bind("<<SelectAll>>", self.selectAll)
        self.bind("<<SelectNone>>", self.unselectAll)
        self.bind("<<SelectInvert>>", self.selectInvert)
        self.bind("<<SelectLayer>>", self.selectLayer)

        self.bind("<Control-Key-e>", self.editor.toggleExpand)
        self.bind("<Control-Key-n>", self.showInfo)
        self.bind("<<ShowInfo>>", self.showInfo)
        self.bind("<Control-Key-l>", self.editor.toggleEnable)
        self.bind("<Control-Key-q>", self.quit)
        self.bind("<Control-Key-o>", self.loadDialog)
        self.bind("<Control-Key-r>", self.drawAfter)
        self.bind("<Control-Key-s>", self.saveAll)
        self.bind("<Control-Key-y>", self.redo)
        self.bind("<Control-Key-z>", self.undo)
        self.bind("<Control-Key-Z>", self.redo)

        # Manual movement is confined to Advanced settings.

        for x in self.widgets:
            if isinstance(x, Entry):
                x.bind("<Escape>", self.canvasFocus)

        self.bind("<FocusIn>", self.focusIn)
        self.protocol("WM_DELETE_WINDOW", self.quit)

        self.canvas.focus_set()

        # Fill basic global variables
        CNC.vars["state"] = NOT_CONNECTED
        CNC.vars["color"] = STATECOLOR[NOT_CONNECTED]
        self._drawAfter = None  # after handle for modification
        self._inFocus = False
        # END - insertCount lines where ok was applied to for $xxx commands
        self._insertCount = (0)
        self.monitorSerial()
        self.canvasFrame.toggleDrawFlag()


        # Collapse the State sub-panel by default to save screen real estate.
        # Use after_idle() so the widget is fully laid out before collapse()
        # reads winfo_width() – otherwise it would get 1 (un-rendered size).

        from PlotterAdaptive import AdaptiveWorkflow
        self.workflow = AdaptiveWorkflow(self)

        # Auto start serial when configured.

        if _openserial and Utils.getBool("Connection", "openserial"):
            self.openClose()

    # -----------------------------------------------------------------------
    def setStatus(self, msg, force_update=False):
        CNC.vars['msg'] = str(msg)
        if force_update:
            self.update_idletasks()

    # -----------------------------------------------------------------------
    # Set a status message from an event
    # -----------------------------------------------------------------------
    def updateStatus(self, event):
        self.setStatus(_(event.data))

    # -----------------------------------------------------------------------
    # Update canvas coordinates
    # -----------------------------------------------------------------------
    def updateCanvasCoords(self, event):
        x, y, z = event.data.split()
        self.cursor_position = (x, y, z)

    # -----------------------------------------------------------------------
    def quit(self, event=None):
        if (self.sender.running
                or getattr(getattr(self, 'mat_handling', None), 'active', False)
                or getattr(getattr(self, 'tool_sequence', None), 'active', False)):
            messagebox.showinfo(
                _("Running"),
                _("CNC is currently running, please stop it before."),
                parent=self,
            )
            return
        if self.fileModified():
            return

        del self.widgets[:]

        if hasattr(self, "workflow"):
            self.workflow.project.clear_recovery()
        self.saveConfig()
        self.destroy()

    # ---------------------------------------------------------------------
    def configWidgets(self, var, value):
        for w in self.widgets:
            if isinstance(w, tuple):
                try:
                    w[0].entryconfig(w[1], state=value)
                except TclError:
                    pass
            else:
                w[var] = value

    # ---------------------------------------------------------------------
    def busy(self):
        try:
            self.config(cursor="watch")
            self.update_idletasks()
        except TclError:
            pass

    # ----------------------------------------------------------------------
    def notBusy(self):
        try:
            self.config(cursor="")
        except TclError:
            pass

    # ---------------------------------------------------------------------
    def enable(self):
        self.configWidgets("state", NORMAL)

    # ---------------------------------------------------------------------
    def disable(self):
        self.configWidgets("state", DISABLED)

    # ----------------------------------------------------------------------
    # Check for updates
    # ----------------------------------------------------------------------
    def checkUpdates(self):
        # Find bCNC version
        Updates.CheckUpdateDialog(self, __version__)

    # ----------------------------------------------------------------------
    # Show the error message, if no serial is present
    # ----------------------------------------------------------------------
    def showSerialError(self):
        self.reportPlotterError(_("python serial missing"), _(
                "ERROR: Please install the python pyserial module\n"
                "Windows:\n\tC:\\PythonXX\\Scripts\\easy_install pyserial\n"
                "Mac:\tpip install pyserial\n"
                "Linux:\tsudo apt-get install python-serial\n"
                "\tor yum install python-serial\n"
                "\tor dnf install python-pyserial"
            ))

    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------
    def loadConfig(self):
        global geometry

        if geometry is None:
            geometry = "x".join([
                f"{Utils.getInt(Utils.__prg__, 'width', 900)}",
                f"{Utils.getInt(Utils.__prg__, 'height', 650)}"
            ])
        try:
            self.geometry(geometry)
        except Exception:
            pass

        # restore windowsState
        try:
            self.wm_state(Utils.getStr(Utils.__prg__, "windowstate", "normal"))
        except Exception:
            pass


        PlotterTk.Balloon.font = Utils.getFont("balloon", PlotterTk.Balloon.font)

        self.tools.loadConfig()
        configured = Utils.getStr('Connection', 'controller')
        self.sender.controllerSet(configured if configured in self.sender.controllers else 'GRBL1')
        GCode.LOOP_MERGE = Utils.getBool('File', 'dxfloopmerge')

        # ── Plotter / cutting-mat settings ──────────────────────────────────
        CNC.vars["mat_pressure"]      = Utils.getFloat("Plotter", "pressure",      500.0)
        CNC.vars["mat_speed"]         = Utils.getFloat("Plotter", "speed",         500.0)
        CNC.vars["mat_knife_offset"]  = Utils.getFloat("Plotter", "knife_offset",  0.5)
        CNC.vars["mat_overcut"] = Utils.getFloat("Plotter", "overcut", Utils.getFloat("DragKnife", "overcut", 0.0))
        CNC.vars["mat_width"]         = Utils.getFloat("Plotter", "mat_width",     300.0)
        CNC.vars["mat_height"]        = Utils.getFloat("Plotter", "mat_height",    300.0)
        CNC.vars["mat_load_distance"]   = Utils.getFloat("Plotter", "load_distance",  20.0)
        CNC.vars["mat_auto_dragknife"]  = Utils.getBool("Plotter", "auto_dragknife", False)

    # -----------------------------------------------------------------------
    def saveConfig(self):
        # Program
        Utils.setInt(Utils.__prg__, "width", str(self.winfo_width()))
        Utils.setInt(Utils.__prg__, "height", str(self.winfo_height()))

        # save windowState
        Utils.setStr(Utils.__prg__, "windowstate", str(self.wm_state()))
        self.connection_preferences.save()

        # Connection
        self.tools.saveConfig()
        self.canvasFrame.saveConfig()

        # ── Plotter / cutting-mat settings ──────────────────────────────────
        Utils.addSection("Plotter")
        Utils.setStr("Plotter", "pressure",      CNC.vars.get("mat_pressure",      500.0))
        Utils.setStr("Plotter", "speed",         CNC.vars.get("mat_speed",         500.0))
        Utils.setStr("Plotter", "knife_offset",  CNC.vars.get("mat_knife_offset",  0.5))
        Utils.setStr("Plotter", "overcut", CNC.vars.get("mat_overcut", 0.0))
        Utils.setStr("Plotter", "mat_width",     CNC.vars.get("mat_width",         300.0))
        Utils.setStr("Plotter", "mat_height",    CNC.vars.get("mat_height",        300.0))
        Utils.setBool("Plotter", "auto_dragknife", CNC.vars.get("mat_auto_dragknife", False))
        Utils.setStr("Plotter", "load_distance",  CNC.vars.get("mat_load_distance",  20.0))

    # -----------------------------------------------------------------------
    def cut(self, event=None):
        focus = self.focus_get()
        if focus in (self.canvas, self.editor):
            self.editor.cut()
            return "break"

    # -----------------------------------------------------------------------
    def copy(self, event=None):
        focus = self.focus_get()
        if focus in (self.canvas, self.editor):
            self.editor.copy()
            return "break"

    # -----------------------------------------------------------------------
    def paste(self, event=None):
        focus = self.focus_get()
        if focus in (self.canvas, self.editor):
            self.editor.paste()
            return "break"

    # -----------------------------------------------------------------------
    def undo(self, event=None):
        if not self.sender.running and self.gcode.canUndo():
            self.gcode.undo()
            self.editor.fill()
            self.drawAfter()
        return "break"

    # -----------------------------------------------------------------------
    def redo(self, event=None):
        if not self.sender.running and self.gcode.canRedo():
            self.gcode.redo()
            self.editor.fill()
            self.drawAfter()
        return "break"

    # -----------------------------------------------------------------------
    def addUndo(self, undoinfo):
        self.gcode.addUndo(undoinfo)

    # -----------------------------------------------------------------------
    def alarmClear(self, event=None):
        self.sender._alarm = False

    # -----------------------------------------------------------------------
    # Display information on selected blocks
    # -----------------------------------------------------------------------
    def showInfo(self, event=None):
        self.canvas.showInfo(self.editor.getSelectedBlocks())
        return "break"

    # -----------------------------------------------------------------------
    def viewChange(self, event=None):
        if self.sender.running:
            self._selectI = 0  # last selection pointer in items
        self.draw()

    # ----------------------------------------------------------------------
    def refresh(self, event=None):
        from PlotterLayers import apply_visibility
        apply_visibility(self.gcode)
        self.editor.fill()
        self.draw()

    # ----------------------------------------------------------------------
    def draw(self):
        from PlotterLayers import apply_visibility
        apply_visibility(self.gcode)
        self.canvas.draw()
        self.selectionChange()

    # ----------------------------------------------------------------------
    # Redraw with a small delay
    # ----------------------------------------------------------------------
    def drawAfter(self, event=None):
        if self._drawAfter is not None:
            self.after_cancel(self._drawAfter)
        self._drawAfter = self.after(DRAW_AFTER, self.draw)
        return "break"

    # -----------------------------------------------------------------------
    def canvasFocus(self, event=None):
        self.canvas.focus_set()
        return "break"

    # -----------------------------------------------------------------------
    def automaticMatLoading(self):
        mode = Utils.getStr("Plotter", "load_mode", "auto")
        return mode != "manual" and getattr(self.sender.firmware, "board", "") == "GRBLFilmCut"

    def matStatus(self, message, error):
        self.setStatus(message)
        if error:
            self.reportPlotterError("Mat needs attention", message)

    def handleMat(self, loading):
        if not self.machine.snapshot().ready:
            self.setStatus("Connect the plotter and wait until it is idle before handling the mat.")
            return
        self.workflow.confirmed.set(False)
        CNC.vars["mat_loaded"] = False
        if self.automaticMatLoading():
            try:
                self.mat_handling.begin(loading, CNC.vars.get("mat_load_distance", 20), CNC.vars.get("mat_height", 300))
            except ValueError as error:
                self.matStatus(str(error), True)
        else:
            if not loading:
                self.sender.sendGCode("M5")
            self.sender.sendGCode("G92 X0 Y0" if loading else "G92.1")
            self.setStatus("Mat origin requested. Confirm alignment when idle." if loading else
                           "Blade release requested. Wait until idle, then remove the mat manually.")
        self.drawAfter()

    def loadMat(self, event=None):
        self.handleMat(True)

    def unloadMat(self, event=None):
        self.handleMat(False)

    # -----------------------------------------------------------------------
    def openPlotterSettings(self, event=None):
        return self.workflow.settings()

    # -----------------------------------------------------------------------
    def selectAll(self, event=None):
        focus = self.focus_get()
        if focus in (self.canvas, self.editor):
            self.editor.selectAll()
            self.selectionChange()
            return "break"

    # -----------------------------------------------------------------------
    def unselectAll(self, event=None):
        focus = self.focus_get()
        if focus in (self.canvas, self.editor):
            self.editor.selectClear()
            self.selectionChange()
            return "break"

    # -----------------------------------------------------------------------
    def selectInvert(self, event=None):
        focus = self.focus_get()
        if focus in (self.canvas, self.editor):
            self.editor.selectInvert()
            self.selectionChange()
            return "break"

    # -----------------------------------------------------------------------
    def selectLayer(self, event=None):
        focus = self.focus_get()
        if focus in (self.canvas, self.editor):
            self.editor.selectLayer()
            self.selectionChange()
            return "break"

    # -----------------------------------------------------------------------
    def activeBlock(self):
        return self.editor.activeBlock()

    # -----------------------------------------------------------------------
    def edit(self, event=None):
        return self.workflow.design_dialog('LayersDialog')

    # -----------------------------------------------------------------------
    def select(self, items, double, clear, toggle=True):
        self.editor.select(items, double, clear, toggle)
        self.selectionChange()

    # ----------------------------------------------------------------------
    # Selection has changed highlight the canvas
    # ----------------------------------------------------------------------
    def selectionChange(self, event=None):
        if hasattr(self,'workflow'):
            selected=self.editor.getSelectedBlocks()
            expanded=self.workflow.expand_groups(selected)
            if set(expanded)!=set(selected):
                self.editor.select([(i,None) for i in expanded],clear=True)
            if hasattr(self.workflow,'objects'):
                self.workflow.objects.selection_clear(0,END)
                for position,index in enumerate(self.workflow.object_ids):
                    if index in expanded: self.workflow.objects.selection_set(position)
        items = self.editor.getSelection()
        self.canvas.clearSelection()
        if hasattr(self, 'workflow'):
            self.workflow.update_state()
        if not items:
            return
        self.canvas.select(items)
        self.canvas.activeMarker(self.editor.getActive())

    # -----------------------------------------------------------------------
    # Create a new file
    # -----------------------------------------------------------------------
    def newFile(self, event=None):
        if self.sender.running:
            return
        if self.fileModified():
            return
        self.gcode.init()
        self.gcode.headerFooter()
        self.editor.fill()
        self.draw()
        self.title(f"Foil Studio {__version__} {__platform_fingerprint__}")
        self.workflow.fit_mat()

    # -----------------------------------------------------------------------
    # load dialog
    # -----------------------------------------------------------------------
    def loadDialog(self, event=None):
        if self.sender.running:
            return
        filename = filedialog.askopenfilename(
            parent=self,
            title=_("Open file"),
            initialfile=os.path.join(
                Utils.getUtf("File", "dir"), Utils.getUtf("File", "file")
            ),
            filetypes=FILETYPES,
        )
        if filename:
            self.load(filename)
        return "break"

    # -----------------------------------------------------------------------
    # save dialog
    # -----------------------------------------------------------------------
    def saveDialog(self, event=None):
        if self.sender.running:
            return
        fn, ext = os.path.splitext(Utils.getUtf("File", "file"))
        if ext in (".dxf", ".DXF"):
            ext = ".ngc"
        filename = filedialog.asksaveasfilename(
            parent=self,
            title=_("Save file"),
            initialfile=os.path.join(Utils.getUtf("File", "dir"), fn + ext),
            filetypes=FILETYPES,
        )
        if filename:
            self.save(filename)
        return "break"

    # -----------------------------------------------------------------------
    def fileModified(self):
        if self.gcode.isModified():
            from PlotterPages import ask_save_changes
            ans = ask_save_changes(self)
            if ans == messagebox.CANCEL:
                return True
            if ans == messagebox.YES or ans is True:
                if self.saveAll() is False:
                    return True

        return False

    # -----------------------------------------------------------------------
    # Load a file into editor
    # -----------------------------------------------------------------------
    def load(self, filename, autoloaded=False):
        if str(filename).lower().endswith('.foil') and hasattr(self, 'workflow'):
            return self.workflow.project.open(filename)
        fn, ext = os.path.splitext(filename)
        if ext.lower() in ('.stl', '.ply', '.probe', '.orient', '.xyz'):
            self.reportPlotterError('Unsupported file type', 'Use SVG, DXF or GRBL cut files. Height maps, alignment files and 3D meshes are no longer supported.')
            return
        if self.fileModified():
            return

        self.setStatus(_("Loading: {} ...").format(filename), True)
        self.files.load(filename)

        self.editor.selectClear()
        self.editor.fill()
        self.canvas.reset()
        self.draw()
        self.canvas.fit2Screen()
        self.workflow.finish_import(filename)
        # Note: drag-knife compensation is applied transparently at send
        # time (run()) when mat_auto_dragknife is enabled, so the editor
        # always shows the original unmodified design.

        if autoloaded:
            self.setStatus(
                _("'{}' reloaded at '{}'").format(
                    filename, str(datetime.now()))
            )
        else:
            self.setStatus(_("'{}' loaded").format(filename))
        self.title(
            f"Foil Studio {__version__}: {self.gcode.filename} "
            + f"{__platform_fingerprint__}"
        )

    # -----------------------------------------------------------------------
    def save(self, filename):
        if str(filename).lower().endswith('.foil') and hasattr(self, 'workflow'):
            return self.workflow.project.save(filename)
        self.files.save(filename)
        self.setStatus(_("'{}' saved").format(filename))
        self.title(
            f"Foil Studio {__version__}: {self.gcode.filename} "
            + f"{__platform_fingerprint__}"
        )

    # -----------------------------------------------------------------------
    def saveAll(self, event=None):
        if hasattr(self, 'workflow'):
            return self.workflow.project.save()
        if self.gcode.filename:
            self.files.save(self.gcode.filename)
        else:
            self.saveDialog()
        return "break"

    # -----------------------------------------------------------------------
    def reload(self, event=None):
        self.load(self.gcode.filename)

    # -----------------------------------------------------------------------
    def importFile(self, filename=None, skip_header_footer=False):
        if filename is None:
            filename = filedialog.askopenfilename(
                parent=self,
                title=_("Import Gcode/DXF file"),
                initialfile=os.path.join(
                    Utils.getUtf("File", "dir"), Utils.getUtf("File", "file")
                ),
                filetypes=[
                    (_("G-Code"), ("*.ngc", "*.nc", "*.gcode")),
                    ("DXF", "*.dxf"),
                    ("All", "*"),
                ],
            )
        if filename:
            fn, ext = os.path.splitext(filename)
            ext = ext.lower()
            gcode = GCode()
            if ext == ".dxf":
                gcode.importDXF(filename)
            elif ext == ".svg":
                gcode.importSVG(filename)
            else:
                gcode.load(filename)

            # Imported bCNC files and generated DXF/SVG files can carry their
            # own Header/Footer wrapper.  When merging into an existing job,
            # retain the active job's single wrapper pair and insert only the
            # imported drawing blocks.
            active_has_wrapper = any(
                block.name() in ("Header", "Footer")
                for block in self.gcode.blocks
            )
            if skip_header_footer or active_has_wrapper:
                gcode.blocks[:] = [
                    block for block in gcode.blocks
                    if block.name() not in ("Header", "Footer")
                ]

            if skip_header_footer:
                self.gcode.headerFooter()

            sel = self.editor.getSelectedBlocks()
            if not sel:
                footer = next(
                    (
                        bid for bid, block in enumerate(self.gcode.blocks)
                        if block.name() == "Footer"
                    ),
                    None,
                )
                pos = footer
            else:
                pos = sel[-1]
            first = (len(self.gcode.blocks) if pos is None
                     or pos >= len(self.gcode.blocks) else pos)
            inserted = list(range(first, first + len(gcode.blocks)))
            self.addUndo(self.gcode.insBlocksUndo(pos, gcode.blocks))
            del gcode
            self.editor.fill()
            self.draw()
            self.workflow.fit_mat()
            # Note: drag-knife compensation is applied at send time (run()),
            # not on import, so the original design remains editable.
            return inserted

    # -----------------------------------------------------------------------
    def openLibreCAD(self, event=None):
        """Create a DXF drawing in LibreCAD and import it when it exits."""
        return self.openExternalEditor(
            _("LibreCAD"),
            "librecad",
            ".dxf",
            "0\nSECTION\n2\nHEADER\n0\nENDSEC\n"
            "0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n",
        )

    # -----------------------------------------------------------------------
    def openInkscape(self, event=None):
        """Create an SVG drawing in Inkscape and import it when it exits."""
        return self.openExternalEditor(
            _("Inkscape"),
            "inkscape",
            ".svg",
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<svg xmlns=\"http://www.w3.org/2000/svg\" version=\"1.1\">\n"
            "</svg>\n",
        )

    # -----------------------------------------------------------------------
    def openExternalEditor(self, editor_name, config_key, suffix, contents):
        """Edit a temporary drawing and import it after its editor exits."""
        filename = None
        try:
            fd, filename = tempfile.mkstemp(prefix="bCNC-", suffix=suffix)
            with os.fdopen(fd, "w", encoding="utf-8") as drawing:
                drawing.write(contents)
            command = Utils.getStr(
                "Editors",
                config_key,
                Utils.getStr("File", config_key, config_key),
            )
            arguments = shlex.split(command, posix=os.name != "nt")
            if not arguments:
                raise ValueError(_("No editor command is configured."))
            environment = os.environ.copy()
            # bCNC can be launched from Snap-packaged VS Code. Its GTK paths
            # make system-installed Inkscape load incompatible Snap libraries.
            for variable in (
                    "GTK_PATH",
                    "GTK_EXE_PREFIX",
                    "GDK_PIXBUF_MODULE_FILE",
                    "GDK_PIXBUF_MODULEDIR",
            ):
                environment.pop(variable, None)
            process = subprocess.Popen(arguments + [filename], env=environment)
            stat = os.stat(filename)
        except (OSError, ValueError) as error:
            if filename:
                try:
                    os.unlink(filename)
                except OSError:
                    pass
            self.reportPlotterError(editor_name, _("Unable to start {}:\n{}").format(editor_name, error))
            return "break"

        self.setStatus(
            _("Edit the drawing in {}, save it, then close the editor.").format(
                editor_name
            )
        )
        self.after(
            250,
            self._importExternalDrawing,
            process,
            filename,
            stat.st_mtime_ns,
            stat.st_size,
            editor_name,
        )
        return "break"

    # -----------------------------------------------------------------------
    def _importExternalDrawing(
            self, process, filename, mtime_ns, size, editor_name):
        """Import a temporary drawing only when it was saved by the user."""
        exit_code = process.poll()
        if exit_code is None:
            self.after(
                250,
                self._importExternalDrawing,
                process,
                filename,
                mtime_ns,
                size,
                editor_name,
            )
            return

        if exit_code:
            try:
                os.unlink(filename)
            except OSError:
                pass
            self.reportPlotterError(editor_name, _("{} exited with error code {}.").format(
                    editor_name, exit_code
                ))
            return

        try:
            stat = os.stat(filename)
        except OSError:
            self.setStatus(_("{} drawing was not saved.").format(editor_name))
            return

        if stat.st_mtime_ns == mtime_ns and stat.st_size == size:
            os.unlink(filename)
            self.setStatus(_("{} drawing was not changed.").format(editor_name))
            return

        try:
            inserted = self.importFile(filename, skip_header_footer=True)
            self.after_idle(snap_blocks_to_mat, self, inserted)
            self.setStatus(_("{} drawing imported.").format(editor_name))
        except Exception as error:
            self.reportPlotterError(_("{} import").format(editor_name), _("Unable to import {} drawing:\n{}").format(editor_name, error))
        finally:
            try:
                os.unlink(filename)
            except OSError:
                pass

    # -----------------------------------------------------------------------
    def focusIn(self, event):
        if self._inFocus:
            return
        # FocusIn is generated for all sub-windows, handle only the main window
        if self is not event.widget:
            return
        self._inFocus = True
        if self.gcode.checkFile():
            if self.gcode.isModified():
                ans = messagebox.askquestion(
                    _("Warning"),
                    _(
                        "Gcode file {} was changed since "
                        "editing started\n"
                        "Reload new version?"
                    ).format(self.gcode.filename),
                    parent=self,
                )
                if ans == messagebox.YES or ans is True:
                    self.gcode.resetModified()
                    self.load(self.gcode.filename)
            else:
                self.load(self.gcode.filename, True)
        self._inFocus = False
        self.gcode.syncFileTime()

    # -----------------------------------------------------------------------
    def openClose(self, event=None):
        if self.sender.serial is not None:
            self.close()
        else:
            options = self.connection.defaults()
            try:
                self.connection.connect(_device or options.port, _baud or options.baud, options.controller)
            except ValueError as error:
                self.reportPlotterError('Connection setup needed', str(error))

    # -----------------------------------------------------------------------
    def open(self, device, baudrate):
        try:
            return self.sender.open(device, baudrate)
        except Exception as error:
            if self.sender.serial is not None:
                try:
                    self.sender.serial.close()
                except Exception:
                    pass
            self.sender.serial = None
            self.sender.thread = None
            self.reportPlotterError(_("Could not connect"), str(error))
        return False

    def reportPlotterError(self, title, detail):
        if hasattr(self, "workflow"):
            self.workflow.report_error(title, detail)
            parent = (getattr(self, 'workspace_pages', []) or [self.grab_current()])[-1]
            if parent is not None and parent is not self:
                from PlotterErrorDialog import show_modal_error
                current = getattr(self, '_error_dialog', None)
                if current is None or not current.winfo_exists():
                    self._error_dialog = show_modal_error(self.workflow, parent.winfo_toplevel() if parent else self, title, detail)
        else:
            messagebox.showerror(title, detail, parent=self)

    def report_callback_exception(self, kind, value, tb):
        if getattr(self, '_reporting_error', False):
            traceback.print_exception(kind, value, tb)
            return
        self._reporting_error = True
        try:
            detail = ''.join(traceback.format_exception(kind, value, tb))
            if self.sender.running:
                self.sender._stop = True
                self.sender.emptyQueue()
                try:
                    self.sender.feedHold()
                except Exception:
                    detail += '\nCould not request a controller hold. Check the machine directly.'
            self.reportPlotterError('Internal application error', detail)
        finally:
            self._reporting_error = False

    # -----------------------------------------------------------------------
    def close(self):
        self.sender.close()
        self.sender.firmware = None

    # -----------------------------------------------------------------------
    # An entry function should be called periodically during compiling
    # to check if the Pause or Stop buttons are pressed
    # @return true if the compile has to abort
    # -----------------------------------------------------------------------
    def checkStop(self):
        try:
            self.update()  # very tricky function of Tk
        except TclError:
            pass
        return self.sender._stop

    # -----------------------------------------------------------------------
    # Send enabled gcode file to the CNC machine
    # -----------------------------------------------------------------------
    def sequenceStatus(self, message, error):
        self.setStatus(message)
        if error:
            self.workflow.confirmed.set(False)
            self.reportPlotterError('Tool sequence interrupted', message)

    def submitToolPass(self, commands):
        self.editor.selectClear()
        self.selectionChange()
        self.disable()
        self.sender.initRun()
        CNC.vars.update(running=True, errline='', _OvChanged=True)
        self.sender.submit_program(commands)
        self.canvas.clearSelection()

    def run(self):
        if self.sender.running:
            if self.sender._pause:
                self.sender.resume()
            else:
                self.reportPlotterError('Cut already running', 'Stop the current cut before starting another.')
            return
        reason = self.workflow.start_reason()
        if reason:
            self.reportPlotterError('Before cutting', reason)
            return
        try:
            stages = self.plotter.sequence()
            if stages:
                self.workflow.show_step(2)
                self.tool_sequence.begin(stages)
                self.workflow._cut_started = True
                self.workflow._stopped = False
                self.workflow.update_state()
                return
            prepared = self.plotter.prepare(use_material=True)
        except Exception as error:
            self.reportPlotterError('Cannot prepare cut', str(error))
            return
        self.editor.selectClear()
        self.selectionChange()
        self.disable()
        self.sender.initRun()
        self.sender._runLines = sys.maxsize
        CNC.vars.update(running=True, errline='', _OvChanged=True)
        try:
            from PlotterCompilation import compile_buffer
            commands = compile_buffer(prepared, self.checkStop)
            self.sender.submit_program(commands)
        except InterruptedError:
            self.sender.runEnded()
            self.enable()
            self.setStatus('Cut preparation cancelled')
            return
        except Exception as error:
            self.sender.emptyQueue()
            self.sender.runEnded()
            self.enable()
            self.reportPlotterError('Cannot prepare cut', str(error))
            return
        self.canvas.clearSelection()
        self.setStatus('Cutting…')


    # -----------------------------------------------------------------------
    # Inner loop to catch any generic exception
    # -----------------------------------------------------------------------
    def _monitorSerial(self):
        # Check serial output
        t = time.time()

        while not self.sender.log.empty() and time.time() - t < 0.1:
            try:
                msg, line = self.sender.log.get_nowait()
            except Empty:
                break
            self.diagnostic_log.record(msg, str(line).rstrip('\n'))
            mat_active = self.mat_handling.active
            if msg in (Sender.MSG_OK, Sender.MSG_RECEIVE, Sender.MSG_ERROR):
                self.mat_handling.receive(str(line).strip())
                self.tool_sequence.receive(str(line).strip())
            if msg == Sender.MSG_ERROR and not mat_active and hasattr(self, 'workflow'):
                self.workflow.report_error('Cut interrupted / command rejected', str(line))
            elif msg == Sender.MSG_RUNEND:
                self.setStatus(str(line))
                self.enable()

        self.mat_handling.tick()
        self.tool_sequence.tick()

        # Update position if needed
        if self.sender._posUpdate:
            state = CNC.vars["state"]
            try:
                CNC.vars["color"] = STATECOLOR[state]
            except KeyError:
                if self.sender._alarm:
                    CNC.vars["color"] = STATECOLOR["Alarm"]
                else:
                    CNC.vars["color"] = STATECOLORDEF
            self.sender._pause = "Hold" in state
            self.canvas.gantry(
                CNC.vars["wx"],
                CNC.vars["wy"],
                CNC.vars["wz"],
                CNC.vars["mx"],
                CNC.vars["my"],
                CNC.vars["mz"],
            )
            self.sender._posUpdate = False
        # Update status string
        if self.sender._gUpdate:
            self.sender._gUpdate = False

        self.sender._update = None

        if self.sender.running:
            CNC.vars["msg"] = f"{self.sender._gcount} / {self.sender._runLines} lines"

            if self.sender._gcount >= self.sender._runLines:
                self.sender.runEnded()
                self.tool_sequence.pass_finished()

    # -----------------------------------------------------------------------
    # "thread" timed function looking for messages in the serial thread
    # and reporting back in the terminal
    # -----------------------------------------------------------------------
    def monitorSerial(self):
        try:
            self._monitorSerial()
        except Exception:
            typ, val, tb = sys.exc_info()
            self.report_callback_exception(typ, val, tb)
        self.after(MONITOR_AFTER, self.monitorSerial)

    # -----------------------------------------------------------------------
    def get(self, section, item):
        return Utils.config.get(section, item)

    # -----------------------------------------------------------------------
    def set(self, section, item, value):
        return Utils.config.set(section, item, value)


if __name__ == "__main__":
    sys.stderr.write("ERROR: The program cannot be started from this file!\n")
    sys.stderr.write("\tPlease use __main__.py instead!\n")

    sys.exit()
