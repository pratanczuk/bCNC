# Copyright and User License
# ~~~~~~~~~~~~~~~~~~~~~~~~~~
# Copyright Vasilis.Vlachoudis@cern.ch for the
# European Organization for Nuclear Research (CERN)
#
# Please consult the flair documentation for the license
#
# DISCLAIMER
# ~~~~~~~~~~
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT
# NOT LIMITED TO, IMPLIED WARRANTIES OF MERCHANTABILITY, OF
# SATISFACTORY QUALITY, AND FITNESS FOR A PARTICULAR PURPOSE
# OR USE ARE DISCLAIMED. THE COPYRIGHT HOLDERS AND THE
# AUTHORS MAKE NO REPRESENTATION THAT THE SOFTWARE AND
# MODIFICATIONS THEREOF, WILL NOT INFRINGE ANY PATENT,
# COPYRIGHT, TRADE SECRET OR OTHER PROPRIETARY RIGHT.
#
# LIMITATION OF LIABILITY
# ~~~~~~~~~~~~~~~~~~~~~~~
# THE COPYRIGHT HOLDERS AND THE AUTHORS SHALL HAVE NO
# LIABILITY FOR DIRECT, INDIRECT, SPECIAL, INCIDENTAL,
# CONSEQUENTIAL, EXEMPLARY, OR PUNITIVE DAMAGES OF ANY
# CHARACTER INCLUDING, WITHOUT LIMITATION, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES, LOSS OF USE, DATA OR PROFITS,
# OR BUSINESS INTERRUPTION, HOWEVER CAUSED AND ON ANY THEORY
# OF CONTRACT, WARRANTY, TORT (INCLUDING NEGLIGENCE), PRODUCT
# LIABILITY OR OTHERWISE, ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
#
# Author: Vasilis Vlachoudis
#  Email: Vasilis.Vlachoudis@cern.ch
#   Date: 12-Oct-2006

"""Shared Tk event, clipboard and tooltip helpers used by the plotter UI."""
from tkinter import TclError, END, Event, Toplevel, Message, SOLID

GLOBAL_CONTROL_BACKGROUND = "White"

def bindEventData(widget, sequence, func, add=None):
    def _substitute(*args):
        e = Event()
        nsign, b, t, T, d, W = args
        try:
            e.serial = int(nsign)
        except Exception:
            e.serial = nsign
        try:
            e.num = int(b)
        except Exception:
            e.num = b
        try:
            e.time = int(t)
        except Exception:
            e.time = t
        e.type = T
        e.data = d
        try:
            e.widget = widget._nametowidget(W)
        except KeyError:
            e.widget = W
        return (e,)

    funcid = widget._register(func, _substitute, needcleanup=1)
    cmd = '{0}if {{"[{1} %# %b %t %T %d %W]" == "break"}} break\n'.format(
        "+" if add else "", funcid
    )
    widget.tk.call("bind", widget._w, sequence, cmd)

def _entryPaste(event):
    """global replacement for the Entry.paste"""
    try:
        event.widget.delete("sel.first", "sel.last")
    except TclError:
        pass  # nothing is selected

    # in tk.call() use the widget's string representation event.widget._w
    # instead of event.widget, which is the widget instance itself
    try:
        text = event.widget.tk.call(
            "::tk::GetSelection", event.widget._w, "CLIPBOARD")
    except TclError:
        return
    event.widget.insert("insert", text)
    event.widget.tk.call("tk::EntrySeeInsert", event.widget._w)
    return "break"

def _textPaste(event):
    """global replacement for the Text.paste"""
    oldSeparator = event.widget.cget("autoseparators")
    if oldSeparator:
        event.widget.config(autoseparators=0)
        event.widget.edit_separator()
    try:
        event.widget.delete("sel.first", "sel.last")
    except TclError:
        pass  # nothing is selected

    # in tk.call() use the widget's string representation event.widget._w
    # instead of event.widget, which is the widget instance itself
    try:
        text = event.widget.tk.call(
            "::tk::GetSelection", event.widget._w, "CLIPBOARD")
    except TclError:
        return
    event.widget.insert("insert", text)
    if oldSeparator:
        event.widget.edit_separator()
        event.widget.config(autoseparators=1)
    event.widget.see("insert")
    return "break"

def bindClasses(root):
    root.bind_class(
        "Entry", "<Control-Key-a>", lambda e: e.widget.selection_range(0, END)
    )
    root.bind_class("Entry", "<<Paste>>", _entryPaste)
    root.bind_class("Text", "<<Paste>>", _textPaste)

class Balloon:
    _top = None
    _widget = None
    font = ("Helvetica", "-12")
    foreground = "Black"
    background = "LightYellow"
    delay = 1500
    x_mouse = 0
    y_mouse = 0

    # ----------------------------------------------------------------------
    # set a balloon message to a widget
    # ----------------------------------------------------------------------
    @staticmethod
    def set(widget, help):  # noqa: A002
        widget._help = help
        widget.bind("<Any-Enter>", Balloon.enter)
        widget.bind("<Any-Leave>", Balloon.leave)
        widget.bind("<Key>", Balloon.hide)

    # ----------------------------------------------------------------------
    @staticmethod
    def enter(event):
        if Balloon._widget is event.widget:
            return
        Balloon._widget = event.widget
        Balloon.x_mouse = event.x_root
        Balloon.y_mouse = event.y_root
        return event.widget.after(Balloon.delay, Balloon.show)

    # ----------------------------------------------------------------------
    @staticmethod
    def leave(event=None):
        Balloon._widget = None
        if Balloon._top is None:
            return
        try:
            if Balloon._top.winfo_ismapped():
                Balloon._top.withdraw()
        except TclError:
            Balloon._top = None

    hide = leave

    # ----------------------------------------------------------------------

    # ----------------------------------------------------------------------
    @staticmethod
    def show():
        try:
            if Balloon._widget is None:
                return
            widget = Balloon._widget
            if Balloon._top is None:
                Balloon._top = Toplevel()
                Balloon._top.overrideredirect(1)
                Balloon._msg = Message(
                    Balloon._top,
                    aspect=300,
                    foreground=Balloon.foreground,
                    background=Balloon.background,
                    relief=SOLID,
                    borderwidth=1,
                    font=Balloon.font,
                )
                Balloon._msg.pack()
                Balloon._top.bind("<1>", Balloon.hide)
            Balloon._msg.config(text=widget._help)
            # Guess position
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() + widget.winfo_height() + 5
            # if too far away use mouse
            if abs(x - Balloon.x_mouse) > 30:
                x = Balloon.x_mouse + 20
            if abs(y - Balloon.y_mouse) > 30:
                y = Balloon.y_mouse + 10
            Balloon._top.wm_geometry(f"+{int(x)}+{int(y)}")
            Balloon._top.deiconify()
            Balloon._top.lift()
            Balloon._top.update_idletasks()

            # Check if it is hidden on bottom-right sides
            move = False
            if (
                Balloon._top.winfo_rootx() + Balloon._top.winfo_width()
                >= Balloon._top.winfo_screenwidth()
            ):
                x = Balloon._top.winfo_screenwidth() - \
                    Balloon._top.winfo_width() - 20
                move = True
            if (
                Balloon._top.winfo_rooty() + Balloon._top.winfo_height()
                >= Balloon._top.winfo_screenheight()
            ):
                y = Balloon._top.winfo_screenheight() - \
                    Balloon._top.winfo_height() - 10
                move = True
            if move:
                Balloon._top.wm_geometry(f"+{int(x)}+{int(y)}")

        except TclError:
            Balloon._top = None
