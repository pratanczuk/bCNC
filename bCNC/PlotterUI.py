"""Shared, adaptive Tk presentation primitives. No machine commands live here."""
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk, font as tkfont
from PIL import Image, ImageDraw, ImageTk, ImageFont

from PlotterTheme import BG, PANEL, INK, MUTED, ACCENT, SOFT

BORDER = '#7a8993'
DIVIDER = '#d7dfe3'
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
    compact = width < 840
    return Layout(compact, 320 if width >= 840 else 300,
                  max(180, min(330, height // 2)), 16 if width < 600 else 24)


def install_theme(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=PANEL, foreground=INK, font=('DejaVu Sans', 11))
    style.configure('TNotebook', background=PANEL, borderwidth=0)
    style.configure('TNotebook.Tab', padding=(12, 14), borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', SOFT)])
    style.configure('TCombobox', padding=8, fieldbackground=PANEL)
    style.configure('Foil.TCombobox', padding=8, fieldbackground=PANEL)
    style.map('Foil.TCombobox', fieldbackground=[('readonly', PANEL)])
    style.configure('TEntry', padding=8, fieldbackground=PANEL)
    style.configure('Treeview', rowheight=48, background=PANEL, fieldbackground=PANEL)
    style.map('Treeview', background=[('selected', SOFT)], foreground=[('selected', INK)])
    rounded_fields(root)
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
            child.configure(pady=14, anchor='w', justify='left', wraplength=260,
                            highlightcolor=FOCUS, takefocus=True, font=('DejaVu Sans', 11),
                            borderwidth=0, relief='flat', selectcolor=SOFT, highlightbackground=PANEL)
        elif isinstance(child, tk.Text):
            child.configure(highlightthickness=1, highlightbackground=BORDER,
                            highlightcolor=FOCUS, insertbackground=INK)


class SplitPanel:
    """Reflow sibling panes between columns and rows, retaining widget state."""
    def __init__(self, parent, first, second, threshold=840, first_height=220):
        self.parent, self.first, self.second = parent, first, second
        self.threshold, self.first_height = threshold, first_height
        self.mode = None
        self.binding = parent.bind('<Configure>', self.resize, add='+')

    def resize(self, event):
        if event.widget is not self.parent:
            return
        compact = event.width < self.threshold
        if compact:
            preview_height = min(self.first_height, max(100, int(event.height * .42)))
            self.parent.rowconfigure(0, minsize=preview_height)
            self.first.configure(height=preview_height)
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
            self.parent.rowconfigure(0, minsize=preview_height)
            self.first.configure(height=preview_height)
            self.first.pack_propagate(False)
            self.first.grid_propagate(False)
        else:
            self.first.pack_propagate(True)
            self.first.grid_propagate(True)
            self.parent.columnconfigure(1, minsize=300)


def fit_dialog(dialog, app, width=900, height=680):
    """Keep every dialog within the application's available work area."""
    from PlotterPages import WorkspacePage
    if isinstance(dialog, WorkspacePage):
        if not hasattr(dialog, '_responsive_text'):
            polish(dialog)
            dialog._responsive_text = ResponsiveText(dialog)
            from PlotterAppearance import apply_appearance
            apply_appearance(app, scope=dialog)
        dialog.present()
        return
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
        self.pending = None
        self.parent_widths = {}
        dialog.bind('<Configure>', self.resize, add='+')
        parents = {child.master for child in descendants(dialog)
                   if isinstance(child, (tk.Label, tk.Checkbutton))}
        for parent in parents:
            parent.bind('<Configure>', self.queue_resize, add='+')
        dialog.bind('<Destroy>', self.cancel_resize, add='+')

    def queue_resize(self, event):
        if self.parent_widths.get(event.widget) == event.width:
            return
        self.parent_widths[event.widget] = event.width
        if self.pending is None:
            self.pending = self.dialog.after_idle(self.refresh)

    def refresh(self):
        self.pending = None
        self.resize(type('Size', (), dict(widget=self.dialog, width=self.dialog.winfo_width()))())

    def cancel_resize(self, event):
        if event.widget is self.dialog and self.pending is not None:
            self.dialog.after_cancel(self.pending)
            self.pending = None

    def resize(self, event):
        if event.widget is not self.dialog:
            return
        self.width = event.width
        for child in descendants(self.dialog):
            if isinstance(child, (tk.Label, tk.Checkbutton)) and not isinstance(child, ttk.Widget):
                parent_width = child.master.winfo_width()
                try:
                    inset = int(child.master.cget('padx')) * 2
                except (tk.TclError, ValueError):
                    inset = 0
                available = parent_width - inset - 16 if parent_width > 10 else event.width - 48
                child.configure(wraplength=max(80, min(event.width - 32, available)))


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


class RoundedButton(tk.Button):
    """Native keyboard/button behavior with a rounded, antialiased surface."""
    def __init__(self, parent, **options):
        self._surface = {}
        self._minimum_height = options.pop('minimum_height', 48)
        self._icon = None
        self._label = options.get('text', '')
        self._command = options.get('command')
        self._hover = self._focus = False
        self._image_key = None
        self._geometry_key = None
        self._ready = False
        for key in ('bg', 'activebackground', 'padx', 'pady', 'highlightcolor'):
            self._surface[key] = options.pop(key, dict(bg=BG, activebackground=SOFT,
                padx=12, pady=10, highlightcolor=FOCUS)[key])
        options.update(bg=parent.cget('bg'), activebackground=parent.cget('bg'),
                       padx=0, pady=0, highlightthickness=0, borderwidth=0,
                       compound='center', relief='flat', takefocus=True)
        super().__init__(parent, **options)
        self._disabled_cover = tk.Canvas(self, highlightthickness=0, borderwidth=0, takefocus=False)
        self._disabled_picture = self._disabled_cover.create_image(0, 0, anchor='nw')
        self._ready = True
        for event, callback in (('<Configure>', self._resize),
                                ('<Enter>', lambda e: self._interaction(hover=True)),
                                ('<Leave>', lambda e: self._interaction(hover=False)),
                                ('<FocusIn>', lambda e: self._interaction(focus=True)),
                                ('<FocusOut>', lambda e: self._interaction(focus=False))):
            self.bind(event, callback, add='+')
        self.bind('<Return>', lambda e: self.invoke())
        self.configure()

    def configure(self, cnf=None, **options):
        if not self._ready:
            return super().configure(cnf, **options)
        if isinstance(cnf, str):
            return super().configure(cnf)
        options = dict(cnf or {}, **options)
        if 'command' in options:
            if options['command'] == self._command:
                options.pop('command')
            else:
                self._command = options['command']
        # A Tk configure is not free: it schedules display/layout work, and
        # registering an unchanged Python command leaks another Tcl callback.
        stable = {'state', 'text', 'bg', 'fg', 'activebackground', 'disabledforeground'}
        if self._geometry_key is not None and self._image_key is not None and set(options) <= stable:
            if all(str(self.cget(key)) == str(value) for key, value in options.items()):
                return None
        if 'text' in options:
            self._label = options['text']
        if 'icon' in options:
            icon = options.pop('icon')
            if icon != self._icon:
                self._icon = icon
                self._geometry_key = None
        if self._icon:
            options['text'] = ''
        elif 'text' not in options:
            options['text'] = self._label
        if 'minimum_height' in options:
            height = options.pop('minimum_height')
            if height != self._minimum_height:
                self._minimum_height = height
                self._geometry_key = None
        if 'background' in options:
            options['bg'] = options.pop('background')
        for key in tuple(options):
            if key in self._surface:
                self._surface[key] = options.pop(key)
        # The image owns padding and outline; keep the native rectangular frame invisible.
        for key in ('highlightthickness', 'highlightbackground', 'bd', 'borderwidth', 'relief'):
            options.pop(key, None)
        options['bg'] = self.master.cget('bg')
        options['activebackground'] = self.master.cget('bg')
        result = super().configure(**options)
        geometry_key = (super().cget('text'), super().cget('font'),
                        self._surface['padx'], self._surface['pady'])
        if geometry_key != self._geometry_key:
            self._geometry_key = geometry_key
            root = self.winfo_toplevel()
            if not hasattr(root, '_button_fonts'):
                root._button_fonts = {}
                root._button_text_metrics = {}
            font_key = str(geometry_key[1])
            if font_key not in root._button_fonts:
                root._button_fonts[font_key] = tkfont.Font(root, font=geometry_key[1])
            font = root._button_fonts[font_key]
            lines = str(geometry_key[0]).split('\n')
            metric_key = (font_key, str(geometry_key[0]), self.tk.call('tk', 'scaling'))
            if len(root._button_text_metrics) >= 512:
                root._button_text_metrics.clear()
            if metric_key not in root._button_text_metrics:
                root._button_text_metrics[metric_key] = (max(font.measure(line) for line in lines),
                                                        font.metrics('linespace') * len(lines))
            text_width, text_height = root._button_text_metrics[metric_key]
            self._width = 46 if self._icon else text_width + 2 * int(self._surface['padx'])
            self._height = max(self._minimum_height - 2, text_height + 2 * int(self._surface['pady']))
            super().configure(width=self._width, height=self._height)
        self._paint(self.winfo_width() if self.winfo_width() > 1 else self._width,
                    self.winfo_height() if self.winfo_height() > 1 else self._height)
        return result

    config = configure

    def cget(self, key):
        if key == 'text':
            return self._label
        return self._surface[key] if key in self._surface else super().cget(key)

    __getitem__ = cget

    def _interaction(self, hover=None, focus=None):
        if hover is not None:
            self._hover = hover
        if focus is not None:
            self._focus = focus
        self._paint(self.winfo_width(), self.winfo_height())

    def _resize(self, event):
        self._paint(event.width, event.height)

    def _paint(self, width, height):
        width, height = max(1, width), max(1, height)
        disabled = super().cget('state') == 'disabled'
        fill = self._surface['activebackground' if self._hover and not disabled else 'bg']
        palette = getattr(self.winfo_toplevel(), '_palette', {})
        neutral = fill in (BG, PANEL, palette.get(BG), palette.get(PANEL))
        outline = self._surface['highlightcolor'] if self._focus else DIVIDER if neutral else fill
        fill = palette.get(fill, fill)
        outline = palette.get(outline, outline)
        if disabled:
            fill = palette.get(BG, BG)
            outline = palette.get(DIVIDER, DIVIDER)
        key = (width, height, fill, outline, self._icon, disabled, self._label, super().cget('font'))
        if key == self._image_key:
            return
        self._image_key = key
        image = Image.new('RGBA', (width * 2, height * 2))
        ImageDraw.Draw(image).rounded_rectangle((1, 1, width * 2 - 1, height * 2 - 1),
            radius=min(16, height - 1), fill=fill, outline=outline, width=4 if self._focus else 2)
        if disabled and not self._icon:
            # Keep native disabled semantics, but paint the complete disabled
            # surface in a child canvas to avoid Tk's compound-image stipple.
            metrics = tkfont.Font(self, font=super().cget('font'))
            size = max(12, round(metrics.metrics('linespace') * 1.6))
            face = 'DejaVuSans-Bold.ttf' if metrics.actual('weight') == 'bold' else 'DejaVuSans.ttf'
            try:
                font = ImageFont.truetype(face, size)
            except OSError:
                font = ImageFont.load_default()
            ink = palette.get(INK, INK)
            ImageDraw.Draw(image).multiline_text((width, height), self._label, font=font,
                fill=ink, anchor='mm', align='center', spacing=2)
        if self._icon:
            from PlotterIcons import paint
            paint(ImageDraw.Draw(image), self._icon, width-20, height-20, palette.get(INK, INK))
        self._background_image = ImageTk.PhotoImage(image.resize((width, height), Image.Resampling.LANCZOS), master=self)
        super().configure(image=self._background_image)
        if disabled:
            self._disabled_cover.configure(bg=self.master.cget('bg'))
            self._disabled_cover.itemconfigure(self._disabled_picture, image=self._background_image)
            self._disabled_cover.place(x=0, y=0, relwidth=1, relheight=1)
        else:
            self._disabled_cover.place_forget()


class ChoiceButton(RoundedButton):
    """Segment choice with a full touch target and explicit selected state."""
    def __init__(self, parent, **options):
        self.variable = options.pop('variable')
        self.value = options.pop('value')
        callback = options.pop('command', None)
        for key in ('indicatoron', 'selectcolor'):
            options.pop(key, None)
        super().__init__(parent, command=lambda: self.choose(callback), **options)
        self._trace = self.variable.trace_add('write', self.refresh_choice)
        self.bind('<Destroy>', self.release_trace, add='+')
        self.refresh_choice()

    def choose(self, callback):
        self.variable.set(self.value)
        if callback:
            callback()

    def refresh_choice(self, *args):
        self.configure(bg=SOFT if str(self.variable.get()) == str(self.value) else PANEL)

    def release_trace(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self._trace)


class ListDetail(SplitPanel):
    """One page at a time on compact screens; master/detail on desktop."""
    def __init__(self, parent, first, second, **kwargs):
        self.detail = False
        super().__init__(parent, first, second, threshold=840)
        self.back = RoundedButton(second, text='← Back to list', command=self.show_list)
        self.back.pack(side='top', fill='x', before=second.winfo_children()[0] if len(second.winfo_children()) > 1 else None)
        self.back.pack_forget()

    def resize(self, event):
        if event.widget is not self.parent:
            return
        self.mode = event.width < self.threshold
        for pane in (self.first, self.second):
            pane.pack_forget()
            pane.grid_forget()
        self.parent.rowconfigure(0, weight=1)
        self.parent.rowconfigure(1, weight=0, minsize=0)
        self.parent.columnconfigure(0, weight=1)
        self.parent.columnconfigure(1, weight=0 if self.mode else 1, minsize=0)
        if self.mode:
            (self.second if self.detail else self.first).grid(row=0, column=0, sticky='nsew')
            self.back.pack(side='top', fill='x', before=next((c for c in self.second.winfo_children() if c is not self.back), None))
        else:
            self.first.grid(row=0, column=0, sticky='nsew', padx=(0, 24))
            self.second.grid(row=0, column=1, sticky='nsew')
            self.back.pack_forget()

    def show_detail(self):
        self.detail = True
        self.resize(type('Size', (), dict(widget=self.parent, width=self.parent.winfo_width()))())

    def show_list(self):
        self.detail = False
        self.resize(type('Size', (), dict(widget=self.parent, width=self.parent.winfo_width()))())


class Field(ttk.Entry):
    """Shared rounded entry, retaining the legacy Tk entry call surface."""
    PRESENTATION = {'bg', 'fg', 'background', 'foreground', 'relief', 'bd', 'borderwidth',
                    'highlightthickness', 'highlightbackground', 'highlightcolor',
                    'insertbackground', 'selectbackground', 'selectforeground'}

    def __init__(self, parent, **options):
        self._presentation = {}
        for key in tuple(options):
            if key in self.PRESENTATION:
                self._presentation[key] = options.pop(key)
        super().__init__(parent, style='TEntry', **options)

    def configure(self, cnf=None, **options):
        if isinstance(cnf, str):
            return super().configure(cnf)
        options = dict(cnf or {}, **options)
        for key in tuple(options):
            if key in self.PRESENTATION:
                self._presentation[key] = options.pop(key)
        return super().configure(**options)

    config = configure

    def cget(self, key):
        if key in self.PRESENTATION:
            return self._presentation.get(key, '')
        return super().cget(key)

    __getitem__ = cget


def rounded_fields(root, surface=PANEL, border=BORDER, selected=SOFT, focus=FOCUS):
    """Nine-slice field surfaces scale without losing corner geometry."""
    style = ttk.Style(root)
    pictures = []
    for fill, edge in [(surface, border), (surface, focus), (selected, border)]:
        bitmap = Image.new('RGBA', (64, 48))
        ImageDraw.Draw(bitmap).rounded_rectangle((1, 1, 62, 46), radius=8, fill=fill, outline=edge, width=2 if edge == focus else 1)
        pictures.append(bitmap)
    if hasattr(root, '_rounded_fields'):
        for image, bitmap in zip(root._rounded_fields, pictures):
            image.paste(bitmap)
        return
    root._rounded_fields = [ImageTk.PhotoImage(p, master=root) for p in pictures]
    normal, focused, selection = root._rounded_fields
    style.element_create('Foil.field', 'image', normal, ('focus', focused), border=8, padding=8, sticky='nsew')
    style.layout('TEntry', [('Foil.field', {'sticky':'nsew','children':[('Entry.padding', {'sticky':'nsew','children':[('Entry.textarea', {'sticky':'nsew'})]})]})])
    combo = [('Foil.field', {'sticky':'nsew','children':[('Combobox.downarrow', {'side':'right','sticky':'ns'}),
             ('Combobox.padding', {'sticky':'nsew','children':[('Combobox.textarea', {'sticky':'nsew'})]})]})]
    style.layout('TCombobox', combo)
    style.layout('Foil.TCombobox', combo)
    style.element_create('Foil.tab', 'image', normal, ('selected', selection), border=8, padding=8, sticky='nsew')
    style.layout('TNotebook.Tab', [('Foil.tab', {'sticky':'nsew','children':[('Notebook.padding', {'side':'top','sticky':'nsew','children':[('Notebook.label', {'side':'top','sticky':''})]})]})])
