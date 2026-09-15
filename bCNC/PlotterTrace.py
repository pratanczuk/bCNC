"""Foil Studio bitmap tracing with staged controls and outline preview."""
import os
import tkinter as tk
from PlotterUI import Field
from tkinter import filedialog, ttk

from PlotterDesign import DesignDialog, positive
from PlotterTheme import PANEL, BG, INK, MUTED, ACCENT


class TraceDialog(DesignDialog):
    MODES = {'Cut outlines': 'Contours', 'Multiple shades': 'Multi-threshold',
             'Centerlines': 'Centerline', 'Outer silhouette': 'Print then cut'}

    def __init__(self, workflow):
        super().__init__(workflow, 'Trace an image')
        self.geometry('900x700')
        self.minsize(820, 680)
        self.source = None
        self.filename = ''
        self.full_resolution = False
        self.photo = None
        self.mode = tk.StringVar(self, 'Cut outlines')
        self.view = tk.StringVar(self, 'Outline')
        self.invert = tk.BooleanVar(self, False)
        self.background = tk.BooleanVar(self, True)
        self.threshold = tk.DoubleVar(self, 128)
        self.file_label = workflow.label(self.controls, 'Choose a PNG, JPG or other bitmap.', muted=True)
        self.file_label.pack(fill='x', pady=(0, 8))
        workflow.button(self.controls, 'Choose image…', self.browse, primary=True).pack(fill='x')
        nav = tk.Frame(self.controls, bg=PANEL)
        nav.pack(fill='x', pady=10)
        self.basic = tk.Frame(self.controls, bg=PANEL)
        self.advanced = tk.Frame(self.controls, bg=PANEL)
        self.tabs = {}
        for title, page in [('Basics', self.basic), ('Refine', self.advanced)]:
            self.tabs[title] = workflow.button(nav, title, lambda page=page: self.show_page(page))
            self.tabs[title].pack(side='left', expand=True, fill='x', padx=2)
        self.settings = {}
        self.entry(self.basic, 'Longest image side · mm', 'size', '100')
        workflow.label(self.basic, 'Darkness threshold', bold=True).pack(anchor='w', pady=(12, 4))
        ttk.Scale(self.basic, from_=0, to=255, variable=self.threshold,
                  command=self.schedule).pack(fill='x', pady=6)
        self.threshold_label = workflow.label(self.basic, '', muted=True)
        self.threshold_label.pack(anchor='w')
        for title, var in [('Trace light areas instead', self.invert), ('Remove edge background', self.background)]:
            tk.Checkbutton(self.basic, text=title, variable=var, command=self.schedule,
                bg=PANEL, fg=INK, activebackground=PANEL, selectcolor=PANEL,
                font=('DejaVu Sans', 11), anchor='w').pack(fill='x', pady=6)
        workflow.label(self.basic, 'Use high-contrast artwork for cleaner cuts.', muted=True).pack(fill='x', pady=8)
        workflow.label(self.advanced, 'Tracing method', bold=True).pack(anchor='w')
        mode = ttk.Combobox(self.advanced, textvariable=self.mode, values=list(self.MODES),
                            state='readonly', style='Foil.TCombobox')
        mode.pack(fill='x', pady=6)
        mode.bind('<<ComboboxSelected>>', self.mode_changed)
        self.mode_rows = {}
        for label, key, value in [('Remove specks · px²', 'area', '16'),
                                  ('Smooth outlines · px', 'smooth', '1'),
                                  ('Background tolerance', 'tolerance', '24'),
                                  ('Shade levels', 'levels', '4'),
                                  ('Trim short branches · px', 'spur', '4'),
                                  ('Silhouette bleed · mm', 'bleed', '0')]:
            row = self.entry(self.advanced, label, key, value)
            if key in ('levels', 'spur', 'bleed'):
                self.mode_rows[key] = row
        views = tk.Frame(self.controls, bg=PANEL)
        views.pack(side='bottom', fill='x', pady=10)
        for title in ('Outline', 'Original'):
            tk.Radiobutton(views, text=title, variable=self.view, value=title,
                indicatoron=False, bg=BG, fg=INK, selectcolor='#dfeee8', relief='flat',
                font=('DejaVu Sans', 11), pady=8, command=self.draw_preview).pack(side='left', fill='x', expand=True)
        self.show_page(self.basic)
        self.mode_changed()
        self.insert_button.config(state='disabled')
        self.message.set('Choose an image to begin. Nothing is added until you select Add to mat.')

    def mode_changed(self, event=None):
        active = {'Multiple shades': 'levels', 'Centerlines': 'spur', 'Outer silhouette': 'bleed'}.get(self.mode.get())
        for key, row in self.mode_rows.items():
            row.pack_forget()
            if key == active:
                row.pack(fill='x', pady=6)
        self.schedule()

    def show_page(self, page):
        self.basic.pack_forget()
        self.advanced.pack_forget()
        page.pack(fill='both', expand=True)
        for title, button in self.tabs.items():
            button.config(bg='#dfeee8' if (title == 'Basics') == (page is self.basic) else BG)

    def entry(self, parent, label, key, default):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill='x', pady=6)
        self.workflow.label(row, label, size=10).pack(side='left')
        var = tk.StringVar(self, default)
        self.settings[key] = var
        Field(row, textvariable=var, width=6, font=('DejaVu Sans', 12),
                 bg=BG, fg=INK, relief='flat').pack(side='right', ipady=7)
        var.trace_add('write', self.schedule)
        return row

    def browse(self):
        filename = filedialog.askopenfilename(parent=self, title='Choose an image',
            filetypes=[('Images', '*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp')])
        if filename:
            self.load_image(filename)

    def load_image(self, filename):
        self.source = None
        self.paths = []
        self.insert_button.config(state='disabled')
        try:
            from PIL import Image
            with Image.open(filename) as image:
                self.source = image.convert('RGBA')
            self.filename = filename
            self.file_label.config(text=os.path.basename(filename))
            self.rebuild()
        except Exception as error:
            self.filename = ''
            self.file_label.config(text='Choose another image')
            self.show_inline_error(error, 'Cannot open image')
            self.draw_preview()

    def number(self, key, minimum=0, maximum=10000):
        import math
        value = float(self.settings[key].get())
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f'{key.capitalize()}: enter a value between {minimum} and {maximum}.')
        return value

    def make_paths(self):
        if self.source is None:
            raise ValueError('Choose an image to begin.')
        from PIL import Image
        from imagetrace import trace_image
        from bmath import Vector
        from bpath import Path, Segment
        maximum = positive(self.settings['size'].get(), 'Image size')
        width, height = self.source.size
        ratio = 1 if self.full_resolution else min(1, 760 / max(width, height))
        sample = self.source if ratio == 1 else self.source.resize(
            (max(1, round(width*ratio)), max(1, round(height*ratio))), Image.Resampling.LANCZOS)
        threshold = round(self.threshold.get())
        self.threshold_label.config(text=f'{threshold} / 255 · higher values include lighter pixels')
        scale = maximum / max(sample.size)
        records = trace_image(sample, mode=self.MODES[self.mode.get()], threshold=threshold,
            invert=self.invert.get(), remove_background=self.background.get(),
            tolerance=self.number('tolerance', 0, 255), minimum_area=self.number('area')*ratio**2,
            simplify=self.number('smooth', 0, 100)*ratio,
            levels=int(self.number('levels', 1, 32)) if self.mode.get() == 'Multiple shades' else 4,
            spur_length=int(self.number('spur', 0, 100)*ratio) if self.mode.get() == 'Centerlines' else 4,
            bleed_pixels=self.number('bleed', 0, 100)/scale if self.mode.get() == 'Outer silhouette' else 0)
        paths = []
        for name, pixels, closed in records:
            points = [Vector(x*scale, (sample.height-y)*scale) for x, y in pixels]
            if closed and points and points[0] != points[-1]:
                points.append(points[0])
            path = Path(name)
            for a, b in zip(points, points[1:]):
                if a != b:
                    path.append(Segment(Segment.LINE, a, b))
            if path:
                paths.append(path)
        if not paths:
            raise ValueError('No outlines found. Adjust the threshold or background removal.')
        return paths

    def rebuild(self):
        super().rebuild()
        if self.paths:
            self.message.set(f'{len(self.paths)} paths · preview may use a smaller image. Full-resolution tracing runs when added.'
                + (' Centerlines can be open paths.' if self.mode.get() == 'Centerlines' else '')
                + (' Silhouette only; no print registration.' if self.mode.get() == 'Outer silhouette' else ''))

    def draw_preview(self):
        if getattr(self, 'view', None) is None or self.view.get() == 'Outline' or self.source is None:
            return super().draw_preview()
        from PIL import Image, ImageTk
        image = self.source.copy()
        image.thumbnail((max(1, self.preview.winfo_width()-16), max(1, self.preview.winfo_height()-16)), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(image)
        self.preview.delete('all')
        self.preview.create_image(self.preview.winfo_width()/2, self.preview.winfo_height()/2, image=self.photo)

    def design_name(self):
        return 'Trace: ' + os.path.basename(self.filename)

    def insert(self):
        self.full_resolution = True
        try:
            return super().insert()
        finally:
            self.full_resolution = False
