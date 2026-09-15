"""Material and tool library editor. Edits never send machine commands."""
import tkinter as tk
from PlotterUI import Field
from PlotterPages import WorkspacePage
from tkinter import ttk, messagebox, colorchooser
from PlotterTheme import PANEL, INK, MUTED
from PlotterLibrary import validate_profile


class LibraryDialog(WorkspacePage):
    def __init__(self, workflow):
        super().__init__(workflow.app)
        self.workflow = workflow
        self.library = workflow.library
        self.title('Materials & tools · Foil Studio')
        self.geometry('900x710'); self.minsize(800, 630)
        self.configure(bg=PANEL); self.transient(workflow.app)
        self.message = tk.StringVar(self)
        self.forms, self.lists, self.selected_names, self.widgets, self.rows = {}, {}, {}, {}, {}
        self.searches = {}
        self.details = {}
        top = tk.Frame(self, bg=PANEL, padx=20, pady=14); top.pack(fill='x')
        title = workflow.label(top, 'Materials & tools', size=20, bold=True)
        title.configure(wraplength=750); title.pack(anchor='w')
        subtitle = workflow.label(top, 'Save tested setups. Assign them to layers in Layers & objects.', muted=True)
        subtitle.configure(wraplength=750); subtitle.pack(anchor='w', pady=(6,0))
        bottom = tk.Frame(self, bg=PANEL, padx=20, pady=12); bottom.pack(side='bottom', fill='x')
        workflow.button(bottom, 'Done', self.destroy, primary=True).pack(side='bottom', anchor='e')
        tk.Label(bottom, textvariable=self.message, wraplength=620, justify='left', anchor='w', bg=PANEL, fg=INK).pack(side='top', fill='x')
        book = ttk.Notebook(self); book.pack(fill='both', expand=True, padx=20)
        definitions = {
            'materials': [('name','Name',None),('speed','Speed · mm/min',None),('pressure','Pressure · 0–1000 PWM',None),
                          ('thickness','Thickness · mm (reference)',None),('passes','Passes',None),
                          ('compatible','Compatible tools',('Both','Knife','Pen')),('notes','Notes',None)],
            'tools': [('name','Name',None),('kind','Tool type',('Knife','Pen')),('angle','Blade angle · degrees (reference)',None),
                      ('offset','Blade offset · mm',None),('overcut','Overcut · mm',None),('compensate','Drag-knife compensation',('On','Off')),
                      ('width','Pen stroke width · mm (reference)',None),('color','Pen color · #RRGGBB',None),('notes','Notes',None)]}
        for kind, fields in definitions.items():
            page = tk.Frame(book, bg=PANEL, padx=12, pady=12); book.add(page, text=kind.title())
            left = tk.Frame(page, bg=PANEL); left.pack(side='left', fill='y', padx=(0,20))
            search = tk.StringVar(self)
            self.searches[kind] = search
            workflow.label(left, 'Search ' + kind).pack(anchor='w')
            ttk.Entry(left, textvariable=search).pack(fill='x', pady=8)
            search.trace_add('write', lambda *args, k=kind: self.refresh(k))
            listing = tk.Listbox(left, width=25, font=('DejaVu Sans',11), exportselection=False, bd=0,
                                 bg='#f1f5f7', fg=INK, selectbackground='#166c5e', selectforeground='white')
            listing.pack(fill='both', expand=True); self.lists[kind] = listing
            listing.bind('<<ListboxSelect>>', lambda e, k=kind: self.select(k))
            actions = tk.Frame(left, bg=PANEL)
            actions.pack(side='bottom', fill='x', pady=6, before=listing)
            for index, (label, action) in enumerate([('Add', self.new),('Duplicate', self.duplicate),('Delete', self.delete)]):
                actions.columnconfigure(index, weight=1)
                workflow.button(actions, label, lambda a=action,k=kind: a(k)).grid(row=0, column=index, sticky='ew', padx=2)
            right = tk.Frame(page, bg=PANEL); right.pack(side='left', fill='both', expand=True)
            footer = tk.Frame(right, bg=PANEL); footer.pack(side='bottom', fill='x', pady=8)
            workflow.button(footer, 'Save preset', lambda k=kind:self.save(k)).pack(fill='x', pady=4)
            workflow.button(footer, 'Use on selected layer', lambda k=kind:self.use_on_layer(k), primary=True).pack(fill='x', pady=4)
            if kind == 'tools':
                self.color_button = workflow.button(footer, 'Choose color…', self.pick_color)
                self.color_button.pack(fill='x')
            holder = tk.Frame(right, bg=PANEL); holder.pack(fill='both', expand=True)
            holder.columnconfigure(0,weight=1); holder.rowconfigure(0,weight=1)
            canvas = tk.Canvas(holder, bg=PANEL, highlightthickness=0)
            canvas.grid(row=0,column=0,sticky='nsew')
            bar = ttk.Scrollbar(holder, command=canvas.yview); bar.grid(row=0,column=1,sticky='ns')
            canvas.configure(yscrollcommand=bar.set)
            form = tk.Frame(canvas,bg=PANEL); window = canvas.create_window(0,0,window=form,anchor='nw')
            form.bind('<Configure>', lambda e,c=canvas:c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>',lambda e,c=canvas,w=window:c.itemconfigure(w,width=e.width))
            self.forms[kind], self.widgets[kind], self.rows[kind] = {}, {}, {}
            for key,label,choices in fields:
                row = tk.Frame(form, bg=PANEL); row.pack(fill='x'); self.rows[kind][key] = row
                workflow.label(row,label,size=10).pack(anchor='w',pady=(7,2))
                var = tk.StringVar(self); self.forms[kind][key] = var
                widget = ttk.Combobox(row,textvariable=var,values=choices,state='readonly',style='Foil.TCombobox') if choices else ttk.Entry(row,textvariable=var,font=('DejaVu Sans',11))
                widget.pack(fill='x',ipady=4); self.widgets[kind][key] = widget
                if key == 'kind': widget.bind('<<ComboboxSelected>>',lambda e:self.tool_changed())
            if kind == 'tools':
                self.tool_note = workflow.label(form,'',muted=True,size=10)
                self.tool_note.configure(wraplength=470); self.tool_note.pack(fill='x',pady=12)
            self.refresh(kind); self.new(kind)
            from PlotterUI import ListDetail
            # List/detail becomes a stacked, scrollable form on a narrow screen.
            if not hasattr(self, 'adaptive_splits'):
                self.adaptive_splits = []
            self.details[kind] = ListDetail(page, left, right)
            self.adaptive_splits.append(self.details[kind])
        self.bind('<Escape>',lambda e:self.destroy())
        self.grab_set()

    def refresh(self, kind, selected=None):
        listing = self.lists[kind]; listing.delete(0,'end')
        for name in sorted(self.library.records[kind]):
            if self.searches[kind].get().casefold() in name.casefold():
                listing.insert('end',name)
        if selected:
            names = list(listing.get(0, 'end'))
            if selected in names:
                listing.selection_set(names.index(selected))
                self.select(kind)

    def new(self, kind):
        if kind in self.details:
            self.details[kind].show_detail()
        self.selected_names[kind] = None
        self.lists[kind].selection_clear(0,'end')
        defaults = validate_profile(kind, {'name':'New material' if kind=='materials' else 'New tool'})
        defaults['name'] = ''
        self.populate(kind, defaults)
        self.message.set('Enter a name and settings, then Save changes. Existing layer setups stay unchanged.')

    def populate(self, kind, record):
        for key,var in self.forms[kind].items():
            item = record[key]
            var.set(('On' if item else 'Off') if key=='compensate' else str(item))
        if kind=='tools': self.tool_changed()

    def use_on_layer(self, kind):
        name = self.selected_names[kind]
        if not name or not self.workflow.selection():
            self.message.set('Select artwork and a saved preset first.')
            return
        from PlotterLayersUI import LayersDialog
        from PlotterUI import fit_dialog
        page = LayersDialog(self.workflow)
        page.tree.selection_set(page.tree.parent('object:' + str(self.workflow.selection()[0])))
        page.selected()
        (page.material_profile if kind == 'materials' else page.tool_profile).set(name)
        if kind == 'tools':
            page.operation.set('Draw' if self.library.records[kind][name]['kind'] == 'Pen' else 'Cut')
        page.adaptive_split.show_detail()
        page.message.set('Review the selected layer setup, then Apply material & tool.')
        fit_dialog(page, self.workflow.app)

    def select(self, kind):
        if kind in self.details:
            self.details[kind].show_detail()
        selection = self.lists[kind].curselection()
        if not selection: return
        name = self.lists[kind].get(selection[0]); self.selected_names[kind] = name
        self.populate(kind, self.library.records[kind][name])

    def tool_changed(self):
        pen = self.forms['tools']['kind'].get() == 'Pen'
        for key in ('angle','offset','overcut','compensate'):
            if pen: self.forms['tools'][key].set('Off' if key=='compensate' else '0')
            self.widgets['tools'][key].configure(state='disabled' if pen else 'readonly' if key=='compensate' else 'normal')
        if not pen and self.forms['tools']['angle'].get()=='0': self.forms['tools']['angle'].set('45')
        for row in self.rows['tools'].values(): row.pack_forget()
        hidden = ('angle','offset','overcut','compensate') if pen else ('width','color')
        for key, row in self.rows['tools'].items():
            if key not in hidden: row.pack(fill='x', before=self.tool_note)
        self.tool_note.configure(text='Pen paths use no drag-knife compensation or overcut. Stroke width describes the physical pen; it does not widen the drawing paths.' if pen else 'Blade angle is a reference for choosing your physical knife. Offset and overcut affect the prepared cutting paths.')
        if pen: self.color_button.pack(fill='x')
        else: self.color_button.pack_forget()

    def pick_color(self):
        chosen = colorchooser.askcolor(parent=self, title='Pen color')[1]
        if chosen: self.forms['tools']['color'].set(chosen)

    def save(self, kind):
        if self.workflow.app.sender.running or self.workflow.app.mat_handling.active:
            self.message.set('Wait until the plotter finishes.'); return
        try:
            raw = {key:var.get() for key,var in self.forms[kind].items()}
            if kind=='tools': raw['compensate'] = raw['compensate']=='On'
            name = self.library.save(kind,raw,self.selected_names[kind])
            self.workflow.save_library(); self.refresh(kind,name)
            self.message.set('Saved. To update an existing layer, select this profile there and apply its setup again.')
        except ValueError as error: self.message.set(str(error))

    def duplicate(self, kind):
        name = self.selected_names[kind]
        if name:
            name = self.library.duplicate(kind,name)
            self.workflow.save_library(); self.refresh(kind,name)

    def delete(self, kind):
        name = self.selected_names[kind]
        if name and messagebox.askyesno('Delete profile',f'Delete “{name}” from the library? Existing project layers keep their saved setup.',parent=self):
            self.library.delete(kind,name); self.workflow.save_library(); self.refresh(kind); self.new(kind)
