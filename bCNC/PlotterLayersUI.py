"""Persistent layer/object manager backed by the headless layer service."""
import tkinter as tk
from PlotterUI import Field
from PlotterPages import WorkspacePage
from tkinter import ttk
from PlotterTheme import PANEL, BG, INK, MUTED, ACCENT
from PlotterLayers import LayerManager, catalog, signature, layer_name, DEFAULT

PALETTE = {'Teal':'#166c5e', 'Red':'#b23b3b', 'Blue':'#345bb1',
           'Gold':'#b47a12', 'Purple':'#7045a0', 'Charcoal':'#333333'}


class LayersDialog(WorkspacePage):
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
        self.context = tk.IntVar(self, 0)
        top = tk.Frame(self, bg=PANEL, padx=20, pady=8)
        top.pack(fill='x')
        from PlotterUI import ChoiceButton
        for index, name in reversed(list(enumerate(('Layer', 'Objects')))):
            ChoiceButton(top, text=name, variable=self.context, value=index,
                         command=lambda:self.controls.select(self.context.get())).pack(side='right', padx=3)
        title = workflow.label(top, 'Layers & objects', size=20, bold=True)
        title.config(wraplength=700); title.pack(side='left')
        subtitle = workflow.label(top, 'Choose what cuts and how.', muted=True)
        subtitle.config(wraplength=380); subtitle.pack(side='left', padx=20)
        footer = tk.Frame(self, bg=PANEL, padx=20, pady=8)
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
        self.scrollers = []
        list_shell = tk.Frame(body, bg=PANEL)
        list_shell.grid(row=0, column=0, sticky='nsew', padx=(0,16))
        left = list_shell
        tools = tk.Frame(left, bg=PANEL); tools.pack(fill='x', pady=(0,8))
        workflow.button(tools, '+ Layer', self.add_layer, primary=True).pack(side='right', padx=(8,0))
        workflow.label(tools, 'Find', size=10).pack(side='left', padx=(0,8))
        ttk.Entry(tools, textvariable=self.search, width=12).pack(side='left', fill='both', expand=True)
        selection = tk.Frame(left, bg=PANEL); selection.pack(side='bottom', fill='x', pady=(8,0))
        workflow.button_grid(selection, [('Select all', self.select_all), ('Select group', self.select_group)])
        holder = tk.Frame(left, bg=PANEL); holder.pack(fill='both', expand=True)
        holder.columnconfigure(0, weight=1); holder.rowconfigure(0, weight=1)
        style = ttk.Style(self)
        style.configure('FoilObjects.Treeview', rowheight=44, font=('DejaVu Sans',11), background=PANEL, fieldbackground=PANEL)
        style.configure('FoilObjects.Treeview.Heading', font=('DejaVu Sans',10,'bold'))
        self.tree = ttk.Treeview(holder, height=4, columns=('included','kind','passes'), selectmode='extended', style='FoilObjects.Treeview')
        self.tree.heading('#0', text='Layer / object')
        self.tree.column('#0', width=190, minwidth=110, stretch=True)
        for key, label, width in [('included','Cut',60),('kind','Type',82),('passes','Passes',65)]:
            self.tree.heading(key, text=label); self.tree.column(key, width=width, minwidth=width, stretch=False)
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.tree_bar = ttk.Scrollbar(holder, command=self.tree.yview)
        self.tree.configure(yscrollcommand=lambda first,last:self.scrollbar(self.tree_bar,first,last))
        self.detail_shell = tk.Frame(body, bg=PANEL)
        style.layout('LayerContext.TNotebook.Tab', [])
        self.controls = ttk.Notebook(self.detail_shell, style='LayerContext.TNotebook')
        self.controls.bind('<<NotebookTabChanged>>', lambda e:self.context.set(self.controls.index('current')))
        self.controls.pack(fill='both', expand=True)
        self.sections = {}
        for title in ('Layer', 'Objects'):
            group = ttk.Notebook(self.controls)
            self.controls.add(group, text=title)
            self.sections[title] = group
        setup = self.scroll_page('Cut setup', self.sections['Layer'])
        layer_style = self.scroll_page('Layer options', self.sections['Layer'])
        manage = self.scroll_page('Manage', self.sections['Layer'])
        pair = tk.Frame(setup, bg=PANEL); pair.pack(fill='x')
        pair.columnconfigure(0, weight=1, uniform='setup'); pair.columnconfigure(1, weight=1, uniform='setup')
        operation_box = tk.Frame(pair, bg=PANEL); operation_box.grid(row=0,column=0,sticky='ew',padx=(0,6))
        tool_box = tk.Frame(pair, bg=PANEL); tool_box.grid(row=0,column=1,sticky='ew',padx=(6,0))
        self.operation_combo = self.combo(operation_box, 'Operation', self.operation, ['Current settings','Cut','Draw'])
        self.operation_combo.bind('<<ComboboxSelected>>', lambda e:self.process_choices())
        self.tool_combo = self.combo(tool_box, 'Tool', self.tool_profile, [])
        self.material_combo = self.combo(setup, 'Material', self.material_profile, ['Current settings'])
        self.button(setup, 'Apply material & tool', self.apply_process)
        workflow.label(setup, 'Choose a layer on the left to set its material and tool.', size=10, muted=True).pack(fill='x', pady=4)
        self.action_field(layer_style, 'Layer color', self.color, self.color_layer, 'Apply', list(PALETTE))
        workflow.button_grid(layer_style, [('Include', lambda:self.show_layer(True)), ('Exclude', lambda:self.show_layer(False))])
        workflow.button_grid(layer_style, [('Only this layer', self.only_layer), ('Show all', self.show_all)])
        self.layer_rename, _ = self.action_field(manage, 'Layer name', self.layer, self.rename_layer, 'Rename')
        workflow.button_grid(layer_style, [('Move up', lambda:self.order_layer(-1)), ('Move down', lambda:self.order_layer(1))])
        self.combo(manage, 'When deleting', self.delete_mode, ['Keep objects in Default','Delete objects too'])
        self.layer_delete = self.button(manage, 'Delete layer', self.delete_layer)
        properties = self.scroll_page('Properties', self.sections['Objects'])
        arrange = self.scroll_page('Arrange', self.sections['Objects'])
        object_style = self.scroll_page('Appearance', self.sections['Objects'])
        self.action_field(properties, 'Object name', self.object_name, self.rename_object, 'Rename')
        _, self.target_combo = self.action_field(properties, 'Layer', self.target_layer, self.assign, 'Move', [DEFAULT])
        options = tk.Frame(properties, bg=PANEL); options.pack(fill='x', pady=(6,4))
        workflow.label(options, 'Passes', size=10).pack(side='left')
        ttk.Entry(options, textvariable=self.passes, width=5).pack(side='left', fill='y', padx=8)
        workflow.button(options, 'Apply', self.apply_passes).pack(side='right')
        workflow.button_grid(arrange, [('Include', lambda:self.include_objects(True)), ('Exclude', self.exclude)])
        workflow.button_grid(arrange, [('Move up', lambda:self.order_objects(-1)), ('Move down', lambda:self.order_objects(1))])
        workflow.button_grid(arrange, [('Duplicate', self.duplicate), ('Delete', self.delete_objects)])
        workflow.button_grid(arrange, [('Attach', self.attach), ('Detach', self.detach)])
        workflow.label(arrange, 'Drag objects in the list to reorder.', size=10, muted=True).pack(fill='x', pady=8)
        self.object_color_button, _ = self.action_field(object_style, 'Object color', self.object_color, self.color_objects, 'Apply', ['Layer color'] + list(PALETTE))
        workflow.label(object_style, 'Layer color follows the color of the containing layer.', size=10, muted=True).pack(fill='x', pady=8)
        self.tree.bind('<<TreeviewSelect>>', self.selected)
        self.tree.bind('<ButtonPress-1>', self.press, add='+')
        self.tree.bind('<ButtonRelease-1>', self.release, add='+')
        self.tree.bind('<Delete>', lambda e: self.delete_objects())
        self.bind('<Escape>', lambda e: self.destroy())
        self.search.trace_add('write', lambda *args: self.refresh(self.ids))
        self.refresh(self.ids)
        from PlotterUI import ListDetail
        self.adaptive_split = ListDetail(body, list_shell, self.detail_shell)
        body.bind('<Configure>', self.adapt_columns, add='+')
        self.tree.bind('<ButtonRelease-1>', lambda event: self.adaptive_split.show_detail() if self.tree.selection() else None, add='+')
        self.tree.bind('<Return>', lambda event: self.adaptive_split.show_detail(), add='+')
        self.grab_set()

    def adapt_columns(self, event):
        if event.widget is not self.adaptive_split.parent:
            return
        uniform = 'layers' if event.width >= 840 else ''
        event.widget.columnconfigure(0, uniform=uniform)
        event.widget.columnconfigure(1, uniform=uniform)
        self.tree.configure(displaycolumns=('included',) if event.width < 760 else ('included', 'kind', 'passes'))

    def scroll_page(self, title, notebook=None):
        notebook = notebook or self.controls
        holder = tk.Frame(notebook, bg=PANEL, width=1)
        notebook.add(holder, text=title)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        canvas = tk.Canvas(holder, bg=PANEL, highlightthickness=0, width=1, height=1)
        bar = ttk.Scrollbar(holder, command=canvas.yview)
        canvas.grid(row=0, column=0, sticky='nsew')
        canvas.configure(yscrollcommand=lambda first,last:self.scrollbar(bar,first,last))
        self.scrollers.append((canvas,bar))
        page = tk.Frame(canvas, bg=PANEL, padx=8, pady=4)
        window = canvas.create_window(0, 0, window=page, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        page.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        return page

    def scrollbar(self, bar, first, last):
        bar.set(first, last)
        needed = float(first) > 0.001 or float(last) < 0.999
        if needed and not bar.winfo_manager():
            bar.grid(row=0, column=1, sticky='ns')
        elif not needed and bar.winfo_manager():
            bar.grid_remove()

    def action_field(self, parent, label, variable, command, action, values=None):
        self.workflow.label(parent, label, size=10, bold=True).pack(anchor='w', pady=(4,3))
        row = tk.Frame(parent, bg=PANEL); row.pack(fill='x', pady=(0,4))
        button = self.workflow.button(row, action, command)
        button.pack(side='right', padx=(8,0))
        field = (ttk.Entry(row, textvariable=variable, width=10) if values is None else
                 ttk.Combobox(row, textvariable=variable, values=values, state='readonly', width=10))
        field.pack(side='left', fill='both', expand=True)
        return button, field

    def combo(self, parent, label, variable, values):
        self.workflow.label(parent, label, size=10, bold=True).pack(anchor='w', pady=(7,3))
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state='readonly', width=10, font=('DejaVu Sans',10))
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
        if event is not None and rows == getattr(self, '_last_rows', None): return
        self._last_rows = rows
        if event is not None and hasattr(self, 'adaptive_split'):
            self.adaptive_split.show_detail()
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
