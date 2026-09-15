"""Persistent layer/object manager backed by the headless layer service."""
import tkinter as tk
from tkinter import ttk
from PlotterTheme import PANEL, BG, INK, MUTED, ACCENT
from PlotterLayers import LayerManager, catalog, signature, layer_name, DEFAULT

PALETTE = {'Teal':'#166c5e', 'Red':'#b23b3b', 'Blue':'#345bb1',
           'Gold':'#b47a12', 'Purple':'#7045a0', 'Charcoal':'#333333'}


class LayersDialog(tk.Toplevel):
    def __init__(self, workflow):
        super().__init__(workflow.app)
        self.workflow, self.app = workflow, workflow.app
        self.manager = LayerManager(self.app.gcode, lambda: self.app.sender.running)
        self.title('Layers & objects · Foil Studio')
        self.configure(bg=PANEL)
        self.geometry('960x690')
        self.minsize(880, 620)
        self.transient(self.app)
        self.ids = list(self.app.editor.getSelectedBlocks())
        self.layer_rows = {}
        self.pending_drag = None
        self.refreshing = False
        self.message = tk.StringVar(self)
        self.search = tk.StringVar(self)
        self.layer = tk.StringVar(self, DEFAULT)
        self.color = tk.StringVar(self, 'Teal')
        self.object_name = tk.StringVar(self)
        self.target_layer = tk.StringVar(self, DEFAULT)
        self.passes = tk.StringVar(self, '1')
        self.object_color = tk.StringVar(self, 'Layer color')
        self.operation = tk.StringVar(self, 'Current settings')
        self.tool_profile = tk.StringVar(self)
        self.material_profile = tk.StringVar(self, 'Current settings')
        self.saved_process = None
        self.delete_mode = tk.StringVar(self, 'Keep objects in Default')
        top = tk.Frame(self, bg=PANEL, padx=20, pady=16)
        top.pack(fill='x')
        title = workflow.label(top, 'Layers & objects', size=20, bold=True)
        title.config(wraplength=700); title.pack(anchor='w')
        subtitle = workflow.label(top, 'Organize artwork, choose what cuts, and keep changes undoable.', muted=True)
        subtitle.config(wraplength=800); subtitle.pack(anchor='w', pady=(4,0))
        footer = tk.Frame(self, bg=PANEL, padx=20, pady=12)
        footer.pack(side='bottom', fill='x')
        self.insert_button = workflow.button(footer, 'Done', self.destroy, primary=True)
        self.insert_button.pack(side='right')
        workflow.button(footer, 'Undo', lambda: self.history(False)).pack(side='left')
        workflow.button(footer, 'Redo', lambda: self.history(True)).pack(side='left', padx=6)
        tk.Label(footer, textvariable=self.message, bg=PANEL, fg=MUTED, wraplength=590,
                 justify='left', anchor='w').pack(side='left', fill='x', expand=True, padx=12)
        body = tk.Frame(self, bg=PANEL, padx=20)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=310)
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=PANEL)
        left.grid(row=0, column=0, sticky='nsew', padx=(0,16))
        tools = tk.Frame(left, bg=PANEL); tools.pack(fill='x', pady=(0,8))
        workflow.button(tools, '+ Add layer', self.add_layer, primary=True).pack(side='right', padx=(8,0))
        search = ttk.Entry(tools, textvariable=self.search, font=('DejaVu Sans',11))
        search.pack(side='left', fill='x', expand=True, ipady=8)
        search.insert(0, '')
        workflow.label(left, 'Search layers or objects · Ctrl/Shift selects several', size=10, muted=True).pack(anchor='w')
        holder = tk.Frame(left, bg=PANEL); holder.pack(fill='both', expand=True, pady=6)
        holder.columnconfigure(0, weight=1); holder.rowconfigure(0, weight=1)
        style = ttk.Style(self)
        style.configure('FoilObjects.Treeview', rowheight=31, font=('DejaVu Sans',11), background=PANEL, fieldbackground=PANEL)
        style.configure('FoilObjects.Treeview.Heading', font=('DejaVu Sans',10,'bold'))
        self.tree = ttk.Treeview(holder, columns=('included','kind','passes'), selectmode='extended', style='FoilObjects.Treeview')
        self.tree.heading('#0', text='Layer / object')
        self.tree.column('#0', width=220, minwidth=120, stretch=True)
        for key, label, width in [('included','Cut',75),('kind','Type',92),('passes','Passes',55)]:
            self.tree.heading(key, text=label); self.tree.column(key, width=width, minwidth=width, stretch=False)
        self.tree.grid(row=0, column=0, sticky='nsew')
        bar = ttk.Scrollbar(holder, command=self.tree.yview); bar.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=bar.set)
        workflow.button_grid(left, [('Select all objects', self.select_all), ('Select attached group', self.select_group)])
        hint = workflow.label(left, 'Drag objects onto a layer, or before another object. Moving and duplicating includes attached group members.', size=10, muted=True)
        hint.config(wraplength=530); hint.pack(fill='x', pady=8)
        self.controls = ttk.Notebook(body)
        self.controls.grid(row=0, column=1, sticky='nsew')
        layer_page = self.scroll_page('Layer')
        object_page = self.scroll_page('Objects')
        self.entry(layer_page, 'Layer name', self.layer)
        self.layer_rename = self.button(layer_page, 'Rename layer', self.rename_layer)
        self.operation_combo = self.combo(layer_page, 'Operation', self.operation, ['Current settings','Cut','Draw'])
        self.operation_combo.bind('<<ComboboxSelected>>', lambda e:self.process_choices())
        self.tool_combo = self.combo(layer_page, 'Tool', self.tool_profile, [])
        self.material_combo = self.combo(layer_page, 'Material', self.material_profile, ['Current settings'])
        self.button(layer_page, 'Apply material & tool', self.apply_process)
        self.workflow.label(layer_page, 'Draw uses a pen, with compensation and overcut always off. Library edits do not change this layer until applied again.', muted=True, size=10).pack(fill='x',pady=6)
        self.combo(layer_page, 'Layer color', self.color, list(PALETTE))
        self.button(layer_page, 'Apply layer color', self.color_layer)
        workflow.button_grid(layer_page, [('Include', lambda: self.show_layer(True)), ('Exclude', lambda: self.show_layer(False))])
        workflow.button_grid(layer_page, [('Only this layer', self.only_layer), ('All layers', self.show_all)])
        workflow.button_grid(layer_page, [('Move layer up', lambda: self.order_layer(-1)), ('Move down', lambda: self.order_layer(1))])
        self.combo(layer_page, 'When deleting this layer', self.delete_mode, ['Keep objects in Default','Delete objects too'])
        self.layer_delete = self.button(layer_page, 'Delete layer', self.delete_layer)
        note = workflow.label(layer_page, 'Default holds unassigned artwork and cannot be renamed or deleted. Excluding a layer preserves each object’s own cut setting.', size=10, muted=True)
        note.config(wraplength=285); note.pack(fill='x', pady=8)
        self.entry(object_page, 'Object name (one selected)', self.object_name)
        self.button(object_page, 'Rename object', self.rename_object)
        self.target_combo = self.combo(object_page, 'Move selected objects to', self.target_layer, [DEFAULT])
        self.button(object_page, 'Move to layer', self.assign)
        options = tk.Frame(object_page, bg=PANEL); options.pack(fill='x', pady=(8,4))
        workflow.label(options, 'Cut passes', size=10).pack(side='left')
        ttk.Spinbox(options, from_=1, to=100, textvariable=self.passes, width=5).pack(side='left', padx=8)
        workflow.button(options, 'Apply', self.apply_passes).pack(side='right')
        workflow.button_grid(object_page, [('Include objects', lambda: self.include_objects(True)), ('Exclude', self.exclude)])
        workflow.button_grid(object_page, [('Move up', lambda: self.order_objects(-1)), ('Move down', lambda: self.order_objects(1))])
        workflow.button_grid(object_page, [('Duplicate', self.duplicate), ('Delete objects', self.delete_objects)])
        workflow.button_grid(object_page, [('Attach', self.attach), ('Detach', self.detach)])
        self.combo(object_page, 'Object color', self.object_color, ['Layer color'] + list(PALETTE))
        self.button(object_page, 'Apply object color', self.color_objects)
        for page in (layer_page, object_page):
            self.compact_buttons(page)
        self.tree.bind('<<TreeviewSelect>>', self.selected)
        self.tree.bind('<ButtonPress-1>', self.press, add='+')
        self.tree.bind('<ButtonRelease-1>', self.release, add='+')
        self.tree.bind('<Delete>', lambda e: self.delete_objects())
        self.bind('<Escape>', lambda e: self.destroy())
        self.search.trace_add('write', lambda *args: self.refresh(self.ids))
        self.refresh(self.ids)
        self.grab_set()

    def scroll_page(self, title):
        holder = tk.Frame(self.controls, bg=PANEL, width=330)
        self.controls.add(holder, text=title)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        canvas = tk.Canvas(holder, bg=PANEL, highlightthickness=0, width=310)
        bar = ttk.Scrollbar(holder, command=canvas.yview)
        canvas.grid(row=0, column=0, sticky='nsew')
        bar.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=bar.set)
        page = tk.Frame(canvas, bg=PANEL, padx=8, pady=4)
        window = canvas.create_window(0, 0, window=page, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        page.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        return page

    def compact_buttons(self, parent):
        for child in parent.winfo_children():
            if isinstance(child, tk.Button):
                child.configure(pady=4, font=('DejaVu Sans', 10))
            self.compact_buttons(child)

    def entry(self, parent, label, variable):
        self.workflow.label(parent, label, size=10, bold=True).pack(anchor='w', pady=(4,3))
        ttk.Entry(parent, textvariable=variable, font=('DejaVu Sans',11)).pack(fill='x', ipady=5)

    def combo(self, parent, label, variable, values):
        self.workflow.label(parent, label, size=10, bold=True).pack(anchor='w', pady=(7,3))
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state='readonly', font=('DejaVu Sans',10))
        combo.pack(fill='x', ipady=3)
        return combo

    def button(self, parent, label, command):
        button = self.workflow.button(parent, label, command)
        button.pack(fill='x', pady=4)
        return button

    def refresh(self, selection=None):
        self.refreshing = True
        self.tree.delete(*self.tree.get_children())
        self.layer_rows = {}
        layers = catalog(self.app.gcode)
        query = self.search.get().casefold().strip()
        for n, layer in enumerate(layers):
            name = layer['name']
            children = [(i,b) for i,b in enumerate(self.app.gcode.blocks)
                        if b.name() not in ('Header','Footer') and layer_name(b).casefold() == name.casefold()]
            shown = [(i,b) for i,b in children if not query or query in name.casefold() or query in b.name().casefold()]
            if query and not shown and query not in name.casefold():
                continue
            row = f'layer:{n}'
            self.layer_rows[row] = name
            self.tree.insert('', 'end', iid=row, text=f'{name}  ({len(children)})', open=True,
                             values=('Yes' if layer['enabled'] else 'No',layer.get('process', {}).get('operation', 'Layer'),''))
            for i,b in shown:
                kind = 'Text' if 'text' in b.foil else 'Outline'
                if b.foil.get('group'): kind += ' · group'
                state = 'Yes' if b.enable else ('Layer off' if b.foil.get('object_enabled',b.enable) else 'No')
                self.tree.insert(row, 'end', iid=f'object:{i}', text=b.name(), values=(state,kind,b.passes))
        self.target_combo.configure(values=[layer['name'] for layer in layers])
        if self.target_layer.get() not in [layer['name'] for layer in layers]:
            self.target_layer.set(DEFAULT)
        rows = []
        if isinstance(selection, str):
            rows = [row for row,name in self.layer_rows.items() if name == selection]
        elif selection:
            rows = [f'object:{i}' for i in selection if self.tree.exists(f'object:{i}')]
        if not rows and self.tree.get_children(): rows = [self.tree.get_children()[0]]
        self.tree.selection_set(rows)
        if rows: self.tree.focus(rows[0]); self.tree.see(rows[0])
        self.expected = signature(self.app.gcode)
        self.refreshing = False
        self.selected()

    def selected(self, event=None):
        if self.refreshing: return
        rows = self.tree.selection()
        self.ids = [int(row.split(':')[1]) for row in rows if row.startswith('object:')]
        layer_rows = [row for row in rows if row in self.layer_rows]
        if layer_rows:
            name = self.layer_rows[layer_rows[0]]
        elif self.ids:
            name = layer_name(self.app.gcode.blocks[self.ids[0]])
        else:
            return
        self.selected_layer = name
        self.layer.set(name)
        info = next(layer for layer in catalog(self.app.gcode) if layer['name'].casefold() == name.casefold())
        self.saved_process = info.get('process')
        self.operation.set(self.saved_process['operation'] if self.saved_process else 'Current settings')
        self.tool_profile.set(self.saved_process['tool']['name'] if self.saved_process else '')
        self.material_profile.set(self.saved_process['material']['name'] if self.saved_process and self.saved_process['material'] else 'Current settings')
        self.process_choices()
        self.color.set(next((label for label,color in PALETTE.items() if color == info['color']), 'Teal'))
        self.layer_rename.config(state='disabled' if name == DEFAULT else 'normal')
        self.layer_delete.config(state='disabled' if name == DEFAULT else 'normal')
        if len(self.ids) == 1:
            block = self.app.gcode.blocks[self.ids[0]]
            self.object_name.set(block.name()); self.passes.set(str(block.passes))
            self.object_color.set(next((label for label,color in PALETTE.items() if color == block.color), 'Layer color') if block.foil.get('color_override') else 'Layer color')
        else:
            self.object_name.set('')
        if self.ids:
            self.controls.select(1)
            self.app.editor.select([(i,None) for i in self.ids], clear=True)
            self.app.selectionChange()
        elif layer_rows:
            self.controls.select(0)
        self.message.set(f'{len(self.ids)} objects selected' if self.ids else f'Layer: {name}')

    def perform(self, operation):
        if signature(self.app.gcode) != self.expected:
            self.refresh()
            self.message.set('The design changed. The list was refreshed; select the objects again.')
            return False
        try:
            result = operation()
            self.workflow.confirmed.set(False)
            self.app.refresh(); self.workflow.update_state()
            self.refresh(result)
            self.message.set('Applied. Undo restores the previous state.')
            return True
        except ValueError as error:
            self.message.set(str(error))
            return False

    def add_layer(self, name=None):
        if name is None:
            used = {layer['name'].casefold() for layer in catalog(self.app.gcode)}
            n = 1
            while f'layer {n}' in used: n += 1
            name = f'Layer {n}'
        return self.perform(lambda: self.manager.add(name))

    def rename_layer(self):
        return self.perform(lambda: self.manager.rename_layer(self.selected_layer, self.layer.get()))

    def delete_layer(self):
        return self.perform(lambda: self.manager.delete_layer(self.selected_layer, self.delete_mode.get() == 'Delete objects too'))

    def color_layer(self):
        return self.perform(lambda: self.manager.layer_properties(self.selected_layer, color=PALETTE[self.color.get()]))

    def show_layer(self, enabled):
        return self.perform(lambda: self.manager.layer_properties(self.selected_layer, enabled=enabled))

    def only_layer(self):
        return self.perform(lambda: self.manager.layer_properties(self.selected_layer, only=True))

    def show_all(self):
        return self.perform(self.manager.show_all)

    def order_layer(self, direction):
        return self.perform(lambda: self.manager.order_layer(self.selected_layer, direction))

    def rename_object(self):
        return self.perform(lambda: self.manager.object_properties(self.ids, name=self.object_name.get()))

    def assign(self):
        return self.perform(lambda: self.manager.move(self.ids, self.target_layer.get()))

    def include_objects(self, enabled):
        return self.perform(lambda: self.manager.object_properties(self.ids, enabled=enabled))

    def exclude(self):
        return self.include_objects(False)

    def process_choices(self):
        operation = self.operation.get()
        kind = 'Pen' if operation=='Draw' else 'Knife'
        library = self.workflow.library.records
        tools = [name for name, profile in library['tools'].items() if profile['kind']==kind]
        materials = [name for name, profile in library['materials'].items() if profile['compatible'] in ('Both',kind)]
        if self.saved_process:
            saved = self.saved_process
            if saved['tool']['kind']==kind and saved['tool']['name'] not in tools:
                tools.append(saved['tool']['name'])
            if saved['material'] and saved['material']['compatible'] in ('Both',kind) and saved['material']['name'] not in materials:
                materials.append(saved['material']['name'])
        self.tool_combo.configure(values=sorted(tools), state='disabled' if operation=='Current settings' else 'readonly')
        self.material_combo.configure(values=['Current settings']+sorted(materials), state='disabled' if operation=='Current settings' else 'readonly')
        if self.tool_profile.get() not in tools: self.tool_profile.set(tools[0] if tools else '')
        if self.material_profile.get() not in materials: self.material_profile.set('Current settings')

    def apply_process(self):
        def apply():
            process = None
            if self.operation.get() != 'Current settings':
                library = self.workflow.library.records
                tool = library['tools'].get(self.tool_profile.get())
                material = library['materials'].get(self.material_profile.get())
                if self.saved_process:
                    if tool is None and self.tool_profile.get()==self.saved_process['tool']['name']:
                        tool = self.saved_process['tool']
                    saved_material = self.saved_process['material']
                    if material is None and saved_material and self.material_profile.get()==saved_material['name']:
                        material = saved_material
                process = {'operation':self.operation.get(), 'tool':tool, 'material':material}
            return self.manager.set_process(self.selected_layer, process)
        return self.perform(apply)

    def apply_passes(self):
        return self.perform(lambda: self.manager.object_properties(self.ids, passes=self.passes.get()))

    def color_objects(self):
        color = 'layer' if self.object_color.get() == 'Layer color' else PALETTE[self.object_color.get()]
        return self.perform(lambda: self.manager.object_properties(self.ids, color=color))

    def duplicate(self):
        return self.perform(lambda: self.manager.duplicate(self.ids))

    def delete_objects(self):
        return self.perform(lambda: self.manager.delete_objects(self.ids))

    def order_objects(self, direction):
        return self.perform(lambda: self.manager.order_objects(self.ids, direction))

    def attach(self):
        return self.perform(lambda: self.manager.group(self.ids))

    def detach(self):
        return self.perform(lambda: self.manager.group(self.ids, False))

    def history(self, redo):
        if self.app.sender.running:
            self.message.set('Wait until the cut finishes before editing.')
            return False
        self.app.redo() if redo else self.app.undo()
        self.refresh()
        self.workflow.confirmed.set(False)
        return True

    def select_all(self):
        self.tree.selection_set([row for layer in self.tree.get_children() for row in self.tree.get_children(layer)])
        self.selected()

    def select_group(self):
        ids = self.workflow.expand_groups(self.ids)
        self.tree.selection_set([f'object:{i}' for i in ids if self.tree.exists(f'object:{i}')])
        self.selected()

    def press(self, event):
        row = self.tree.identify_row(event.y)
        self.pending_drag = (event.x, event.y, row)

    def release(self, event):
        pending, self.pending_drag = self.pending_drag, None
        if pending is None or abs(pending[0]-event.x)+abs(pending[1]-event.y) < 8:
            return
        source = pending[2]
        target = self.tree.identify_row(event.y)
        if not source.startswith('object:') or not target:
            return
        ids = self.ids if int(source.split(':')[1]) in self.ids else [int(source.split(':')[1])]
        if target in self.layer_rows:
            self.perform(lambda: self.manager.move(ids, self.layer_rows[target]))
        elif target.startswith('object:'):
            before = int(target.split(':')[1])
            self.perform(lambda: self.manager.move(ids, layer_name(self.app.gcode.blocks[before]), before))
