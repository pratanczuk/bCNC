"""Quick text-to-vector insertion dialog."""

import glob
import os
import sys
from tkinter import (
    BOTH, E, END, LEFT, NSEW, RIGHT, W, X, Y, Button, Canvas, Entry,
    Frame, Label, Listbox, Scrollbar, StringVar, Text, Toplevel, messagebox,
)
from tkinter import ttk

import Utils
import bFileDialog


def _font_files():
    roots = [
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    ]
    if sys.platform == "darwin":
        roots.extend(["/Library/Fonts", os.path.expanduser("~/Library/Fonts")])
    elif os.name == "nt":
        roots.append(os.path.join(os.environ.get("WINDIR", "C:\\Windows"),
                                  "Fonts"))

    fonts = []
    for root in roots:
        for extension in ("*.ttf", "*.otf", "*.TTF", "*.OTF"):
            fonts.extend(glob.glob(os.path.join(root, "**", extension),
                                   recursive=True))
    return sorted(set(fonts), key=lambda path: os.path.basename(path).lower())


class FontSelectorDialog(Toplevel):
    """Classic font list with a live outline preview."""

    def __init__(self, parent, current_font, on_select):
        super().__init__(parent)
        self.parent = parent
        self.on_select = on_select
        self.fonts = _font_files()
        if current_font and current_font not in self.fonts:
            self.fonts.insert(0, current_font)
        self.filtered = list(self.fonts)

        self.title(_("Select Font"))
        self.geometry("700x430")
        self.minsize(560, 350)
        self.transient(parent)

        body = Frame(self, padx=10, pady=10)
        body.pack(fill=BOTH, expand=True)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(1, weight=1)

        Label(body, text=_("Fonts:"), anchor=W).grid(
            row=0, column=0, sticky=W, pady=(0, 4)
        )
        self.filter_var = StringVar()
        filter_entry = Entry(body, textvariable=self.filter_var)
        filter_entry.grid(row=0, column=1, sticky=NSEW, padx=(8, 0), pady=(0, 4))
        self.filter_var.trace_add("write", self._filter_fonts)

        list_frame = Frame(body)
        list_frame.grid(row=1, column=0, sticky=NSEW)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.listbox = Listbox(list_frame, exportselection=False)
        self.listbox.grid(row=0, column=0, sticky=NSEW)
        scrollbar = Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        preview_frame = Frame(body, bd=1, relief="sunken")
        preview_frame.grid(row=1, column=1, sticky=NSEW, padx=(8, 0))
        preview_frame.rowconfigure(1, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.sample_var = StringVar(value="AaBbYyZz 0123")
        sample = Entry(preview_frame, textvariable=self.sample_var)
        sample.grid(row=0, column=0, sticky=NSEW, padx=6, pady=6)
        self.preview = Canvas(
            preview_frame, background="white", highlightthickness=0
        )
        self.preview.grid(row=1, column=0, sticky=NSEW)

        buttons = Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky=E, pady=(10, 0))
        Button(buttons, text=_("Browse..."), command=self._browse).pack(
            side=LEFT, padx=4
        )
        Button(buttons, text=_("Cancel"), command=self._close).pack(
            side=RIGHT, padx=4
        )
        Button(buttons, text=_("OK"), command=self._accept).pack(
            side=RIGHT, padx=4
        )

        self.listbox.bind("<<ListboxSelect>>", self._draw_preview)
        self.listbox.bind("<Double-Button-1>", lambda event: self._accept())
        self.sample_var.trace_add("write", self._draw_preview)
        self.preview.bind("<Configure>", self._draw_preview)
        self.bind("<Escape>", lambda event: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._populate(current_font)
        self.grab_set()
        filter_entry.focus_set()

    @staticmethod
    def _display_name(path):
        return os.path.splitext(os.path.basename(path))[0].replace("_", " ")

    def _populate(self, selected=None):
        self.listbox.delete(0, END)
        for path in self.filtered:
            self.listbox.insert(END, self._display_name(path))
        if not self.filtered:
            self.preview.delete("all")
            self.preview.create_text(
                15, 15, anchor="nw", text=_("No fonts found")
            )
            return
        try:
            index = self.filtered.index(selected)
        except ValueError:
            index = 0
        self.listbox.selection_set(index)
        self.listbox.activate(index)
        self.listbox.see(index)
        self._draw_preview()

    def _filter_fonts(self, *args):
        selected = self._selected_font()
        query = self.filter_var.get().strip().lower()
        self.filtered = [
            path for path in self.fonts
            if query in self._display_name(path).lower()
        ]
        self._populate(selected)

    def _selected_font(self):
        selection = self.listbox.curselection()
        if not selection or not self.filtered:
            return None
        return self.filtered[int(selection[0])]

    def _draw_preview(self, *args):
        font = self._selected_font()
        self.preview.delete("all")
        if not font:
            return
        try:
            from font_text import text_to_paths

            paths = text_to_paths(self.sample_var.get() or "Text", font, 100.0)
            points = [
                point
                for path in paths
                for segment in path
                for point in (segment.A, segment.B)
            ]
            if not points:
                return
            xmin = min(point[0] for point in points)
            xmax = max(point[0] for point in points)
            ymin = min(point[1] for point in points)
            ymax = max(point[1] for point in points)
            width = max(self.preview.winfo_width(), 100)
            height = max(self.preview.winfo_height(), 100)
            scale = min(
                (width - 24) / max(xmax - xmin, 1.0),
                (height - 24) / max(ymax - ymin, 1.0),
            )
            for path in paths:
                coordinates = []
                for segment in path:
                    coordinates.extend((
                        12 + (segment.A[0] - xmin) * scale,
                        height - 12 - (segment.A[1] - ymin) * scale,
                    ))
                if path:
                    coordinates.extend((
                        12 + (path[-1].B[0] - xmin) * scale,
                        height - 12 - (path[-1].B[1] - ymin) * scale,
                    ))
                if len(coordinates) >= 4:
                    self.preview.create_line(
                        *coordinates, fill="black", width=1, smooth=False
                    )
        except Exception as error:
            self.preview.create_text(
                15,
                15,
                anchor="nw",
                width=max(self.preview.winfo_width() - 30, 100),
                text=_("Preview unavailable:\n{} ").format(error),
            )

    def _browse(self):
        filename = bFileDialog.askopenfilename(
            master=self,
            title=_("Select a font"),
            filetypes=[(_("Font files"), ("*.ttf", "*.otf")), ("All", "*")],
        )
        if filename:
            if filename not in self.fonts:
                self.fonts.insert(0, filename)
            self.filtered = list(self.fonts)
            self.filter_var.set("")
            self._populate(filename)

    def _accept(self):
        font = self._selected_font()
        if font:
            self.on_select(font)
            self._close()

    def _close(self):
        self.grab_release()
        self.destroy()
        self.parent.grab_set()


class TextInsertionDialog(Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(_("Insert Text"))
        self.resizable(True, False)
        self.transient(app)

        frame = Frame(self, padx=12, pady=10)
        frame.pack(fill=BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        Label(frame, text=_("Text:"), anchor=W).grid(
            row=0, column=0, sticky=W, padx=(0, 8), pady=3
        )
        self.text = Text(frame, width=42, height=3, wrap="word")
        self.text.grid(row=0, column=1, columnspan=2, sticky=NSEW, pady=3)

        Label(frame, text=_("Font:"), anchor=W).grid(
            row=1, column=0, sticky=W, padx=(0, 8), pady=3
        )
        fonts = _font_files()
        saved_font = Utils.getStr("TextInsertion", "font", "")
        if saved_font and saved_font not in fonts and os.path.isfile(saved_font):
            fonts.insert(0, saved_font)
        self.font_var = StringVar(
            value=saved_font if os.path.isfile(saved_font)
            else (fonts[0] if fonts else "")
        )
        self.font = ttk.Combobox(
            frame, textvariable=self.font_var, values=fonts, width=48
        )
        self.font.grid(row=1, column=1, sticky=NSEW, pady=3)
        Button(frame, text=_("Choose..."), command=self._browse).grid(
            row=1, column=2, sticky=E, padx=(6, 0), pady=3
        )

        Label(frame, text=_("Height (mm):"), anchor=W).grid(
            row=2, column=0, sticky=W, padx=(0, 8), pady=3
        )
        self.height_var = StringVar(
            value=Utils.getStr("TextInsertion", "height", "10.0")
        )
        Entry(frame, textvariable=self.height_var, width=12).grid(
            row=2, column=1, sticky=W, pady=3
        )

        Label(frame, text=_("Depth (mm):"), anchor=W).grid(
            row=3, column=0, sticky=W, padx=(0, 8), pady=3
        )
        self.depth_var = StringVar(
            value=Utils.getStr("TextInsertion", "depth", "0.0")
        )
        Entry(frame, textvariable=self.depth_var, width=12).grid(
            row=3, column=1, sticky=W, pady=3
        )

        buttons = Frame(frame)
        buttons.grid(row=4, column=0, columnspan=3, sticky=E, pady=(10, 0))
        Button(buttons, text=_("Cancel"), command=self.destroy).pack(
            side=LEFT, padx=4
        )
        Button(buttons, text=_("Insert"), command=self._insert).pack(
            side=LEFT, padx=4
        )

        self.bind("<Escape>", lambda event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()
        self.text.focus_set()

    def _browse(self):
        FontSelectorDialog(self, self.font_var.get(), self.font_var.set)

    def _insert(self):
        text = self.text.get("1.0", END).rstrip("\n")
        font = self.font_var.get().strip()
        try:
            from font_text import text_to_paths

            height = float(self.height_var.get())
            depth = float(self.depth_var.get())
            if not os.path.isfile(font):
                raise ValueError(_("Select a valid TTF or OTF font file"))
            paths = text_to_paths(text, font, height)
            if not paths:
                raise ValueError(_("The text produced no vector outlines"))
        except ImportError as error:
            messagebox.showerror(
                _("Insert Text"),
                                _("Text insertion requires fontTools.\n"
                  "Install the project requirements, then restart bCNC.\n\n{}")
                .format(error),
                parent=self,
            )
            return
        except (OSError, ValueError) as error:
            messagebox.showerror(_("Insert Text"), str(error), parent=self)
            return
        except Exception as error:
            messagebox.showerror(
                _("Insert Text"),
                _("Unable to convert text to vectors:\n{} ").format(error),
                parent=self,
            )
            return

        block = self.app.gcode.fromPath(paths, z=depth)
        block._name = _("Text: {} ").format(text.replace("\n", " ")[:32]).strip()
        selected = self.app.editor.getSelectedBlocks()
        if selected:
            position = selected[-1] + 1
        else:
            position = next(
                (index for index, item in enumerate(self.app.gcode.blocks)
                 if item.name() == "Footer"),
                len(self.app.gcode.blocks),
            )
        self.app.gcode.addUndo(
            self.app.gcode.insBlocksUndo(position, [block]), _("Insert Text")
        )
        Utils.addSection("TextInsertion")
        Utils.setStr("TextInsertion", "font", font)
        Utils.setStr("TextInsertion", "height", str(height))
        Utils.setStr("TextInsertion", "depth", str(depth))
        self.app.refresh()
        self.app.setStatus(_("Inserted welded vector text"))
        self.destroy()


def show_text_insertion(app):
    TextInsertionDialog(app)
