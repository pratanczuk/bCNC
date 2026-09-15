"""Preview-first text and shape creation for the cutting workspace."""
import math
import os
from functools import lru_cache
import tkinter as tk
from PlotterUI import Field
from PlotterPages import WorkspacePage
from PlotterUI import ChoiceButton
from tkinter import filedialog, ttk

import Utils
from CNC import CNC
from bmath import Vector
from bpath import Path, Segment
from PlotterTheme import PANEL, BG, INK, MUTED, ACCENT


@lru_cache(maxsize=2048)
def font_name(path):
    try:
        from fontTools.ttLib import TTFont
        with TTFont(path, lazy=True) as font:
            names = font['name']
            family = names.getDebugName(16) or names.getDebugName(1)
            style = names.getDebugName(17) or names.getDebugName(2)
            if family:
                return family + (f' · {style}' if style else '')
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0].replace('_', ' ')


def positive(value, title):
    try:
        number = float(value)
        if not math.isfinite(number) or number <= 0 or number > 10000:
            raise ValueError()
        return number
    except ValueError:
        raise ValueError(f'{title}: enter a number greater than 0, up to 10000.') from None


def shape_paths(kind, width, height):
    width, height = positive(width, 'Width'), positive(height, 'Height')
    if kind == 'Rectangle':
        points = [(0, 0), (width, 0), (width, height), (0, height)]
    elif kind == 'Triangle':
        points = [(0, 0), (width, 0), (width / 2, height)]
    elif kind == 'Star':
        points = []
        for i in range(10):
            angle = math.pi / 2 + i * math.pi / 5
            radius = 1 if i % 2 == 0 else .45
            points.append((width / 2 * (1 + radius * math.cos(angle)),
                           height / 2 * (1 + radius * math.sin(angle))))
    elif kind in ('Circle', 'Ellipse'):
        if kind == 'Circle':
            height = width
        # Chord error <= 0.02 mm on the larger radius.
        count = max(32, math.ceil(math.pi / math.acos(max(-1, 1 - .02 / (max(width, height) / 2)))))
        count = 4 * math.ceil(count / 4)  # Include the four exact axis extrema.
        points = [(width / 2 * (1 + math.cos(i * 2 * math.pi / count)),
                   height / 2 * (1 + math.sin(i * 2 * math.pi / count))) for i in range(count)]
    else:
        raise ValueError('Choose a shape.')
    # Normalize all shapes to the requested outer dimensions.
    x0, y0 = min(x for x, y in points), min(y for x, y in points)
    dx, dy = max(x for x, y in points) - x0, max(y for x, y in points) - y0
    points = [Vector((x - x0) * width / dx, (y - y0) * height / dy) for x, y in points]
    path = Path(kind)
    for i, point in enumerate(points):
        path.append(Segment(Segment.LINE, point, points[(i + 1) % len(points)]))
    return [path]


def path_bounds(paths):
    boxes = [path.bbox() for path in paths if path]
    if not boxes:
        raise ValueError('No outlines to insert. Enter text and choose a font.')
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


