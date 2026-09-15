"""Shared, adaptive Tk presentation primitives. No machine commands live here."""
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

from PlotterTheme import BG, PANEL, INK, MUTED, ACCENT, SOFT

BORDER = '#c7d2d8'
FOCUS = '#245fc0'
DANGER = '#b42318'


@dataclass(frozen=True)
class Layout:
    compact: bool
    panel_width: int
    panel_height: int
    padding: int


def layout_for(width, height):
    """Logical window dimensions, not platform/device detection."""
    compact = width < 760
    return Layout(compact, min(340, max(280, width // 3)),
                  max(180, min(330, height // 2)), 12 if compact else 20)


def install_theme(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=PANEL, foreground=INK, font=('DejaVu Sans', 11))
    style.configure('TNotebook', background=PANEL, borderwidth=0)
    style.configure('TNotebook.Tab', padding=(12, 9))
    style.map('TNotebook.Tab', background=[('selected', SOFT)])
    style.configure('TCombobox', padding=8, fieldbackground=PANEL)
    style.configure('Foil.TCombobox', padding=8, fieldbackground=PANEL)
    style.map('Foil.TCombobox', fieldbackground=[('readonly', PANEL)])
    style.configure('TEntry', padding=8, fieldbackground=PANEL)
    style.configure('Treeview', rowheight=40, background=PANEL, fieldbackground=PANEL)
    style.map('Treeview', background=[('selected', SOFT)], foreground=[('selected', INK)])
    style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=BG,
                    borderwidth=0, thickness=8)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def polish(widget):
    """Consistent field boundaries and keyboard focus across existing editors."""
    for child in descendants(widget):
        if isinstance(child, ttk.Widget):
            continue
        if isinstance(child, tk.Entry):
            child.configure(relief='flat', bg=PANEL, fg=INK, insertbackground=INK,
                            highlightthickness=1, highlightbackground=BORDER,
                            highlightcolor=FOCUS)
        elif isinstance(child, tk.Listbox):
            child.configure(bg=BG, fg=INK, selectbackground=SOFT,
                            selectforeground=INK, highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=FOCUS)
        elif isinstance(child, tk.Checkbutton):
            child.configure(pady=8, anchor='w', justify='left', wraplength=260,
                            highlightcolor=FOCUS, takefocus=True, font=('DejaVu Sans', 11))
        elif isinstance(child, tk.Text):
            child.configure(highlightthickness=1, highlightbackground=BORDER,
                            highlightcolor=FOCUS, insertbackground=INK)


class SplitPanel:
    """Reflow sibling panes between columns and rows, retaining widget state."""
    def __init__(self, parent, first, second, threshold=700, first_height=190):
        self.parent, self.first, self.second = parent, first, second
        self.threshold, self.first_height = threshold, first_height
        self.mode = None
        self.binding = parent.bind('<Configure>', self.resize, add='+')

    def resize(self, event):
        if event.widget is not self.parent:
            return
        compact = event.width < self.threshold
        if compact == self.mode:
            return
        self.mode = compact
        for pane in (self.first, self.second):
            pane.pack_forget()
            pane.grid_forget()
        self.parent.columnconfigure(0, weight=1, minsize=0)
        self.parent.columnconfigure(1, weight=0, minsize=0)
        self.parent.rowconfigure(0, weight=0 if compact else 1, minsize=0)
        self.parent.rowconfigure(1, weight=1 if compact else 0, minsize=0)
        self.first.grid(row=0, column=0, sticky='nsew', padx=0 if compact else (0, 16))
        self.second.grid(row=1 if compact else 0, column=0 if compact else 1, sticky='nsew')
        if compact:
            self.parent.rowconfigure(0, minsize=self.first_height)
            self.first.configure(height=self.first_height)
            self.first.pack_propagate(False)
            self.first.grid_propagate(False)
        else:
            self.first.pack_propagate(True)
            self.first.grid_propagate(True)
            self.parent.columnconfigure(1, minsize=300)


def fit_dialog(dialog, app, width=900, height=680):
    """Keep every dialog within the application's available work area."""
    dialog.resizable(True, True)
    dialog.minsize(300, 400)
    w = min(width, max(320, app.winfo_width()), app.winfo_screenwidth())
    h = min(height, max(440, app.winfo_height()), app.winfo_screenheight() - 60)
    dialog.geometry(f'{w}x{h}+{max(0, app.winfo_rootx())}+{max(0, app.winfo_rooty())}')
    polish(dialog)
    if not hasattr(dialog, '_responsive_text'):
        dialog._responsive_text = ResponsiveText(dialog)


class ResponsiveText:
    """Wrap dialog copy to available width rather than clipping it on tablets."""
    def __init__(self, dialog):
        self.dialog = dialog
        self.width = None
        dialog.bind('<Configure>', self.resize, add='+')

    def resize(self, event):
        if event.widget is not self.dialog or event.width == self.width:
            return
        self.width = event.width
        for child in descendants(self.dialog):
            if isinstance(child, (tk.Label, tk.Checkbutton)) and not isinstance(child, ttk.Widget):
                parent_width = child.master.winfo_width()
                available = parent_width - 16 if parent_width > 10 else event.width - 48
                child.configure(wraplength=max(180, min(event.width - 48, available)))


class ScrollFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=PANEL, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg=PANEL, highlightthickness=0, width=1)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.bar = ttk.Scrollbar(self, command=self.canvas.yview)
        self.bar.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.body = tk.Frame(self.canvas, bg=PANEL)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', self.content_size)
        self.canvas.bind('<Configure>', self.viewport_size)

    def content_size(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def viewport_size(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
