"""Interactive bitmap tracing dialog with a debounced live preview."""

import os
import tkinter as tk
from tkinter import ttk

import bFileDialog


IMAGE_TYPES = [
    (_("Bitmap images"), ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.tif", "*.tiff", "*.webp")),
    (_("All files"), "*"),
]


class ImageTraceDialog(tk.Toplevel):
    """Configure bitmap tracing while displaying the generated vectors."""

    PREVIEW_LIMIT = 760

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.tool = app.tools["ImageTrace"]
        self._source = None
        self._photo = None
        self._preview_after = None

        self.title(_("Trace Bitmap"))
        self.geometry("1080x700")
        self.minsize(820, 540)
        self.transient(app)

        self.vars = {
            "File": tk.StringVar(value=self.tool["File"] or ""),
            "Mode": tk.StringVar(value=self.tool["Mode"] or "Contours"),
            "Threshold": tk.IntVar(value=self._number("Threshold", 128, int)),
            "Thresholds": tk.IntVar(value=self._number("Thresholds", 4, int)),
            "Invert": tk.BooleanVar(value=bool(self.tool["Invert"])),
            "RemoveBackground": tk.BooleanVar(
                value=True if self.tool["RemoveBackground"] == ""
                else bool(self.tool["RemoveBackground"])
            ),
            "BackgroundTolerance": tk.IntVar(
                value=self._number("BackgroundTolerance", 24, int)
            ),
            "MinArea": tk.IntVar(value=self._number("MinArea", 16, int)),
            "Simplify": tk.DoubleVar(
                value=self._number("Simplify", 1.0, float)
            ),
            "SpurLength": tk.IntVar(
                value=self._number("SpurLength", 4, int)
            ),
            "MaxSize": tk.DoubleVar(
                value=self._number("MaxSize", 100.0, float)
            ),
            "Bleed": tk.DoubleVar(value=self._number("Bleed", 0.0, float)),
            "Depth": tk.DoubleVar(value=self._number("Depth", 0.0, float)),
        }

        self._build()
        for key, variable in self.vars.items():
            if key == "File":
                continue
            variable.trace_add("write", self._schedule_preview)
        self.vars["File"].trace_add("write", self._file_changed)
        self.canvas.bind("<Configure>", self._schedule_preview)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _event: self._close())

        filename = self.vars["File"].get()
        if filename and os.path.isfile(filename):
            self._load_image(filename)
        else:
            self.after_idle(self._browse)
        self.grab_set()

    def _number(self, key, default, converter):
        try:
            return converter(self.tool[key])
        except (TypeError, ValueError):
            return default

    def _build(self):
        body = ttk.Frame(self, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)

        files = ttk.Frame(body)
        files.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))
        files.columnconfigure(1, weight=1)
        ttk.Label(files, text=_("Image:"), width=12).grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Entry(files, textvariable=self.vars["File"]).grid(
            row=0, column=1, sticky=tk.EW, padx=6
        )
        ttk.Button(files, text=_("Browse..."), command=self._browse).grid(
            row=0, column=2
        )

        controls = ttk.LabelFrame(body, text=_("Trace settings"), padding=10)
        controls.grid(row=1, column=0, sticky=tk.NS, padx=(0, 10))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text=_("Mode:")).grid(
            row=0, column=0, sticky=tk.W, pady=3
        )
        ttk.Combobox(
            controls,
            textvariable=self.vars["Mode"],
            values=("Contours", "Multi-threshold", "Centerline", "Print then cut"),
            state="readonly",
            width=19,
        ).grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=3)

        ttk.Label(controls, text=_("Threshold:")).grid(
            row=1, column=0, sticky=tk.W, pady=3
        )
        ttk.Scale(
            controls,
            from_=0,
            to=255,
            variable=self.vars["Threshold"],
            orient=tk.HORIZONTAL,
        ).grid(row=1, column=1, sticky=tk.EW, pady=3)
        ttk.Label(controls, textvariable=self.vars["Threshold"], width=4).grid(
            row=1, column=2, sticky=tk.E
        )

        entries = (
            ("Thresholds", _("Threshold levels:")),
            ("BackgroundTolerance", _("Background tolerance:")),
            ("MinArea", _("Minimum area (px):")),
            ("Simplify", _("Smoothing (px):")),
            ("SpurLength", _("Spur removal (px):")),
            ("MaxSize", _("Output size (mm):")),
            ("Bleed", _("Cut bleed (mm):")),
            ("Depth", _("Working depth (mm):")),
        )
        for row, (key, label) in enumerate(entries, start=2):
            ttk.Label(controls, text=label).grid(
                row=row, column=0, sticky=tk.W, pady=3
            )
            ttk.Entry(controls, textvariable=self.vars[key], width=10).grid(
                row=row, column=1, columnspan=2, sticky=tk.EW, pady=3
            )

        ttk.Checkbutton(
            controls,
            text=_("Invert luminance"),
            variable=self.vars["Invert"],
        ).grid(row=10, column=0, columnspan=3, sticky=tk.W, pady=(8, 2))
        ttk.Checkbutton(
            controls,
            text=_("Automatically remove edge background"),
            variable=self.vars["RemoveBackground"],
        ).grid(row=11, column=0, columnspan=3, sticky=tk.W, pady=2)

        preview = ttk.LabelFrame(body, text=_("Live preview"), padding=4)
        preview.grid(row=1, column=1, sticky=tk.NSEW)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            preview, background="#30343b", highlightthickness=0
        )
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)

        footer = ttk.Frame(body)
        footer.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
        self.status = tk.StringVar(value=_("Select a bitmap to begin"))
        ttk.Label(footer, textvariable=self.status).pack(side=tk.LEFT)
        ttk.Button(footer, text=_("Cancel"), command=self._close).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        self.generate_button = ttk.Button(
            footer,
            text=_("Generate G-code"),
            command=self._generate,
            state=tk.DISABLED,
        )
        self.generate_button.pack(side=tk.RIGHT)

    def _browse(self):
        filename = bFileDialog.askopenfilename(
            master=self,
            title=_("Select bitmap image"),
            filetypes=IMAGE_TYPES,
        )
        if filename:
            self.vars["File"].set(filename)

    def _load_image(self, filename):
        try:
            from PIL import Image

            source = Image.open(filename)
            source.load()
            self._source = source.convert("RGBA")
            self.generate_button.config(state=tk.NORMAL)
            self._schedule_preview()
        except Exception as error:
            self._source = None
            self.generate_button.config(state=tk.DISABLED)
            self.status.set(_("Cannot load image: {}").format(error))

    def _file_changed(self, *args):
        filename = self.vars["File"].get()
        if os.path.isfile(filename):
            self._load_image(filename)

    def _schedule_preview(self, *args):
        if self._preview_after is not None:
            self.after_cancel(self._preview_after)
        self._preview_after = self.after(180, self._draw_preview)

    def _settings(self, preview_scale=1.0):
        return {
            "mode": self.vars["Mode"].get(),
            "threshold": max(0, min(255, int(self.vars["Threshold"].get()))),
            "levels": max(1, int(self.vars["Thresholds"].get())),
            "invert": bool(self.vars["Invert"].get()),
            "remove_background": bool(self.vars["RemoveBackground"].get()),
            "tolerance": max(0, int(self.vars["BackgroundTolerance"].get())),
            "minimum_area": max(
                0, float(self.vars["MinArea"].get()) * preview_scale ** 2
            ),
            "simplify": max(
                0.0, float(self.vars["Simplify"].get()) * preview_scale
            ),
            "spur_length": max(
                0, int(float(self.vars["SpurLength"].get()) * preview_scale)
            ),
        }

    def _draw_preview(self):
        self._preview_after = None
        self.canvas.delete("all")
        if self._source is None:
            return
        try:
            from PIL import Image, ImageTk
            from imagetrace import trace_image

            width, height = self._source.size
            source_scale = min(
                1.0, self.PREVIEW_LIMIT / float(max(width, height))
            )
            resampling = getattr(Image, "Resampling", Image)
            if source_scale < 1.0:
                preview = self._source.resize(
                    (
                        max(1, int(width * source_scale)),
                        max(1, int(height * source_scale)),
                    ),
                    resampling.LANCZOS,
                )
            else:
                preview = self._source.copy()

            settings = self._settings(source_scale)
            maximum = max(0.001, float(self.vars["MaxSize"].get()))
            output_scale = maximum / max(width, height)
            settings["bleed_pixels"] = (
                max(0.0, float(self.vars["Bleed"].get()))
                / output_scale
                * source_scale
            )
            records = trace_image(preview, **settings)

            canvas_w = max(self.canvas.winfo_width(), 100)
            canvas_h = max(self.canvas.winfo_height(), 100)
            display_scale = min(
                (canvas_w - 24) / preview.width,
                (canvas_h - 24) / preview.height,
            )
            display_w = max(1, int(preview.width * display_scale))
            display_h = max(1, int(preview.height * display_scale))
            shown = preview.resize((display_w, display_h), resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(shown)
            offset_x = (canvas_w - display_w) / 2.0
            offset_y = (canvas_h - display_h) / 2.0
            self.canvas.create_image(
                offset_x, offset_y, anchor=tk.NW, image=self._photo
            )
            self.canvas.create_rectangle(
                offset_x,
                offset_y,
                offset_x + display_w,
                offset_y + display_h,
                outline="#7d8794",
            )

            colors = ("#ff3355", "#00c8ff", "#ffd43b", "#65e572", "#d783ff")
            for index, (_name, points, closed) in enumerate(records):
                coordinates = []
                for x, y in points:
                    coordinates.extend(
                        (offset_x + x * display_scale,
                         offset_y + y * display_scale)
                    )
                if closed and points:
                    coordinates.extend(
                        (offset_x + points[0][0] * display_scale,
                         offset_y + points[0][1] * display_scale)
                    )
                if len(coordinates) >= 4:
                    self.canvas.create_line(
                        *coordinates,
                        fill=colors[index % len(colors)],
                        width=2,
                        smooth=False,
                    )
            self.status.set(
                _("{} × {} pixels — {} vector path(s)").format(
                    width, height, len(records)
                )
            )
        except (ValueError, tk.TclError):
            self.status.set(_("Enter valid numeric settings"))
        except Exception as error:
            self.status.set(_("Preview unavailable: {}").format(error))

    def _generate(self):
        if self._source is None:
            return
        try:
            if float(self.vars["MaxSize"].get()) <= 0:
                raise ValueError(_("Output size must be positive"))
            for key, variable in self.vars.items():
                self.tool[key] = variable.get()
            self.tool.execute(self.app)
        except (ValueError, tk.TclError) as error:
            self.status.set(str(error) or _("Enter valid numeric settings"))
            return
        self._close()

    def _close(self):
        if self._preview_after is not None:
            self.after_cancel(self._preview_after)
            self._preview_after = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def show_image_trace(app):
    return ImageTraceDialog(app)