class DesignDialog(WorkspacePage):
    def __init__(self, workflow, title):
        super().__init__(workflow.app)
        self.workflow, self.app = workflow, workflow.app
        self.configure(bg=PANEL)
        self.title(f'{title} · Foil Studio')
        self.geometry('900x650')
        self.minsize(760, 580)
        self.transient(self.app)
        self.pending = None
        self.paths = []
        self.message = tk.StringVar(self)
        top = tk.Frame(self, bg=PANEL, padx=24, pady=12)
        top.pack(fill='x')
        heading = workflow.label(top, title, size=20, bold=True)
        heading.config(wraplength=800)
        heading.pack(anchor='w')
        subtitle = workflow.label(top, 'Create, preview, then add to your mat.', muted=True)
        subtitle.config(wraplength=800)
        subtitle.pack(anchor='w', pady=(6, 0))
        bottom = tk.Frame(self, bg=PANEL, padx=24, pady=16)
        bottom.pack(side='bottom', fill='x')
        self.insert_button = workflow.button(bottom, 'Add to mat', self.insert, primary=True)
        self.insert_button.pack(side='right')
        self.cancel_button = workflow.button(bottom, 'Cancel', self.destroy)
        self.cancel_button.pack(side='right', padx=8)
        self.preview_error_detail = ''
        self.preview_error_title = 'Internal application error'
        self.error_button = workflow.button(bottom, 'Show details', self.show_error_details)
        body = tk.Frame(self, bg=PANEL, padx=24)
        body.pack(fill='both', expand=True)
        controls_shell = tk.Frame(body, bg=PANEL, width=310)
        controls_shell.pack(side='left', fill='y')
        controls_shell.grid_propagate(False)
        controls_shell.columnconfigure(0, weight=1)
        controls_shell.rowconfigure(0, weight=1)
        controls_canvas = tk.Canvas(controls_shell, bg=PANEL, width=1, highlightthickness=0)
        controls_canvas.grid(row=0, column=0, sticky='nsew')
        controls_bar = ttk.Scrollbar(controls_shell, command=controls_canvas.yview)
        controls_bar.grid(row=0, column=1, sticky='ns', padx=(5,0))
        controls_canvas.configure(yscrollcommand=controls_bar.set)
        self.controls = tk.Frame(controls_canvas, bg=PANEL)
        controls_window = controls_canvas.create_window(0,0,window=self.controls,anchor='nw')
        self.controls.bind('<Configure>', lambda e: controls_canvas.config(scrollregion=controls_canvas.bbox('all')))
        controls_canvas.bind('<Configure>', lambda e: controls_canvas.itemconfig(controls_window,width=e.width))
        def scroll_controls(event):
            direction = -1 if getattr(event,'num',None)==4 or getattr(event,'delta',0)>0 else 1
            controls_canvas.yview_scroll(direction*3,'units')
            return 'break'
        def bind_controls(widget):
            # Text/list widgets retain their own content scrolling.
            if not isinstance(widget,(tk.Text,tk.Listbox)):
                for event in ('<MouseWheel>','<Button-4>','<Button-5>'): widget.bind(event,scroll_controls)
            for child in widget.winfo_children(): bind_controls(child)
        self.controls_binding = self.after_idle(lambda: bind_controls(self.controls) if self.winfo_exists() else None)
        right = tk.Frame(body, bg=PANEL)
        right.pack(side='right', fill='both', expand=True, padx=(20, 0))
        workflow.label(right, 'CUT OUTLINE PREVIEW', muted=True).pack(anchor='w', pady=(0, 10))
        self.preview = tk.Canvas(right, bg=BG, highlightthickness=0)
        self.preview.pack(fill='both', expand=True)
        feedback_parent = self.controls
        feedback = tk.Label(feedback_parent, textvariable=self.message, bg=PANEL, fg=MUTED, wraplength=480,
                 justify='left', anchor='w')
        def show_feedback(*args):
            if self.message.get():
                first = next((c for c in feedback_parent.winfo_children() if c is not feedback and c.winfo_manager()), None)
                feedback.pack(fill='x', pady=4, before=first)
            else: feedback.pack_forget()
        self.message.trace_add('write', show_feedback)
        self.preview.bind('<Configure>', lambda event: self.draw_preview())
        from PlotterUI import SplitPanel
        self.adaptive_split = SplitPanel(body, right, controls_shell, threshold=840, first_height=220)
        self.bind('<Escape>', lambda event: self.destroy())
        self.grab_set()

    def field(self, title, value):
        self.workflow.label(self.controls, title, bold=True).pack(anchor='w', pady=(12, 6))
        variable = tk.StringVar(self, value)
        Field(self.controls, textvariable=variable, font=('DejaVu Sans', 12),
                 bg=BG, fg=INK, relief='flat').pack(fill='x')
        variable.trace_add('write', self.schedule)
        return variable

    def schedule(self, *args):
        if self.pending is not None:
            self.after_cancel(self.pending)
        self.pending = self.after(220, self.rebuild)

    def rebuild(self):
        if self.pending is not None:
            self.after_cancel(self.pending)
        self.pending = None
        self.error_button.pack_forget()
        try:
            self.paths = self.make_paths()
            x0, y0, x1, y1 = path_bounds(self.paths)
            self.message.set(f'{x1-x0:.1f} × {y1-y0:.1f} mm · {len(self.paths)} outlines')
            self.insert_button.config(state='normal')
        except Exception as error:
            self.paths = []
            self.show_inline_error(error)
            self.insert_button.config(state='disabled')
        self.draw_preview()

    def show_inline_error(self, error, title='Preview unavailable'):
        import traceback
        from PlotterErrors import friendly_error
        self.preview_error_title = title if isinstance(error, (ValueError, OSError, ImportError)) else 'Internal application error'
        self.preview_error_detail = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        if isinstance(error, ValueError):
            message = str(error)
            if message.startswith(('could not convert', 'invalid literal')):
                message = 'Check the settings: enter a valid number in each numeric field.'
        else:
            heading, guidance, _, _ = friendly_error(self.preview_error_title, self.preview_error_detail)
            message = f'{heading}. {guidance}'
        self.message.set(message)
        if not isinstance(error, ValueError):
            self.error_button.pack(side='top', fill='x', before=self.insert_button, pady=(0, 8))

    def show_error_details(self):
        from PlotterErrorDialog import show_modal_error
        show_modal_error(self.workflow, self, self.preview_error_title, self.preview_error_detail)

    def draw_preview(self):
        self.preview.delete('all')
        if not self.paths:
            return
        x0, y0, x1, y1 = path_bounds(self.paths)
        w, h = max(1, self.preview.winfo_width()), max(1, self.preview.winfo_height())
        margin = min(24, w/5, h/5)
        scale = min((w-2*margin)/max(x1-x0, .001), (h-2*margin)/max(y1-y0, .001))
        ox, oy = (w-(x1-x0)*scale)/2, (h-(y1-y0)*scale)/2
        for path in self.paths:
            path = path.linearize(.5)
            points = [seg.A for seg in path] + [path[-1].B]
            coords = [value for point in points for value in
                      (ox+(point[0]-x0)*scale, h-oy-(point[1]-y0)*scale)]
            self.preview.create_line(*coords, fill=ACCENT, width=2)

    def insert(self):
        if self.app.sender.running:
            return False
        self.rebuild()
        if not self.paths:
            return False
        x0, y0, x1, y1 = path_bounds(self.paths)
        margin = 10
        if x1-x0+margin > CNC.vars['mat_width'] or y1-y0+margin > CNC.vars['mat_height']:
            self.message.set('This design is too large for the mat. Reduce its dimensions before adding it.')
            return False
        paths = []
        for source in self.paths:
            path = Path(source.name)
            for seg in source:
                path.append(Segment(Segment.LINE, Vector(seg.A[0]-x0+margin, seg.A[1]-y0+margin),
                                    Vector(seg.B[0]-x0+margin, seg.B[1]-y0+margin)))
            paths.append(path)
        block = self.app.gcode.fromPath(paths, z=0)
        block._name = self.design_name()
        if hasattr(self, 'project_properties'):
            block.foil = self.project_properties()
            block.foil['matrix'] = [1, 0, 0, 1, margin-x0, margin-y0]
            block.foil['rendered'] = list(block)
        from PlotterEditing import contour_points
        block.foil['source_outlines'] = [contour_points(path) for path in self.paths]
        block.foil.setdefault('matrix', [1,0,0,1,margin-x0,margin-y0])
        block.foil['rendered'] = list(block)
        if not self.app.gcode.blocks:
            self.app.gcode.headerFooter()
        index = next((i for i, b in enumerate(self.app.gcode.blocks) if b.name() == 'Footer'), len(self.app.gcode.blocks))
        self.app.gcode.insBlocks(index, [block], 'Add ' + self.design_name())
        self.app.refresh()
        self.app.editor.select([(index, None)], clear=True)
        self.app.selectionChange()
        self.workflow.update_state()
        self.app.after_idle(self.workflow.fit_mat)
        self.destroy()
        return True

    def destroy(self):
        # Cancel owned idle work before Tk removes its registered command.
        # Otherwise a later widget may reuse the command name and receive it.
        self.after_cancel(self.controls_binding)
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
        super().destroy()


class ShapeDialog(DesignDialog):
    def __init__(self, workflow):
        super().__init__(workflow, 'Add a shape')
        self.kind = tk.StringVar(self, 'Rectangle')
        for label in ('Rectangle', 'Circle', 'Ellipse', 'Triangle', 'Star'):
            ChoiceButton(self.controls, text=label, value=label, variable=self.kind,
                indicatoron=False, bg=BG, selectcolor='#dfeee8', fg=INK, relief='flat',
                font=('DejaVu Sans', 12), pady=8, command=self.schedule).pack(fill='x', pady=3)
        self.width = self.field('Width / circle diameter · mm', '40')
        self.height = self.field('Height · mm (except circles)', '30')
        self.schedule()

    def make_paths(self):
        return shape_paths(self.kind.get(), self.width.get(), self.width.get() if self.kind.get() == 'Circle' else self.height.get())

    def design_name(self):
        return self.kind.get()


class TextDialog(DesignDialog):
    def __init__(self, workflow):
        super().__init__(workflow, 'Create lettering')
        from FontDiscovery import _font_files
        original_controls = self.controls
        tabs = ttk.Notebook(original_controls)
        tabs.pack(fill='both', expand=True)
        font_controls = tk.Frame(tabs, bg=PANEL)
        layout_controls = tk.Frame(tabs, bg=PANEL)
        tabs.add(font_controls, text='Text & font')
        tabs.add(layout_controls, text='Spacing')
        self.controls = layout_controls
        self.letter_spacing = self.field('Letter spacing · mm', '0')
        self.line_spacing = self.field('Line spacing · multiplier', '1.2')
        self.radius = self.field('Circle radius · mm (0 = straight)', '0')
        self.alignment = tk.StringVar(self, 'Left')
        workflow.label(self.controls, 'Align lines', bold=True).pack(anchor='w', pady=(12,6))
        align = ttk.Combobox(self.controls, textvariable=self.alignment, values=['Left','Center','Right'], state='readonly')
        align.pack(fill='x'); align.bind('<<ComboboxSelected>>', self.schedule)
        workflow.label(self.controls, 'Circular text uses one line. Letters retain their shapes. Unicode glyphs are supported when present in the font; complex-script shaping is not available.', muted=True).pack(fill='x', pady=12)
        self.controls = font_controls
        self.edit_id = None
        self.font_warning = ''
        self.fonts = _font_files()
        self.names = {path: font_name(path) for path in self.fonts}
        self.fonts.sort(key=lambda path: self.names[path].casefold())
        self.workflow.label(self.controls, 'Your text', bold=True).pack(anchor='w')
        self.text = tk.Text(self.controls, height=3, width=24, bg=BG, fg=INK, relief='flat',
                            font=('DejaVu Sans', 15), wrap='word', padx=10, pady=8)
        self.text.pack(fill='x', pady=(6, 0))
        self.text.insert('1.0', 'Made with love')
        self.text.bind('<<Modified>>', self.text_changed)
        self.height = self.field('Font size · mm (em height)', Utils.getStr('TextInsertion', 'height', '20'))
        self.search = self.field('Find a font', '')
        self.search.trace_add('write', self.filter_fonts)
        workflow.button(self.controls, 'Open font file…', self.browse).pack(side='bottom', fill='x', pady=6)
        font_frame = tk.Frame(self.controls, bg=PANEL)
        font_frame.pack(fill='both', expand=True, pady=(8, 0))
        self.font_list = tk.Listbox(font_frame, height=5, bg=BG, fg=INK, relief='flat',
                                   exportselection=False, selectbackground=ACCENT, font=('DejaVu Sans', 11))
        scrollbar = ttk.Scrollbar(font_frame, command=self.font_list.yview)
        scrollbar.pack(side='right', fill='y')
        self.font_list.config(yscrollcommand=scrollbar.set)
        self.font_list.pack(side='left', fill='both', expand=True)
        self.font_list.bind('<<ListboxSelect>>', self.schedule)
        self.filtered = []
        self.filter_fonts()
        saved = Utils.getStr('TextInsertion', 'font', '')
        if saved not in self.filtered:
            saved = next((p for p in self.filtered if os.path.basename(p) == 'DejaVuSans.ttf'), '')
        if saved in self.filtered:
            index = self.filtered.index(saved)
            self.font_list.selection_clear(0, 'end')
            self.font_list.selection_set(index)
            self.font_list.see(index)
        ids = list(self.app.editor.getSelectedBlocks())
        if len(ids) == 1:
            block = self.app.gcode.blocks[ids[0]]
            props = getattr(block, 'foil', {})
            if 'text' in props:
                self.edit_id = ids[0]
                self.original_block = block
                self.original_lines = list(block)
                self.original_properties = props.copy()
                spec = props['text']
                self.text.delete('1.0','end'); self.text.insert('1.0',spec['text'])
                self.height.set(spec['height'])
                self.letter_spacing.set(spec.get('letter_spacing',0))
                self.line_spacing.set(spec.get('line_spacing',1.2))
                self.radius.set(spec.get('radius',0))
                self.alignment.set(spec.get('alignment','Left'))
                font = spec['font']
                if font not in self.fonts and os.path.isfile(font):
                    self.fonts.append(font); self.names[font]=font_name(font); self.filter_fonts()
                if font in self.filtered:
                    self.font_list.selection_clear(0,'end'); self.font_list.selection_set(self.filtered.index(font))
                    self.font_list.see(self.filtered.index(font))
                else:
                    self.font_warning = 'Original font is missing. Choose a replacement; the saved outlines stay unchanged until Apply.'
                    workflow.label(layout_controls, self.font_warning, muted=True).pack(fill='x',pady=8)
                    workflow.label(font_controls, self.font_warning, muted=True).pack(fill='x',pady=8)
                self.insert_button.config(text='Update text')
                self.title('Edit lettering · Foil Studio')
        self.schedule()

    def text_changed(self, event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.schedule()

    def filter_fonts(self, *args):
        query = self.search.get().casefold()
        self.filtered = [p for p in self.fonts if query in self.names[p].casefold()]
        self.font_list.delete(0, 'end')
        for path in self.filtered:
            self.font_list.insert('end', self.names[path])
        if self.filtered:
            self.font_list.selection_set(0)
        self.schedule()

    def browse(self):
        path = filedialog.askopenfilename(parent=self, title='Open a font', filetypes=[('Fonts', '*.ttf *.otf')])
        if path:
            if path not in self.fonts:
                self.fonts.insert(0, path)
                self.names[path] = font_name(path)
            self.search.set('')
            index = self.filtered.index(path)
            self.font_list.selection_clear(0, 'end')
            self.font_list.selection_set(index)
            self.font_list.see(index)
            self.schedule()

    def make_paths(self):
        from font_text import text_to_paths
        selected = self.font_list.curselection()
        if not selected:
            raise ValueError('Choose a font, or open a TTF / OTF font file.')
        text = self.text.get('1.0', 'end-1c')
        if len(text) > 1000:
            raise ValueError('Use up to 1000 characters per text object.')
        return text_to_paths(text, self.filtered[selected[0]], positive(self.height.get(), 'Font size'),
                             letter_spacing=self.letter_spacing.get(), line_spacing=self.line_spacing.get(),
                             alignment=self.alignment.get(), radius=self.radius.get())

    def design_name(self):
        return 'Text: ' + self.text.get('1.0', 'end-1c').replace('\n', ' ')[:32]

    def project_properties(self):
        selected = self.font_list.curselection()
        return {'vector': True, 'text': {'text':self.text.get('1.0','end-1c'),
                'font':self.filtered[selected[0]], 'height':float(self.height.get()),
                'letter_spacing':float(self.letter_spacing.get()), 'line_spacing':float(self.line_spacing.get()),
                'alignment':self.alignment.get(), 'radius':float(self.radius.get())}}

    def insert(self):
        if self.app.sender.running: return False
        selected = self.font_list.curselection()
        font = self.filtered[selected[0]] if selected else ''
        height = self.height.get()
        if self.edit_id is None:
            success = super().insert()
        else:
            from copy import deepcopy
            from PlotterEditing import transform, fit, IDENTITY
            from PlotterProject import commit, changed_block
            i = self.edit_id
            if i >= len(self.app.gcode.blocks) or self.app.gcode.blocks[i] is not self.original_block or list(self.original_block)!=self.original_lines:
                self.message.set('The artwork changed. Reopen the text editor.'); return False
            if self.original_properties.get('rendered') != self.original_lines:
                self.message.set('This text was changed by a legacy outline tool. Create a new text object to avoid overwriting those edits.'); return False
            self.rebuild()
            if not self.paths: return False
            matrix = self.original_properties.get('matrix',IDENTITY)
            paths = transform(self.paths,matrix)
            try: fit([paths],CNC.vars['mat_width'],CNC.vars['mat_height'])
            except ValueError as error: self.message.set(str(error)); return False
            block = changed_block(self.app.gcode,self.original_block,paths)
            block._name=self.design_name()
            block.foil.update(self.project_properties()); block.foil['matrix']=matrix; block.foil['rendered']=list(block)
            blocks=list(self.app.gcode.blocks); blocks[i]=block
            commit(self.app.gcode,blocks,'Edit text')
            self.app.refresh(); self.workflow.confirmed.set(False); self.workflow.update_state(); self.destroy()
            success=True
        if success:
            Utils.addSection('TextInsertion')
            Utils.setStr('TextInsertion','font',font); Utils.setStr('TextInsertion','height',height)
        return success


class ArrangeDialog:
    def __new__(cls, workflow):
        from PlotterStudio import ArrangeDialog as Page
        return Page(workflow)


class CombineDialog(DesignDialog):
    def __init__(self, workflow):
        super().__init__(workflow, 'Combine shapes')
        from PlotterGeometry import OPERATIONS
        self.ids = [i for i in self.app.editor.getSelectedBlocks()
                    if self.app.gcode.blocks[i].name() not in ('Header', 'Footer')]
        self.original = [(i, self.app.gcode.blocks[i], list(self.app.gcode.blocks[i])) for i in self.ids]
        self.operation = tk.StringVar(self, 'Join / weld')
        self.valid = False
        descriptions = {
            'Join / weld': 'Merge overlapping areas into one shape.',
            'Subtract': 'Cut all other selected objects out of the first.',
            'Intersect': 'Keep only the area shared by every object.',
            'Exclude overlap': 'Keep areas covered an odd number of times.',
            'Combine outlines': 'One object; keep all paths and overlaps.',
        }
        for title in OPERATIONS:
            ChoiceButton(self.controls, text=title, value=title, variable=self.operation,
                indicatoron=False, bg=BG, selectcolor='#dfeee8', fg=INK, relief='flat',
                font=('DejaVu Sans', 12), pady=8, command=self.schedule).pack(fill='x', pady=3)
        self.explanation = tk.StringVar(self)
        self.descriptions = descriptions
        tk.Label(self.controls, textvariable=self.explanation, bg=PANEL, fg=MUTED,
                 wraplength=285, justify='left').pack(fill='x', pady=12)
        self.order = tk.StringVar(self)
        tk.Label(self.controls, textvariable=self.order, bg=PANEL, fg=INK,
                 wraplength=285, justify='left').pack(fill='x', pady=8)
        workflow.button(self.controls, 'Reverse object order', self.reverse).pack(fill='x')
        self.insert_button.config(text='Apply changes')
        self.schedule()

    def reverse(self):
        self.ids.reverse()
        self.schedule()

    def make_paths(self):
        from PlotterGeometry import combine_paths, OPERATIONS
        self.explanation.set(self.descriptions[self.operation.get()])
        names = [f'Object {i}: {self.app.gcode.blocks[i].name()}' for i in self.ids]
        self.order.set('Base: ' + names[0] + '\nOther objects: ' + ', '.join(names[1:]) if names else 'No objects selected')
        groups = [self.app.gcode.toPath(i) for i in self.ids]
        return combine_paths(groups, OPERATIONS[self.operation.get()])

    def rebuild(self):
        if self.pending is not None:
            self.after_cancel(self.pending)
        self.pending = None
        self.error_button.pack_forget()
        try:
            self.paths = self.make_paths()
            self.valid = True
            if self.paths:
                self.message.set(f'{len(self.paths)} result outlines. Replaces the selected objects; Undo restores them.')
            else:
                self.message.set('Empty result: applying will remove the selected objects. Undo restores them.')
            self.insert_button.config(state='normal')
        except Exception as error:
            self.paths = []
            self.valid = False
            self.show_inline_error(error)
            self.insert_button.config(state='disabled')
        self.draw_preview()

    def insert(self):
        if self.app.sender.running:
            return False
        if any(i >= len(self.app.gcode.blocks) or self.app.gcode.blocks[i] is not block
               or list(block) != lines for i, block, lines in self.original):
            self.message.set('The selection changed. Close this window and select the objects again.')
            return False
        self.rebuild()
        if not self.valid:
            return False
        block = self.app.gcode.fromPath(self.paths, z=0) if self.paths else None
        if block is not None:
            block._name = self.operation.get()
            base = self.app.gcode.blocks[self.ids[0]]
            block.enable, block.passes, block.color = base.enable, base.passes, base.color
            props = getattr(base,'foil',{})
            block.foil.update({key:props[key] for key in ('group','layer') if key in props})
        undo = [self.app.gcode.delBlockUndo(i) for i in sorted(self.ids, reverse=True)]
        index = min(self.ids)
        if block is not None:
            undo.append(self.app.gcode.insBlocksUndo(index, [block]))
        self.app.gcode.addUndo(undo, self.operation.get())
        self.app.refresh()
        self.app.editor.select([(index, None)] if block is not None else [], clear=True)
        self.app.selectionChange()
        self.workflow.update_state()
        self.destroy()
        return True


class OutlineDialog(DesignDialog):
    """Add offsets or a weeding rectangle without replacing the source artwork."""
    def __init__(self, workflow):
        super().__init__(workflow, 'Offset & weeding border')
        self.ids = [i for i in self.app.editor.getSelectedBlocks()
                    if self.app.gcode.blocks[i].name() not in ('Header', 'Footer')]
        self.original = [(i, self.app.gcode.blocks[i], list(self.app.gcode.blocks[i])) for i in self.ids]
        self.mode = tk.StringVar(self, 'Offset outline')
        for name in ('Offset outline', 'Weeding border'):
            ChoiceButton(self.controls, text=name, value=name, variable=self.mode,
                bg=PANEL, fg=INK, font=('DejaVu Sans', 12), command=self.schedule).pack(anchor='w', pady=8)
        self.distance = self.field('Distance / margin (mm)', '2')
        self.rounded = tk.BooleanVar(self, True)
        tk.Checkbutton(self.controls, text='Round offset corners', variable=self.rounded,
            bg=PANEL, fg=INK, command=self.schedule).pack(anchor='w', pady=12)
        workflow.label(self.controls, 'Positive offsets expand the design; negative offsets shrink it. A weeding border helps peel away excess foil. Original artwork stays in place.', muted=True).pack(fill='x', pady=12)
        self.insert_button.config(text='Add outlines')
        self.schedule()

    def make_paths(self):
        from PlotterGeometry import outline_effect
        return outline_effect([self.app.gcode.toPath(i) for i in self.ids], self.distance.get(),
                              self.mode.get() == 'Weeding border', self.rounded.get())

    def insert(self):
        if self.app.sender.running:
            return False
        if any(i >= len(self.app.gcode.blocks) or self.app.gcode.blocks[i] is not block
               or list(block) != lines for i, block, lines in self.original):
            self.message.set('The artwork changed. Close this window and select it again.')
            return False
        self.rebuild()
        if not self.paths:
            return False
        x0, y0, x1, y1 = path_bounds(self.paths)
        if x0 < 0 or y0 < 0 or x1 > CNC.vars['mat_width'] or y1 > CNC.vars['mat_height']:
            self.message.set('These outlines extend outside the mat. Move the artwork inward or reduce the distance.')
            return False
        block = self.app.gcode.fromPath(self.paths, z=0)
        block._name = self.mode.get()
        layers = {getattr(self.app.gcode.blocks[i],'foil',{}).get('layer','Default') for i in self.ids}
        if len(layers) != 1:
            self.message.set('Select artwork from one material layer for these outlines.'); return False
        block.foil['layer'] = layers.pop()
        block.color = self.app.gcode.blocks[self.ids[0]].color
        index = next((i for i, b in enumerate(self.app.gcode.blocks) if b.name() == 'Footer'), len(self.app.gcode.blocks))
        self.app.gcode.insBlocks(index, [block], 'Add ' + self.mode.get())
        self.app.refresh()
        self.app.editor.select([(index, None)], clear=True)
        self.app.selectionChange()
        self.workflow.confirmed.set(False)
        self.workflow.update_state()
        self.destroy()
        return True
